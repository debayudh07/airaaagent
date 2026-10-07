"""Scheduled research: run each due alert rule as the wallet that owns it and drop the result in its inbox.

    python -m airaa.alerts.runner            # run whatever is due now, then exit (cron / GitHub Actions / Render cron)
    POST /api/internal/alerts/run            # same thing over HTTP with the X-Cron-Secret header (see alert_routes)

Rules are claimed atomically before running (``AlertsRepo.claim_due``), so overlapping runners never double-run a rule.
Automated runs read the owner's memory and watchlist but never write long-term memory, and they use a throwaway
conversation so they do not clutter the owner's chat history.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import uuid
from typing import Any, Callable, Dict, Optional, Tuple

from pydantic import BaseModel, Field

from ..schemas import ResearchRequest

logger = logging.getLogger(__name__)

INBOX_SUMMARY_CHARS = 6000


class Verdict(BaseModel):
    notify: bool = Field(description="True only if the condition is clearly met by the research result.")
    reason: str = Field(default="", description="One short sentence explaining the decision.")


JUDGE_PROMPT = (
    "You decide whether a research result satisfies a user's alert condition. Answer notify=true only when the "
    "result clearly and specifically meets the condition, using only facts stated in the result. If the result is "
    "inconclusive, missing the relevant data, or the condition is not met, answer notify=false."
)


async def evaluate(llm: Any, condition: str, answer: str) -> Tuple[bool, str]:
    from langchain_core.messages import HumanMessage, SystemMessage

    verdict = await llm.with_structured_output(Verdict).ainvoke([
        SystemMessage(content=JUDGE_PROMPT),
        HumanMessage(content=f"CONDITION: {condition}\n\nRESULT:\n{answer[:6000]}"),
    ])
    if isinstance(verdict, dict):
        verdict = Verdict.model_validate(verdict)
    return verdict.notify, verdict.reason


def _default_agent(session_id: str, services: Any) -> Any:
    from ..agent import Web3ResearchAgent
    from ..memory import SessionManager

    return Web3ResearchAgent(
        session_id=session_id, sessions=SessionManager(max_sessions=2, ttl_hours=1),   # in-memory only
        retrieval=services.retrieval, cache=services.cache,
    )


async def run_rule(rule: Dict[str, Any], services: Any, make_agent: Callable[[str, Any], Any] = _default_agent,
                   judge_llm: Any = None) -> str:
    """Returns ``"notified"``, ``"skipped"`` (condition not met) or ``"failed"``."""
    repo = services.alerts_repo
    try:
        wallet = services.auth_repo.get_wallet(rule["wallet_id"])
        if wallet is None:
            return "failed"
        session_id = f"alert-{uuid.uuid4().hex[:16]}"
        request = ResearchRequest(
            query=rule["query_text"], address=wallet["address"], session_id=session_id, wallet_id=wallet["id"],
            wallet_address=wallet["address"], memory_enabled=bool(wallet["settings"].get("memory_enabled", True)),
            store_memory=False,
        )
        result = await make_agent(session_id, services).research(request)
        if not result.get("success"):
            repo.record_result(rule["id"], str(result.get("error") or "Research failed"))
            return "failed"

        answer = str(result.get("result") or "")
        notify, reason = True, ""
        if rule.get("condition_text"):
            try:
                llm = judge_llm if judge_llm is not None else _judge_model(services)
                notify, reason = await evaluate(llm, rule["condition_text"], answer)
            except Exception as exc:  # noqa: BLE001 - fail open: better a noisy alert than a missed one
                logger.warning("Alert condition could not be evaluated (%s); notifying anyway", exc)
                reason = "Condition could not be evaluated, so this result is shown anyway."
        repo.record_result(rule["id"], None)
        if not notify:
            return "skipped"

        summary = answer[:INBOX_SUMMARY_CHARS]
        if reason:
            summary = f"_{reason}_\n\n{summary}"
        repo.add_inbox(rule["wallet_id"], rule["id"], rule["name"], summary, {
            "query": rule["query_text"], "condition": rule.get("condition_text"),
            "sources": result.get("data_sources_used", []), "intent": result.get("query_intent"),
        })
        return "notified"
    except Exception as exc:  # noqa: BLE001
        logger.exception("Alert rule %s failed", rule.get("id"))
        try:
            repo.record_result(rule["id"], f"{type(exc).__name__}: {exc}")
        except Exception:  # noqa: BLE001
            pass
        return "failed"


def _judge_model(services: Any) -> Any:
    from ..agent.llm import planner_llm

    return planner_llm(services.settings)


def run_due(services: Any, limit: Optional[int] = None, make_agent: Callable[[str, Any], Any] = _default_agent,
            judge_llm: Any = None) -> Dict[str, int]:
    """Claim and run due rules one after another. Returns counts by outcome plus ``claimed``."""
    settings = services.settings
    rules = services.alerts_repo.claim_due(limit or settings.alert_batch_size, settings.max_alert_runs_per_day)
    counts: Dict[str, int] = {"claimed": len(rules), "notified": 0, "skipped": 0, "failed": 0}
    for rule in rules:
        outcome = asyncio.run(run_rule(rule, services, make_agent, judge_llm))
        counts[outcome] += 1
    return counts


def main() -> int:
    from ..services import get_services

    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    services = get_services()
    if services.alerts_repo is None:
        print("DATABASE_URL is not set (or the database is unreachable)", file=sys.stderr)
        return 1
    print(run_due(services))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
