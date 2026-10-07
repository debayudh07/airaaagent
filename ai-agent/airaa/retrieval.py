"""Everything the agent pulls in about *this user and this question* before planning, and saves afterwards.

    build()    -> long-term memories + watchlist/portfolio + knowledge-base passages, fetched concurrently,
                  each failing open (a slow or broken source is skipped, never fatal).
    remember() -> fire-and-forget memory extraction after the answer is sent.
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from . import context_service, memory_store
from .config import Settings, get_settings
from .kb import service as kb_service
from .schemas import ResearchRequest

logger = logging.getLogger(__name__)

BUILD_TIMEOUT_SECONDS = 6.0
_background = ThreadPoolExecutor(max_workers=2, thread_name_prefix="airaa-memory")


@dataclass
class Retrieved:
    summary: str = ""                 # short text for the planner
    blocks: str = ""                  # full prompt blocks for the synthesis model
    citations: List[Dict[str, Any]] = field(default_factory=list)
    used: Dict[str, int] = field(default_factory=dict)   # counts per source, for the UI/trace


class Retrieval:
    def __init__(self, embedder: Any, memories: Any = None, context: Any = None, kb: Any = None,
                 settings: Optional[Settings] = None) -> None:
        self.embedder, self.memories, self.context, self.kb = embedder, memories, context, kb
        self.settings = settings or get_settings()

    async def build(self, request: ResearchRequest) -> Retrieved:
        wallet = request.wallet_id
        wants_memory = bool(wallet and request.memory_enabled and self.memories)
        wants_context = bool(wallet and self.context)
        if not (wants_memory or wants_context or self.kb):
            return Retrieved()
        try:
            return await asyncio.wait_for(self._build(request, wants_memory, wants_context), BUILD_TIMEOUT_SECONDS)
        except Exception as exc:  # noqa: BLE001 - includes timeouts; personalisation is optional
            logger.warning("Retrieval skipped: %s", exc)
            return Retrieved()

    async def _build(self, request: ResearchRequest, wants_memory: bool, wants_context: bool) -> Retrieved:
        vector = None
        if self.embedder is not None:
            try:
                vector = await self.embedder.aembed_one(request.query, "query")  # one embedding shared by all sources
            except Exception as exc:  # noqa: BLE001
                logger.warning("Query embedding failed (%s); skipping semantic retrieval", exc)

        async def memory():
            return await self.memories.recall(request.wallet_id, request.query, vector) if vector else []

        async def personal():
            return await self.context.relevant(request.wallet_id, vector)

        async def docs():
            return await self.kb.search(request.query, vector) if vector else []

        tasks = {
            "memory": memory() if wants_memory else None,
            "personal": personal() if wants_context else None,
            "kb": docs() if self.kb else None,
        }
        names = [n for n, t in tasks.items() if t is not None]
        outcomes = await asyncio.gather(*(tasks[n] for n in names), return_exceptions=True)
        got: Dict[str, Any] = {}
        for name, outcome in zip(names, outcomes):
            if isinstance(outcome, Exception):
                logger.warning("Retrieval source %s failed: %s", name, outcome)
            else:
                got[name] = outcome

        memories = got.get("memory") or []
        personal_data = got.get("personal") or {}
        passages = got.get("kb") or []
        blocks = [b for b in (
            memory_store.format_block(memories),
            context_service.format_block(personal_data),
            kb_service.format_block(passages),
        ) if b]

        summary_parts = [f"- {m['content']}" for m in memories[:4]]
        watch = personal_data.get("watchlist") or []
        if watch:
            summary_parts.append("- Watchlist: " + ", ".join(w["entity_id"] for w in watch[:12]))
        return Retrieved(
            summary="\n".join(summary_parts),
            blocks="\n\n".join(blocks),
            citations=kb_service.citations(passages),
            used={"memories": len(memories), "watchlist": len(watch), "snapshots": len(personal_data.get("snapshots") or []),
                  "documents": len(passages)},
        )

    def remember(self, request: ResearchRequest, answer: str, llm_factory: Any) -> None:
        """Extract and store memories in a worker thread so the response is never delayed."""
        if not (request.wallet_id and request.memory_enabled and request.store_memory and self.memories):
            return

        def work() -> None:
            async def go() -> None:
                await self.memories.remember_turn(llm_factory(), request.wallet_id, request.session_id, request.query, answer)
            try:
                asyncio.run(go())
            except Exception:  # noqa: BLE001
                logger.exception("Background memory update crashed")

        _background.submit(work)
