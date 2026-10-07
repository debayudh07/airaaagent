"""Planning and reflection.

The planner turns a question into ``Plan`` (tools + extracted entities) with structured output.
If the LLM is unavailable, slow, or returns something unusable, a rule-based plan is used so the
agent still answers. The reflector decides whether one extra round of tools is worthwhile.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional, get_args

from langchain_core.messages import HumanMessage, SystemMessage

from ..config import Settings, get_settings
from ..memory import SessionManager
from ..schemas import Entities, FollowUp, Intent, Plan, ResearchRequest
from ..tools import TOOL_CATALOG
from ..tools.web import extract_urls
from ..utils.assets import KNOWN_PROTOCOLS, extract_chain, extract_symbols
from .intent import classify_intent
from .llm import planner_llm
from .prompts import PLANNER_SYSTEM_PROMPT, REFLECT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

_DEFI_WORDS = ("tvl", "defi", "yield", "apy", "stablecoin", "protocol", "bridge", "fees", "revenue", "lending", "borrow")
_DEX_WORDS = ("dex", "whale", "swap", "liquidity", "trading pair", "trading volume", "volume analysis")
_WALLET_WORDS = ("wallet", "balance", "transactions", "my address", "my wallet", "transfers", "address")
_MARKET_WORDS = ("price", "market cap", "marketcap", "worth", "volume", "rank", "supply", "performance", "performing")
_SHORT_FOLLOWUP = re.compile(r"^\s*(and|what about|how about|also)\b", re.I)
_HISTORY_WORDS = ("chart", "graph", "plot", "history", "historical", "trend", "over time", "since", "performed", "performance")
_SENTIMENT_WORDS = ("trending", "sentiment", "fear", "greed", "mood")
_NEWS_WORDS = ("news", "headline", "announce", "happening", "why did", "why is", "why has", "hack", "exploit",
               "regulation", "lawsuit", "sec ", "etf", "this week", "today")
_WEB_WORDS = ("roadmap", "upgrade", "launch", "airdrop", "who founded", "who is", "when will", "when is",
              "tokenomics", "partnership", "testnet", "mainnet", "explain", "search", "look up", "google")
_TOKEN_WORDS = ("memecoin", "meme coin", "new token", "token address", "contract address", "launched token", "pump")
_ADDRESS = re.compile(r"0x[a-fA-F0-9]{40}")


def _catalog_text() -> str:
    return "\n".join(f"- {name}: {desc}" for name, desc in TOOL_CATALOG.items())


class Planner:
    def __init__(self, sessions: SessionManager, llm: Any = None, settings: Optional[Settings] = None) -> None:
        self.sessions = sessions
        self._llm = llm
        self.settings = settings or get_settings()

    def _model(self) -> Any:
        return self._llm if self._llm is not None else planner_llm(self.settings)

    # ------------------------------------------------------------------ plan
    async def plan(self, request: ResearchRequest) -> Dict[str, Any]:
        """Returns ``{"plan": Plan, "planner": "llm"|"heuristic", "steps": [...]}``."""
        try:
            plan = await asyncio.wait_for(self._llm_plan(request), timeout=self.settings.planner_timeout_seconds)
            plan = self._sanitise(plan, request)
            if plan.tools:
                return {"plan": plan, "planner": "llm", "steps": self._steps(plan, "LLM planner")}
            # The model says no data is needed. Honour that for conceptual questions ("what is impermanent loss?"), but
            # double-check with the rules: a named coin or protocol, a URL, or a specific topic (TVL, news, DEX data...)
            # means the empty plan was probably a mistake. The rules' two catch-alls (a bare market quote, and a web search
            # triggered by a word like "explain") are not evidence of that.
            rules = self.heuristic_plan(request)
            specific = bool(rules.entities.symbols or rules.entities.protocols or rules.entities.urls
                            or set(rules.tools) - {"coinmarketcap_tool", "web_search_tool"})
            if not specific:
                return {"plan": plan, "planner": "llm", "steps": self._steps(plan, "LLM planner")}
            logger.info("LLM planner chose no tools but the question names something to look up; using rule-based plan")
        except Exception as exc:
            logger.warning("LLM planner unavailable (%s); using rule-based plan", exc)
        plan = self.heuristic_plan(request)
        return {"plan": plan, "planner": "heuristic", "steps": self._steps(plan, "rule-based planner")}

    async def _llm_plan(self, request: ResearchRequest) -> Plan:
        structured = self._model().with_structured_output(Plan)
        history = self.sessions.history_digest(request.session_id, self.settings.history_messages)
        user = (
            f"Available tools:\n{_catalog_text()}\n\n"
            f"Wallet address provided by user: {request.address or 'none'}\n"
            f"Time range: {request.time_range}\n"
            f"Recent conversation:\n{history or '(none)'}\n\n"
            + (f"What is known about this user:\n{request.user_context}\n\n" if request.user_context else "")
            + f"Latest question: {request.query}"
        )
        result = await structured.ainvoke([SystemMessage(content=PLANNER_SYSTEM_PROMPT), HumanMessage(content=user)])
        if isinstance(result, dict):
            result = Plan.model_validate(result)
        return result

    def _sanitise(self, plan: Plan, request: ResearchRequest) -> Plan:
        tools = list(dict.fromkeys(plan.tools))
        if "etherscan_tool" in tools and not request.address:
            tools.remove("etherscan_tool")  # cannot run without an address; never guess one
        plan.tools = tools
        plan.entities.symbols = list(dict.fromkeys(s.upper() for s in plan.entities.symbols))[:10]
        plan.entities.protocols = list(dict.fromkeys(p.lower() for p in plan.entities.protocols))[:4]
        plan.entities.urls = list(dict.fromkeys([*plan.entities.urls, *extract_urls(request.query)]))[:5]
        if "read_url_tool" in tools and not plan.entities.urls:
            tools.remove("read_url_tool")  # nothing to read
        if plan.entities.days is not None:
            plan.entities.days = max(1, min(int(plan.entities.days), 365))
        return plan

    def heuristic_plan(self, request: ResearchRequest) -> Plan:
        """Keyword rules, used when the LLM planner is unavailable (e.g. rate limited)."""
        q = request.query.lower()
        symbols = extract_symbols(q)
        protocols = [p for p in KNOWN_PROTOCOLS if re.search(rf"\b{re.escape(p)}\b", q)]
        chain = extract_chain(q)
        intent = classify_intent(q)
        urls = extract_urls(request.query)

        # A bare follow-up ("and SOL?") inherits the previous question's context.
        if _SHORT_FOLLOWUP.match(q) and request.session_id:
            context = self.sessions.get(request.session_id)
            last = (context or {}).get("research_context", {}).get("last_query")
            if last and not (symbols or protocols):
                symbols = extract_symbols(last)
                protocols = [p for p in KNOWN_PROTOCOLS if re.search(rf"\b{re.escape(p)}\b", last.lower())]

        has = lambda words: any(w in q for w in words)  # noqa: E731
        defi = has(_DEFI_WORDS) or bool(protocols)
        history = has(_HISTORY_WORDS)
        news = has(_NEWS_WORDS)
        web = has(_WEB_WORDS)
        token_lookup = has(_TOKEN_WORDS) or (bool(_ADDRESS.search(request.query)) and not has(_WALLET_WORDS))
        market = has(_MARKET_WORDS)

        tools: List[str] = []
        if urls:
            tools.append("read_url_tool")
        if history or has(_SENTIMENT_WORDS):
            tools.append("coingecko_tool")  # history for charts, trending, Fear & Greed
        elif symbols and (market or not (defi or news or web)) or not (defi or news or web or urls or token_lookup):
            tools.append("coinmarketcap_tool")
        if defi:
            tools.append("defillama_tool")
        if has(_DEX_WORDS):
            tools.append("dune_analytics_tool")
        if token_lookup:
            tools.append("dexscreener_tool")
        if request.address and has(_WALLET_WORDS):
            tools.append("etherscan_tool")
        if news:
            tools.append("news_tool")
        if web and not urls:
            tools.append("web_search_tool")
        if intent in ("analysis", "comparison") and symbols and "coingecko_tool" not in tools:
            tools.append("coingecko_tool")  # 30-day history gives the analysis (and a chart) context

        return Plan(
            intent=intent if intent in get_args(Intent) else "general",
            tools=list(dict.fromkeys(tools)),
            entities=Entities(symbols=symbols, protocols=protocols, chain=chain, urls=urls),
            rationale="Chosen from keywords in the question.",
        )

    @staticmethod
    def _steps(plan: Plan, who: str) -> List[str]:
        steps = [f"Planned with the {who}: intent '{plan.intent}'"]
        steps += [f"Selected {t} - {TOOL_CATALOG[t].split(';')[0].split('.')[0]}" for t in plan.tools]
        if plan.entities.symbols:
            steps.append(f"Assets: {', '.join(plan.entities.symbols)}")
        if plan.entities.protocols:
            steps.append(f"Protocols: {', '.join(plan.entities.protocols)}")
        if plan.rationale:
            steps.append(f"Rationale: {plan.rationale}")
        return steps

    # --------------------------------------------------------------- reflect
    async def reflect(self, request: ResearchRequest, plan: Plan, results: List[Dict[str, Any]]) -> Optional[FollowUp]:
        """Ask whether one more round would help. Any failure means 'no'; reflection is best-effort."""
        try:
            return await asyncio.wait_for(
                self._llm_reflect(request, plan, results), timeout=self.settings.planner_timeout_seconds
            )
        except Exception as exc:
            logger.info("Reflection skipped: %s", exc)
            return None

    async def _llm_reflect(self, request: ResearchRequest, plan: Plan, results: List[Dict[str, Any]]) -> FollowUp:
        lines = []
        for r in results:
            status = "ok" if r.get("success") else f"FAILED ({r.get('error', 'unknown')})"
            lines.append(f"- {r.get('tool')}: {status}")
        user = (
            f"Available tools:\n{_catalog_text()}\n\n"
            f"Question: {request.query}\n"
            f"Wallet address provided: {'yes' if request.address else 'no'}\n"
            f"Entities: symbols={plan.entities.symbols} protocols={plan.entities.protocols} chain={plan.entities.chain}\n"
            f"Tools run so far:\n" + "\n".join(lines)
        )
        structured = self._model().with_structured_output(FollowUp)
        result = await structured.ainvoke([SystemMessage(content=REFLECT_SYSTEM_PROMPT), HumanMessage(content=user)])
        if isinstance(result, dict):
            result = FollowUp.model_validate(result)
        if "etherscan_tool" in result.tools and not request.address:
            result.tools.remove("etherscan_tool")
        return result
