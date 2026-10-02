"""Shared data shapes: the request, and the structured outputs the LLM must produce."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

# Progress callback used by the streaming API.
EventCallback = Optional[Callable[[Dict[str, Any]], Awaitable[None]]]

ToolName = Literal[
    "coinmarketcap_tool", "coingecko_tool", "defillama_tool", "dune_analytics_tool", "etherscan_tool",
    "dexscreener_tool", "news_tool", "web_search_tool", "read_url_tool",
]
Intent = Literal["analysis", "information", "market_data", "comparison", "technical", "defi", "general"]


@dataclass
class ResearchRequest:
    query: str
    address: Optional[str] = None
    time_range: str = "7d"
    session_id: Optional[str] = None
    data_sources: List[str] = field(default_factory=lambda: ["dune", "etherscan", "coinmarketcap", "defillama"])

    def __post_init__(self) -> None:
        if not self.session_id:
            self.session_id = str(uuid.uuid4())


class Entities(BaseModel):
    """What the question is about, extracted by the planner and handed to the tools."""

    symbols: List[str] = Field(
        default_factory=list,
        description="Ticker symbols of coins/tokens mentioned or implied, upper-case (e.g. BTC, ETH, SOL).",
    )
    protocols: List[str] = Field(
        default_factory=list,
        description="DeFiLlama protocol slugs mentioned (lower-case, hyphenated, e.g. aave, uniswap, lido, rocket-pool).",
    )
    chain: Optional[str] = Field(
        default=None, description="Blockchain the question focuses on, if any (e.g. Ethereum, Arbitrum, Solana)."
    )
    urls: List[str] = Field(default_factory=list, description="Web page URLs the user gave or that must be read.")
    search_query: Optional[str] = Field(
        default=None,
        description="A concise web/news search query for this question (e.g. 'Ethereum Fusaka upgrade date'), if search is needed.",
    )
    days: Optional[int] = Field(
        default=None, description="History window in days for price/TVL charts, if the user implies one (e.g. 30, 90, 365)."
    )


class Plan(BaseModel):
    """Planner output: the minimal set of tools needed and the entities to query."""

    intent: Intent = Field(description="Best label for what the user wants.")
    tools: List[ToolName] = Field(description="Minimal set of tools needed. Empty only if no data is needed.")
    entities: Entities = Field(default_factory=Entities)
    rationale: str = Field(default="", description="One short sentence explaining the choice.")


class FollowUp(BaseModel):
    """Reflection output: does the agent need one more round of data gathering?"""

    needs_more: bool = Field(description="True only if an important part of the question is still unanswered.")
    tools: List[ToolName] = Field(default_factory=list, description="Tools to run in the extra round.")
    entities: Entities = Field(default_factory=Entities)
    reason: str = Field(default="", description="One short sentence.")
