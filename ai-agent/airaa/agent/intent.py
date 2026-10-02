"""Keyword intent classification. Used as the planner's fallback; the LLM planner labels intent itself."""
from __future__ import annotations

_RULES = (
    ("news", ("news", "headline", "announced", "announcement", "happening", "why did", "why is", "hack", "exploit")),
    ("comparison", ("compare", " vs ", "versus", "difference between")),
    ("analysis", ("analyze", "analyse", "analysis", "performance", "how is", "how's", "outlook", "should i", "invest")),
    ("information", ("what is", "what's", "tell me about", "info about", "information about", "explain", "details about")),
    ("defi", ("tvl", "defi", "yield", "apy", "stablecoin", "protocol", "bridge", "fees", "revenue", "lending")),
    ("technical", ("dex", "whale", "on-chain", "onchain", "transactions", "wallet", "liquidity")),
    ("market_data", ("price", "trading", "volume", "market", "trend", "cap")),
)


def classify_intent(query: str) -> str:
    q = f" {(query or '').lower()} "
    for intent, words in _RULES:
        if any(w in q for w in words):
            return intent
    return "general"
