"""Etherscan API V2 (multichain): wallet balance, transactions and token transfers.

V1 (``api.etherscan.io/api``) was shut down in August 2025; V2 takes a ``chainid`` parameter
and one API key covers every supported chain.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

import httpx
from langchain_core.tools import tool

from .. import http
from ..config import get_settings
from ..utils.assets import ETHERSCAN_CHAIN_IDS

logger = logging.getLogger(__name__)

BASE_URL = "https://api.etherscan.io/v2/api"
SOURCE = "etherscan"
_ADDRESS = re.compile(r"^0x[a-fA-F0-9]{40}$")


def _actions_for(query: str) -> tuple[str, Dict[str, Any]]:
    q = query.lower()
    if "balance" in q:
        return "balance", {"module": "account", "action": "balance", "tag": "latest"}
    if "token" in q or "transfer" in q:
        return "tokentx", {"module": "account", "action": "tokentx", "page": 1, "offset": 50, "sort": "desc"}
    return "txlist", {"module": "account", "action": "txlist", "page": 1, "offset": 50, "sort": "desc"}


@tool
async def etherscan_tool(query: str, address: Optional[str] = None, chain: Optional[str] = None) -> Dict[str, Any]:
    """
    Get on-chain wallet data from Etherscan V2: ETH balance, recent transactions or token transfers.
    Requires a wallet address.

    Args:
        query: What to look up ("balance", "transactions", "token transfers").
        address: Wallet address (0x...).
        chain: EVM chain name (ethereum, base, arbitrum, optimism, polygon, bsc, avalanche, linea). Default ethereum.
    """
    api_key = get_settings().etherscan_api_key
    if not api_key:
        return {"success": False, "error": "Etherscan API key not configured", "source": SOURCE}
    if not address or not _ADDRESS.match(address):
        return {"success": False, "error": "Etherscan needs a valid 0x wallet address", "source": SOURCE}

    chain_name = (chain or "ethereum").lower()
    chain_id = ETHERSCAN_CHAIN_IDS.get(chain_name)
    if chain_id is None:
        return {"success": False, "error": f"Chain '{chain_name}' is not supported by this tool", "source": SOURCE}

    kind, params = _actions_for(query)
    params = {**params, "chainid": chain_id, "address": address, "apikey": api_key}

    try:
        response = await http.get(BASE_URL, params=params)
    except httpx.HTTPError as exc:
        return {"success": False, "error": f"{type(exc).__name__}: {exc}", "source": SOURCE}
    if response.status_code != 200:
        return {"success": False, "error": f"HTTP {response.status_code}", "source": SOURCE}

    try:
        data = response.json()
    except ValueError:
        return {"success": False, "error": "Invalid JSON from Etherscan", "source": SOURCE}

    # Etherscan reports API-level errors with HTTP 200 and status "0" (except "no transactions found").
    if str(data.get("status")) == "0" and "no transactions" not in str(data.get("message", "")).lower():
        detail = data.get("result") if isinstance(data.get("result"), str) else data.get("message")
        return {"success": False, "error": f"Etherscan: {detail}", "source": SOURCE}

    return {
        "success": True,
        "data": data,
        "metadata": {"query_type": kind, "chain": chain_name, "address": address},
        "source": SOURCE,
    }
