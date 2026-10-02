"""Static knowledge for turning free text into asset/chain identifiers.

This is only a *fallback*: the LLM planner extracts entities for any coin or protocol, and
these maps cover the common cases when the planner is unavailable.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

# name or ticker (lower-case) -> ticker
NAME_TO_SYMBOL: Dict[str, str] = {
    "bitcoin": "BTC", "btc": "BTC",
    "ethereum": "ETH", "eth": "ETH", "ether": "ETH",
    "solana": "SOL", "sol": "SOL",
    "cardano": "ADA", "ada": "ADA",
    "polkadot": "DOT", "dot": "DOT",
    "chainlink": "LINK", "link": "LINK",
    "litecoin": "LTC", "ltc": "LTC",
    "dogecoin": "DOGE", "doge": "DOGE",
    "ripple": "XRP", "xrp": "XRP",
    "binance coin": "BNB", "bnb": "BNB",
    "polygon": "POL", "matic": "POL", "pol": "POL",
    "avalanche": "AVAX", "avax": "AVAX",
    "tether": "USDT", "usdt": "USDT",
    "usd coin": "USDC", "usdc": "USDC",
    "arbitrum": "ARB", "optimism": "OP",
    "uniswap": "UNI", "aave": "AAVE", "lido": "LDO",
}

SYMBOL_TO_COINGECKO: Dict[str, str] = {
    "BTC": "coingecko:bitcoin", "ETH": "coingecko:ethereum", "SOL": "coingecko:solana",
    "USDT": "coingecko:tether", "USDC": "coingecko:usd-coin", "BNB": "coingecko:binancecoin",
    "LINK": "coingecko:chainlink", "POL": "coingecko:matic-network", "AVAX": "coingecko:avalanche-2",
    "ADA": "coingecko:cardano", "DOT": "coingecko:polkadot", "LTC": "coingecko:litecoin",
    "DOGE": "coingecko:dogecoin", "XRP": "coingecko:ripple", "ARB": "coingecko:arbitrum",
    "OP": "coingecko:optimism", "UNI": "coingecko:uniswap", "AAVE": "coingecko:aave", "LDO": "coingecko:lido-dao",
}

KNOWN_PROTOCOLS: List[str] = [
    "aave", "curve", "uniswap", "makerdao", "compound", "rocket-pool", "lido", "morpho", "eigenlayer",
]

SUPPORTED_CHAINS: List[str] = [
    "ethereum", "arbitrum", "optimism", "polygon", "bsc", "avalanche", "solana",
    "base", "fantom", "zksync", "tron", "linea",
]

# Etherscan V2 chain ids (one API key covers all of them)
ETHERSCAN_CHAIN_IDS: Dict[str, int] = {
    "ethereum": 1, "optimism": 10, "bsc": 56, "polygon": 137, "base": 8453,
    "arbitrum": 42161, "avalanche": 43114, "linea": 59144,
}


def extract_symbols(text: str) -> List[str]:
    """Tickers for every known coin/token name in ``text``, in order of appearance."""
    lowered = (text or "").lower()
    hits = []
    for name, symbol in NAME_TO_SYMBOL.items():
        match = re.search(rf"\b{re.escape(name)}\b", lowered)
        if match:
            hits.append((match.start(), symbol))
    ordered: List[str] = []
    for _, symbol in sorted(hits):
        if symbol not in ordered:
            ordered.append(symbol)
    return ordered


def extract_chain(text: str) -> Optional[str]:
    """Chain name in the capitalisation DefiLlama expects (``BSC`` stays upper-case)."""
    lowered = (text or "").lower()
    for chain in SUPPORTED_CHAINS:
        if re.search(rf"\b{chain}\b", lowered):
            return "BSC" if chain == "bsc" else chain.capitalize()
    return None


def to_coingecko_ids(symbols: List[str]) -> List[str]:
    return [SYMBOL_TO_COINGECKO[s] for s in symbols if s in SYMBOL_TO_COINGECKO]
