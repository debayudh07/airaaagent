"""CoinGecko (free, no key required): any token's market data, price history for charts, trending
coins, global market stats, plus the Crypto Fear & Greed index from alternative.me.

Keyless use is rate limited (roughly 5-15 calls/minute); set ``COINGECKO_API_KEY`` to a free
"demo" key for higher limits.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx
from langchain_core.tools import tool

from .. import http
from ..config import get_settings
from ..utils.assets import SYMBOL_TO_COINGECKO, extract_symbols

logger = logging.getLogger(__name__)

BASE_URL = "https://api.coingecko.com/api/v3"
FEAR_GREED_URL = "https://api.alternative.me/fng/"
SOURCE = "coingecko"
MAX_COINS = 8
MAX_HISTORY_COINS = 3
MAX_POINTS = 120
_SYMBOL = re.compile(r"^[A-Z0-9]{1,15}$")
_HISTORY_WORDS = ("chart", "graph", "plot", "history", "historical", "trend", "over time", "since", "performance", "performed")
_SENTIMENT_WORDS = ("sentiment", "fear", "greed", "mood")
_id_cache: Dict[str, Optional[str]] = {s: i.split(":", 1)[1] for s, i in SYMBOL_TO_COINGECKO.items()}


def _headers() -> Dict[str, str]:
    key = get_settings().coingecko_api_key
    headers = {"Accept": "application/json"}
    if key:
        headers["x-cg-demo-api-key"] = key
    return headers


async def _get(url: str, params: Optional[Dict[str, Any]] = None) -> Tuple[Any, Optional[str]]:
    try:
        response = await http.get(url, params=params, headers=_headers())
    except httpx.HTTPError as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if response.status_code != 200:
        return None, "Rate limited by CoinGecko (HTTP 429)" if response.status_code == 429 else f"HTTP {response.status_code}"
    try:
        return response.json(), None
    except ValueError:
        return None, "Invalid JSON from CoinGecko"


async def _resolve(symbol: str) -> Optional[str]:
    """Ticker -> CoinGecko id. Picks the highest-ranked coin whose symbol matches exactly."""
    if symbol in _id_cache:
        return _id_cache[symbol]
    data, err = await _get(f"{BASE_URL}/search", {"query": symbol})
    coin_id = None
    if not err and isinstance(data, dict):
        matches = [c for c in data.get("coins", []) if str(c.get("symbol", "")).upper() == symbol]
        matches.sort(key=lambda c: c.get("market_cap_rank") or 10**9)
        coin_id = matches[0]["id"] if matches else None
    _id_cache[symbol] = coin_id
    return coin_id


def _downsample(points: List[List[float]], limit: int = MAX_POINTS) -> List[List[float]]:
    if len(points) <= limit:
        return points
    step = len(points) / limit
    sampled = [points[int(i * step)] for i in range(limit)]
    if sampled[-1] != points[-1]:
        sampled[-1] = points[-1]
    return sampled


def _market_row(c: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": c.get("id"), "symbol": str(c.get("symbol", "")).upper(), "name": c.get("name"),
        "price": c.get("current_price"), "market_cap": c.get("market_cap"), "rank": c.get("market_cap_rank"),
        "volume_24h": c.get("total_volume"),
        "percent_change_24h": c.get("price_change_percentage_24h_in_currency", c.get("price_change_percentage_24h")),
        "percent_change_7d": c.get("price_change_percentage_7d_in_currency"),
        "percent_change_30d": c.get("price_change_percentage_30d_in_currency"),
        "ath": c.get("ath"), "ath_change_percentage": c.get("ath_change_percentage"), "ath_date": c.get("ath_date"),
        "circulating_supply": c.get("circulating_supply"), "max_supply": c.get("max_supply"),
        "fully_diluted_valuation": c.get("fully_diluted_valuation"), "last_updated": c.get("last_updated"),
    }


async def _fear_greed() -> Optional[Dict[str, Any]]:
    try:
        response = await http.get(FEAR_GREED_URL, params={"limit": 7})
        rows = response.json().get("data", []) if response.status_code == 200 else []
    except (httpx.HTTPError, ValueError):
        return None
    if not rows:
        return None
    return {
        "value": int(rows[0]["value"]), "classification": rows[0]["value_classification"],
        "timestamp": rows[0]["timestamp"],
        "last_7_days": [{"value": int(r["value"]), "classification": r["value_classification"], "timestamp": r["timestamp"]} for r in rows],
    }


@tool
async def coingecko_tool(query: str, symbols: Optional[List[str]] = None, days: Optional[int] = None) -> Dict[str, Any]:
    """
    Free market data from CoinGecko for ANY listed token: price, market cap, 24h/7d/30d change, ATH,
    supply; price history for charts; trending coins; global market stats; Crypto Fear & Greed index.

    Args:
        query: The user's question (decides history / trending / global / sentiment sections).
        symbols: Token tickers (e.g. ["ETH", "PENDLE"]).
        days: Price-history window in days (1-365). Implied when the question asks for a chart or trend.
    """
    try:
        q = (query or "").lower()
        wanted = [s.strip().upper() for s in (symbols or []) if s and s.strip()] or extract_symbols(q)
        wanted = list(dict.fromkeys(s for s in wanted if _SYMBOL.match(s)))[:MAX_COINS]
        want_history = bool(days) or any(w in q for w in _HISTORY_WORDS)
        window = max(1, min(int(days or 30), 365))

        out: Dict[str, Any] = {}
        errors: List[str] = []

        if wanted:
            ids = await asyncio.gather(*(_resolve(s) for s in wanted))
            resolved = {s: i for s, i in zip(wanted, ids) if i}
            out["unresolved"] = [s for s in wanted if s not in resolved]
            if resolved:
                data, err = await _get(f"{BASE_URL}/coins/markets", {
                    "vs_currency": "usd", "ids": ",".join(resolved.values()),
                    "price_change_percentage": "24h,7d,30d",
                })
                if err:
                    errors.append(err)
                else:
                    out["markets"] = [_market_row(c) for c in data if isinstance(c, dict)]
                if want_history:
                    history: Dict[str, Any] = {}
                    for symbol, coin_id in list(resolved.items())[:MAX_HISTORY_COINS]:
                        chart, err = await _get(f"{BASE_URL}/coins/{coin_id}/market_chart", {"vs_currency": "usd", "days": window})
                        if err:
                            errors.append(f"{symbol} history: {err}")
                        elif isinstance(chart, dict) and chart.get("prices"):
                            history[symbol] = _downsample(chart["prices"])
                    if history:
                        out["history"] = {"days": window, "series": history}
        elif "trending" in q:
            data, err = await _get(f"{BASE_URL}/search/trending")
            if err:
                errors.append(err)
            else:
                out["trending"] = [
                    {"name": c["item"].get("name"), "symbol": c["item"].get("symbol"), "rank": c["item"].get("market_cap_rank"),
                     "price": (c["item"].get("data") or {}).get("price"),
                     "change_24h": ((c["item"].get("data") or {}).get("price_change_percentage_24h") or {}).get("usd")}
                    for c in (data or {}).get("coins", [])[:10]
                ]
        else:
            if any(w in q for w in ("global", "total market", "dominance", "overall market", "market overview")):
                data, err = await _get(f"{BASE_URL}/global")
                if not err and isinstance(data, dict):
                    g = data.get("data", {})
                    out["global"] = {
                        "total_market_cap_usd": (g.get("total_market_cap") or {}).get("usd"),
                        "total_volume_usd": (g.get("total_volume") or {}).get("usd"),
                        "market_cap_change_24h_pct": g.get("market_cap_change_percentage_24h_usd"),
                        "btc_dominance": (g.get("market_cap_percentage") or {}).get("btc"),
                        "eth_dominance": (g.get("market_cap_percentage") or {}).get("eth"),
                        "active_cryptocurrencies": g.get("active_cryptocurrencies"),
                    }
            data, err = await _get(f"{BASE_URL}/coins/markets", {
                "vs_currency": "usd", "order": "market_cap_desc", "per_page": 15, "page": 1,
                "price_change_percentage": "24h,7d,30d",
            })
            if err:
                errors.append(err)
            else:
                out["markets"] = [_market_row(c) for c in data if isinstance(c, dict)]

        if any(w in q for w in _SENTIMENT_WORDS) or ("market" in q and not wanted):
            fg = await _fear_greed()
            if fg:
                out["fear_greed"] = fg

        if not any(k in out for k in ("markets", "history", "trending", "global", "fear_greed")):
            message = "; ".join(errors) or (f"Unknown token(s): {', '.join(out.get('unresolved', []))}" if out.get("unresolved") else "No data")
            return {"success": False, "error": message, "source": SOURCE}
        meta = {"symbols": wanted, "days": window if want_history else None, "partial_errors": errors or None}
        return {"success": True, "data": out, "metadata": meta, "source": SOURCE}
    except Exception as exc:  # a tool must never raise into the agent loop
        logger.exception("coingecko_tool failed")
        return {"success": False, "error": str(exc), "source": SOURCE}
