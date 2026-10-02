"""The research agent: plan -> gather -> (reflect -> gather again) -> synthesise.

    greeting?  -> canned reply, no LLM or data calls
    plan       -> LLM picks tools and extracts entities (rule-based fallback)
    gather     -> tools run in parallel with timeouts and retry on transient errors
    reflect    -> only if something failed: one extra round if the LLM thinks it would help
    synthesise -> streamed answer grounded in the verified data; data-only fallback if the LLM is down
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ..config import Settings, get_settings
from ..greeting import detect_greeting, get_greeting_response
from ..http import client_scope
from ..memory import SessionManager, get_session_manager
from ..schemas import EventCallback, Plan, ResearchRequest
from .context import build_context, plain_summary
from .executor import emit, run_tools
from .llm import synthesis_llm, text_of
from .merge import merge_results, new_merged
from .planner import Planner
from .prompts import SYNTHESIS_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

SOURCE_LABELS = {
    "coinmarketcap": "CoinMarketCap", "defillama": "DefiLlama",
    "dune_analytics": "Dune", "etherscan": "Etherscan",
}
_UNRECOVERABLE = ("not configured", "only supports", "unsupported", "valid 0x", "invalid")


def _label(source: str) -> str:
    return SOURCE_LABELS.get(source, source)


def _footer(merged: Dict[str, Any]) -> str:
    meta = merged["metadata"]
    if not meta["tools_attempted"]:
        return ""
    used = ", ".join(_label(s) for s in meta["sources_used"]) or "none"
    line = f"*Sources: {used} · {meta['tools_succeeded']} of {meta['tools_attempted']} responded*"
    failed = meta["failed_sources"]
    if failed:
        line += "  \n*Unavailable: " + "; ".join(f"{_label(f['source'])} ({f['error'][:80]})" for f in failed) + "*"
    return "\n\n---\n" + line


class Web3ResearchAgent:
    def __init__(
        self,
        session_id: Optional[str] = None,
        *,
        sessions: Optional[SessionManager] = None,
        settings: Optional[Settings] = None,
        planner_llm: Any = None,
        synthesis_model: Any = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.sessions = sessions or get_session_manager()
        self.session = self.sessions.get_or_create(session_id)
        self.session_id: str = self.session["id"]
        self.planner = Planner(self.sessions, llm=planner_llm, settings=self.settings)
        self._synthesis_model = synthesis_model

    # ------------------------------------------------------------------ public
    async def research(self, request: ResearchRequest, on_event: EventCallback = None) -> Dict[str, Any]:
        started = time.perf_counter()
        if request.session_id and request.session_id != self.session_id:
            self.session = self.sessions.get_or_create(request.session_id)
            self.session_id = self.session["id"]
        request.session_id = self.session_id

        if detect_greeting(request.query):
            return self._greeting(request, started)

        steps: List[str] = []
        try:
            async with client_scope():
                return await self._research(request, on_event, started, steps)
        except Exception as exc:
            logger.exception("Research failed")
            return {
                "success": False,
                "error": str(exc),
                "reasoning_steps": steps,
                "citations": [],
                "data_sources_used": [],
                "execution_time": round(time.perf_counter() - started, 2),
                "query_intent": "general",
                "tool_trace": [],
                "session_id": self.session_id,
            }

    # ------------------------------------------------------------------ pipeline
    async def _research(self, request: ResearchRequest, on_event: EventCallback, started: float, steps: List[str]) -> Dict[str, Any]:
        await emit(on_event, {"type": "status", "stage": "planning", "message": "Planning which data sources to query"})
        planned = await self.planner.plan(request)
        plan: Plan = planned["plan"]
        steps.extend(planned["steps"])
        await emit(on_event, {
            "type": "plan",
            "tools": plan.tools,
            "rationale": plan.rationale,
            "planner": planned["planner"],
            "entities": plan.entities.model_dump(),
        })

        merged = new_merged()
        trace: List[Dict[str, Any]] = []
        if plan.tools:
            await emit(on_event, {"type": "status", "stage": "gathering", "message": "Gathering data"})
            results = await run_tools(plan.tools, request, plan.entities, on_event, self.settings)
            merged = merge_results(results)
            trace.extend(self._trace(results, round_no=1))
            steps.append(f"Ran {len(results)} tool(s): " + ", ".join(
                f"{r['tool']} ({'ok' if r.get('success') else 'failed'}, {r['duration_ms']}ms)" for r in results))

            for round_no in range(2, 2 + self.settings.max_followup_rounds):
                extra = await self._follow_up(request, plan, results, merged, on_event, steps)
                if not extra:
                    break
                results = extra
                merged = merge_results(results, merged)
                trace.extend(self._trace(results, round_no=round_no))
        else:
            steps.append("No live data needed for this question")

        await emit(on_event, {"type": "status", "stage": "synthesizing", "message": "Writing the analysis"})
        text, degraded = await self._synthesise(request, plan, merged, on_event)
        steps.append(
            f"Wrote the answer with {self.settings.synthesis_model}" if not degraded
            else "Language model unavailable; returned the retrieved data instead"
        )
        final = text.rstrip() + _footer(merged)

        sources = list(merged["metadata"]["sources_used"])
        citations = [
            {"source": s, "timestamp": datetime.now().isoformat(), "query_context": request.query[:100]} for s in sources
        ]
        score = merged["metadata"]["completeness_score"]
        elapsed = round(time.perf_counter() - started, 2)

        research_data = {
            "success": True, "result": final, "reasoning_steps": steps, "citations": citations,
            "data_sources_used": sources, "query_intent": plan.intent, "merged_data": merged,
            "data_quality_score": score, "tool_trace": trace, "planner": planned["planner"],
            "execution_time": elapsed,
        }
        self._remember(request, final, research_data)
        return {**research_data, "degraded": degraded, "session_id": self.session_id,
                "models": {"planner": self.settings.planner_model, "synthesis": self.settings.synthesis_model}}

    async def _follow_up(self, request, plan, results, merged, on_event, steps) -> Optional[List[Dict[str, Any]]]:
        """One reflection step. Returns the extra round's results, or ``None`` if nothing more is needed."""
        if not self._worth_reflecting(results, merged):
            return None
        decision = await self.planner.reflect(request, plan, results)
        if not decision or not decision.needs_more:
            return None
        succeeded = {r["tool"] for r in results if r.get("success")}
        tools = [t for t in decision.tools if t not in succeeded or decision.entities.symbols or decision.entities.protocols]
        if not tools:
            return None
        entities = plan.entities.model_copy(update={
            "symbols": list(dict.fromkeys(plan.entities.symbols + decision.entities.symbols)),
            "protocols": list(dict.fromkeys(plan.entities.protocols + decision.entities.protocols)),
            "chain": decision.entities.chain or plan.entities.chain,
        })
        steps.append(f"Follow-up round: {', '.join(tools)} ({decision.reason or 'filling gaps'})")
        await emit(on_event, {"type": "status", "stage": "gathering", "message": "Filling gaps in the data"})
        await emit(on_event, {"type": "followup", "tools": tools, "reason": decision.reason})
        return await run_tools(tools, request, entities, on_event, self.settings) or None

    @staticmethod
    def _worth_reflecting(results: List[Dict[str, Any]], merged: Dict[str, Any]) -> bool:
        failed = [r for r in results if not r.get("success")]
        if not failed:
            return False
        recoverable = [r for r in failed if not any(m in str(r.get("error", "")).lower() for m in _UNRECOVERABLE)]
        has_data = bool(merged["primary_data"] or merged["supplementary_data"])
        return bool(recoverable) or not has_data

    async def _synthesise(self, request: ResearchRequest, plan: Plan, merged: Dict[str, Any], on_event: EventCallback):
        """Stream the answer. Returns ``(text, degraded)``; never raises."""
        if plan.tools:
            context = build_context(request, plan, merged)
        else:
            context = (
                f"QUESTION: {request.query}\n\nNo live data was retrieved because none was needed. Answer conceptual "
                "questions from general knowledge, and do not state any prices, TVL, APYs, volumes or other live figures."
            )
        messages = [SystemMessage(content=SYNTHESIS_SYSTEM_PROMPT)]
        messages += self.sessions.recent_messages(self.session_id, self.settings.history_messages)
        messages.append(HumanMessage(content=context))

        chunks: List[str] = []
        try:
            llm = self._synthesis_model if self._synthesis_model is not None else synthesis_llm(self.settings)
            async for chunk in llm.astream(messages):
                piece = text_of(chunk)
                if piece:
                    chunks.append(piece)
                    await emit(on_event, {"type": "token", "text": piece})
            text = "".join(chunks).strip()
            if text:
                return text, False
            raise RuntimeError("model returned an empty answer")
        except Exception as exc:
            logger.error("Synthesis failed: %s", exc)
            if not plan.tools or not (merged["primary_data"] or merged["supplementary_data"]):
                raise  # nothing useful to fall back to; surface the error to the caller
            return plain_summary(request, plan, merged), True

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _trace(results: List[Dict[str, Any]], round_no: int) -> List[Dict[str, Any]]:
        return [
            {
                "tool": r.get("tool"), "success": bool(r.get("success")), "duration_ms": r.get("duration_ms"),
                "attempts": r.get("attempts", 1), "round": round_no,
                "error": None if r.get("success") else r.get("error"),
            }
            for r in results
        ]

    def _remember(self, request: ResearchRequest, answer: str, research_data: Dict[str, Any]) -> None:
        now = datetime.now().isoformat()
        user = HumanMessage(content=request.query, additional_kwargs={"timestamp": now})
        ai = AIMessage(content=answer, additional_kwargs={"timestamp": now, "research_data": research_data})
        self.sessions.record_turn(self.session_id, user, ai)
        self.sessions.update_context(self.session_id, {
            "last_query": request.query,
            "query_intent": research_data["query_intent"],
            "data_sources": research_data["data_sources_used"],
        })

    def _greeting(self, request: ResearchRequest, started: float) -> Dict[str, Any]:
        reply = get_greeting_response(request.query, self.session)
        self._remember(request, reply, {
            "success": True, "result": reply, "reasoning_steps": [], "citations": [],
            "data_sources_used": [], "query_intent": "greeting", "merged_data": new_merged(), "data_quality_score": 100,
        })
        return {
            "success": True, "result": reply, "reasoning_steps": ["Detected a greeting; no data sources needed"],
            "citations": [], "data_sources_used": [], "execution_time": round(time.perf_counter() - started, 2),
            "query_intent": "greeting", "session_id": self.session_id, "tool_trace": [],
            "data_quality_score": 100, "metadata": {"is_greeting": True},
        }
