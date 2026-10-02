"""Tool registry. ``TOOLS`` maps the names the planner uses to LangChain tools."""
from __future__ import annotations

from typing import Dict

from langchain_core.tools import BaseTool

from .coinmarketcap import coinmarketcap_tool
from .defillama import defillama_tool
from .dune import dune_analytics_tool
from .etherscan import etherscan_tool

TOOLS: Dict[str, BaseTool] = {
    "coinmarketcap_tool": coinmarketcap_tool,
    "defillama_tool": defillama_tool,
    "dune_analytics_tool": dune_analytics_tool,
    "etherscan_tool": etherscan_tool,
}

# Shown to the planner. Keep each line about *when* to use the tool.
TOOL_CATALOG: Dict[str, str] = {
    "coinmarketcap_tool": "Live price, 24h/7d change, market cap, volume, rank and supply for specific coins; also market listings and global metrics.",
    "defillama_tool": "DeFi data: protocol TVL, chain TVL, stablecoin supply, yield/APY pools, DEX volume, fees/revenue, bridges.",
    "dune_analytics_tool": "DEX trading pairs ranked by volume and liquidity on a chain.",
    "etherscan_tool": "A wallet's ETH balance, recent transactions and token transfers. Needs a wallet address from the user.",
}

__all__ = ["TOOLS", "TOOL_CATALOG"]
