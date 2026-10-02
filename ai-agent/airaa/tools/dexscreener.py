"""DEX Screener (free, no key): live DEX pairs for any token, including brand-new and long-tail tokens
that are not on CoinMarketCap/CoinGecko yet."""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

import httpx
from langchain_core.tools import tool

from .. import http

logger = logging.getLogger(__name__)

SEARCH_URL = "https://api.dexscreener.com/latest/dex/search"
TOKEN_URL = "https://api.dexscreener.com/latest/dex/tokens/{address}"
SOURCE = "dexscreener"
_ADDRESS = re.compile(r"0x[a-fA-F0-9]{40}")


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _pair(p: Dict[str, Any]) -> Dict[str, Any]:
    base, quote = p.get("baseToken") or {}, p.get("quoteToken") or {}
    return {
        "pair": f"{base.get('symbol')}/{quote.get('symbol')}",
        "base_name": base.get("name"), "base_address": base.get("address"),
        "chain": p.get("chainId"), "dex": p.get("dexId"),
        "price_usd": p.get("priceUsd"),
        "price_change_24h": (p.get("priceChange") or {}).get("h24"),
        "volume_24h": (p.get("volume") or {}).get("h24"),
        "liquidity_usd": (p.get("liquidity") or {}).get("usd"),
        "fdv": p.get("fdv"), "market_cap": p.get("marketCap"),
        "pair_created_at": p.get("pairCreatedAt"),
        "url": p.get("url"),
    }


@tool
async def dexscreener_tool(query: str, search: Optional[str] = None) -> Dict[str, Any]:
    """
    Live DEX trading pairs from DEX Screener for any token name, symbol or contract address: price,
    24h change, volume, liquidity, FDV, chain and DEX. Good for new/small tokens and memecoins.

    Args:
        query: The user's question.
        search: The token name/symbol/address to look up (defaults to the question).
    """
    term = (search or query or "").strip()
    address = _ADDRESS.search(term)
    try:
        if address:
            response = await http.get(TOKEN_URL.format(address=address.group(0)))
        else:
            response = await http.get(SEARCH_URL, params={"q": term[:100]})
    except httpx.HTTPError as exc:
        return {"success": False, "error": f"{type(exc).__name__}: {exc}", "source": SOURCE}
    if response.status_code != 200:
        return {"success": False, "error": f"HTTP {response.status_code}", "source": SOURCE}
    try:
        pairs = response.json().get("pairs") or []
    except ValueError:
        return {"success": False, "error": "Invalid JSON from DEX Screener", "source": SOURCE}
    if not pairs:
        return {"success": False, "error": f"No DEX pairs found for '{term[:60]}'", "source": SOURCE}

    rows: List[Dict[str, Any]] = [_pair(p) for p in pairs if isinstance(p, dict)]
    rows.sort(key=lambda r: _num(r["liquidity_usd"]), reverse=True)
    return {
        "success": True,
        "data": {"search": term[:100], "pairs_found": len(rows), "top_pairs": rows[:10]},
        "metadata": {"query_type": "token" if address else "search"},
        "source": SOURCE,
    }
