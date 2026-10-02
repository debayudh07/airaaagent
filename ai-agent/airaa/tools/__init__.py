"""Tool registry. ``TOOLS`` maps the names the planner uses to LangChain tools."""
from __future__ import annotations

from typing import Dict

from langchain_core.tools import BaseTool

from .coingecko import coingecko_tool
from .coinmarketcap import coinmarketcap_tool
from .defillama import defillama_tool
from .dexscreener import dexscreener_tool
from .dune import dune_analytics_tool
from .etherscan import etherscan_tool
from .web import news_tool, read_url_tool, web_search_tool

TOOLS: Dict[str, BaseTool] = {
    "coinmarketcap_tool": coinmarketcap_tool,
    "coingecko_tool": coingecko_tool,
    "defillama_tool": defillama_tool,
    "dune_analytics_tool": dune_analytics_tool,
    "etherscan_tool": etherscan_tool,
    "dexscreener_tool": dexscreener_tool,
    "news_tool": news_tool,
    "web_search_tool": web_search_tool,
    "read_url_tool": read_url_tool,
}

# Shown to the planner. Each line says *when* to use the tool.
TOOL_CATALOG: Dict[str, str] = {
    "coinmarketcap_tool": "Live price, 24h/7d change, market cap, volume, rank and supply for major coins; market listings and global metrics.",
    "coingecko_tool": "Free market data for ANY listed token (incl. small caps), price HISTORY for charts/trends, trending coins, global stats, Fear & Greed sentiment index.",
    "defillama_tool": "DeFi data: protocol TVL (with history), chain TVL, stablecoin supply, yield/APY pools, DEX volume, fees/revenue, bridges.",
    "dune_analytics_tool": "DEX trading pairs ranked by volume and liquidity on a chain (Dune; may be days old).",
    "etherscan_tool": "A wallet's balance, recent transactions and token transfers on EVM chains. Needs a wallet address from the user.",
    "dexscreener_tool": "Live DEX pairs for any token name/symbol/contract: price, liquidity, volume, FDV. Best for new, small or meme tokens.",
    "news_tool": "Latest crypto news headlines (CoinDesk, Cointelegraph, Decrypt, The Block, web news) for a topic or token.",
    "web_search_tool": "General web search for things data APIs don't cover: upgrades, roadmaps, launches, hacks, regulation, people, explanations.",
    "read_url_tool": "Open and read specific web pages (links the user gave, or articles found by search) and extract the facts.",
}

__all__ = ["TOOLS", "TOOL_CATALOG"]
