"""CoinMarketCap Pro API: live quotes, listings, global metrics."""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

import httpx
from langchain_core.tools import tool

from .. import http
from ..config import get_settings
from ..utils.assets import extract_symbols

logger = logging.getLogger(__name__)

BASE_URL = "https://pro-api.coinmarketcap.com/v1"
SOURCE = "coinmarketcap"
MAX_SYMBOLS = 10
_SYMBOL = re.compile(r"^[A-Z0-9]{1,12}$")


def _error_message(response: httpx.Response) -> str:
    try:
        message = (response.json().get("status") or {}).get("error_message")
    except ValueError:
        message = None
    prefix = "Rate limited by CoinMarketCap. " if response.status_code == 429 else ""
    return prefix + (message or f"HTTP {response.status_code}")


def _normalise_symbols(symbols: Optional[List[str]], query: str) -> List[str]:
    candidates = [s.strip().upper() for s in (symbols or []) if s and s.strip()] or extract_symbols(query)
    unique = list(dict.fromkeys(s for s in candidates if _SYMBOL.match(s)))
    return unique[:MAX_SYMBOLS]


def _endpoint_for(query: str) -> tuple[str, Dict[str, str], str]:
    """Pick a non-coin-specific endpoint from keywords: (path, params, query_type)."""
    q = query.lower()
    listings = {"start": "1", "convert": "USD", "sort": "market_cap", "sort_dir": "desc"}
    if any(k in q for k in ("key info", "api usage", "limits")):
        return "/key/info", {}, "key_info"
    if any(k in q for k in ("global", "total market", "market overview")):
        return "/global-metrics/quotes/latest", {"convert": "USD"}, "global_metrics"
    if "trending" in q:
        return "/cryptocurrency/trending/latest", {}, "trending"
    if any(k in q for k in ("ranking", "market cap", "top ")):
        return "/cryptocurrency/listings/latest", {**listings, "limit": "20"}, "listings"
    return "/cryptocurrency/listings/latest", {**listings, "limit": "25"}, "listings"


@tool
async def coinmarketcap_tool(query: str, symbols: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Get cryptocurrency market data from CoinMarketCap: price, 24h/7d change, market cap,
    volume, rank and supply for specific coins, or market-wide listings and global metrics.

    Args:
        query: The user's question (used to pick listings/global/trending when no coin is named).
        symbols: Ticker symbols to quote (e.g. ["BTC", "ETH"]). Up to 10.
    """
    api_key = get_settings().coinmarketcap_api_key
    if not api_key:
        return {"success": False, "error": "CoinMarketCap API key not configured", "source": SOURCE}

    headers = {"X-CMC_PRO_API_KEY": api_key, "Accept": "application/json"}
    wanted = _normalise_symbols(symbols, query)

    if wanted:
        path, params, query_type = "/cryptocurrency/quotes/latest", {"symbol": ",".join(wanted), "convert": "USD"}, "quotes_latest"
    else:
        path, params, query_type = _endpoint_for(query)

    try:
        response = await http.get(f"{BASE_URL}{path}", headers=headers, params=params)
    except httpx.HTTPError as exc:
        logger.warning("CoinMarketCap request failed: %s", exc)
        return {"success": False, "error": f"{type(exc).__name__}: {exc}", "source": SOURCE}

    if response.status_code != 200:
        message = _error_message(response)
        logger.warning("CoinMarketCap %s -> %s", path, message)
        return {"success": False, "error": message, "source": SOURCE}

    try:
        data = response.json()
    except ValueError:
        return {"success": False, "error": "Invalid JSON from CoinMarketCap", "source": SOURCE}

    metadata: Dict[str, Any] = {"query_type": query_type}
    if wanted:
        metadata.update({"symbol": wanted[0], "symbols": wanted})
    return {"success": True, "data": data, "metadata": metadata, "source": SOURCE}
