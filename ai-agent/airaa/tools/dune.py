"""Dune Analytics: DEX pair volume and liquidity.

Dune serves its curated "DEX pairs" table as a regular saved query (id 3568055), read through the
query-results endpoint with ``filters``/``sort_by``/``limit``. (There is no ``/dex/pairs/{chain}`` route;
the old integration called one and always got a 404.)

The results are whatever the query last computed, which may be old, so the tool reports ``as_of`` and the
answer layer flags stale data instead of presenting it as live.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

import httpx
from langchain_core.tools import tool

from .. import http
from ..config import get_settings
from ..utils.assets import extract_chain

logger = logging.getLogger(__name__)

DEX_PAIRS_QUERY_ID = 3568055
RESULTS_URL = f"https://api.dune.com/api/v1/query/{DEX_PAIRS_QUERY_ID}/results"
SOURCE = "dune_analytics"
_ADDRESS = re.compile(r"^0x[a-fA-F0-9]{40}$")
_DEX_WORDS = ("dex", "pair", "trading", "swap", "volume", "liquidity", "whale", "uniswap", "ethereum", "eth", "bitcoin", "btc")

# Our chain names -> the values in the table's ``chain`` column. Chains absent here have no data.
DUNE_CHAIN_NAMES: Dict[str, str] = {
    "ethereum": "ethereum", "arbitrum": "arbitrum", "optimism": "optimism", "polygon": "polygon",
    "base": "base", "bsc": "bnb", "fantom": "fantom", "zksync": "zksync", "solana": "solana",
}


def _fail(message: str) -> Dict[str, Any]:
    return {"success": False, "error": message, "source": SOURCE}


@tool
async def dune_analytics_tool(
    query: str,
    address: Optional[str] = None,
    time_range: str = "7d",
    chain: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get DEX trading-pair analytics from Dune: 24h/7d/30d volume and USD liquidity per pair on a chain,
    sorted by 24h volume. Results carry an ``as_of`` timestamp because Dune serves a saved query's last run.

    Args:
        query: The user's question.
        address: Optional token contract address to filter pairs by.
        time_range: Requested window (informational; the table reports fixed 1d/7d/30d windows).
        chain: Blockchain name (ethereum, arbitrum, base, ...). Defaults to ethereum.
    """
    api_key = get_settings().dune_api_key
    if not api_key:
        return _fail("Dune API key not configured")

    q = (query or "").lower()
    if not any(w in q for w in _DEX_WORDS):
        return _fail("Dune tool only supports DEX pair/volume questions")

    chain_name = (chain or extract_chain(q) or "ethereum").lower()
    dune_chain = DUNE_CHAIN_NAMES.get(chain_name)
    if dune_chain is None:
        return _fail(f"Dune DEX data is not available for chain: {chain_name}")

    filters = f"chain = '{dune_chain}'"
    if address:
        if not _ADDRESS.match(address):
            return _fail("Invalid token address")
        if any(w in q for w in ("address", "token", "specific", "particular", "contract")):
            addr = address.lower()
            filters += f" AND (token_a_address = '{addr}' OR token_b_address = '{addr}')"

    try:
        response = await http.get(
            RESULTS_URL,
            headers={"X-Dune-API-Key": api_key, "Accept": "application/json"},
            params={"limit": 50, "filters": filters, "sort_by": "one_day_volume desc"},
            timeout=60.0,
        )
    except httpx.HTTPError as exc:
        return _fail(f"{type(exc).__name__}: {exc}")
    if response.status_code != 200:
        return _fail(f"Dune API HTTP {response.status_code}")

    try:
        payload = response.json()
    except ValueError:
        return _fail("Invalid JSON from Dune")

    result = payload.get("result") if isinstance(payload, dict) else None
    rows = result.get("rows") if isinstance(result, dict) else None
    if not isinstance(rows, list) or not rows:
        return _fail("Dune returned no DEX pairs")

    return {
        "success": True,
        "data": rows,
        "metadata": {
            "query_type": "dex_pairs",
            "chain": chain_name,
            "total_results": len(rows),
            "time_range": time_range,
            "as_of": payload.get("execution_ended_at"),
        },
        "source": SOURCE,
    }
