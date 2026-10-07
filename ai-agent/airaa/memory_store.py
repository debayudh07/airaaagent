"""Long-term memory: what the agent remembers about a wallet across conversations.

Write path (after each answered turn, off the request path):
    extract durable facts/preferences/findings with a small LLM -> embed -> merge near-duplicates -> insert.
Read path (before planning):
    embed the question -> nearest memories -> re-rank by similarity, recency and importance -> prompt block.
"""
from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from .config import Settings, get_settings

logger = logging.getLogger(__name__)

MAX_MEMORIES_PER_WALLET = 500
_W_SIMILARITY, _W_RECENCY, _W_IMPORTANCE = 0.65, 0.20, 0.15


class MemoryItem(BaseModel):
    kind: Literal["fact", "preference", "finding", "summary"] = Field(
        description="fact = something true about the user; preference = how they like answers or what they favour; "
                    "finding = a durable research conclusion they reached; summary = a short recap of a long topic.")
    content: str = Field(description="One self-contained sentence, third person ('The user ...'). Never include secrets.")
    importance: float = Field(default=0.5, description="0 trivial .. 1 essential to remember long-term.")


class MemoryExtraction(BaseModel):
    memories: List[MemoryItem] = Field(
        default_factory=list,
        description="Durable things worth remembering. Empty for small talk, one-off lookups and anything transient.")


EXTRACTION_PROMPT = (
    "You maintain long-term memory for a crypto research assistant. From the exchange below, extract only "
    "information that will still matter in future conversations: the user's holdings or strategy, chains and protocols "
    "they follow, risk tolerance, preferred answer style, and durable conclusions of their research. "
    "Skip prices, market data and anything that goes stale within days. Skip greetings and one-off questions. "
    "Never store private keys, seed phrases, passwords or API keys. Write each memory as one standalone sentence. "
    "Return an empty list if nothing qualifies."
)


def rank(rows: List[Dict[str, Any]], half_life_days: float, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Score = 0.65 similarity + 0.20 recency (exponential decay) + 0.15 importance. Pinned memories get a boost."""
    now = now or datetime.now(timezone.utc)
    scored = []
    for row in rows:
        stamp = row.get("last_accessed") or row.get("created_at")
        if isinstance(stamp, str):
            stamp = datetime.fromisoformat(stamp)
        age_days = max((now - stamp).total_seconds() / 86400, 0.0) if stamp else 0.0
        recency = math.pow(0.5, age_days / max(half_life_days, 0.1))
        score = _W_SIMILARITY * row["similarity"] + _W_RECENCY * recency + _W_IMPORTANCE * row["importance"]
        if row.get("pinned"):
            score += 0.2
        scored.append({**row, "score": round(score, 4)})
    return sorted(scored, key=lambda r: r["score"], reverse=True)


def format_block(memories: List[Dict[str, Any]]) -> str:
    if not memories:
        return ""
    lines = "\n".join(f"- {m['content']}" for m in memories)
    return ("WHAT YOU REMEMBER ABOUT THIS USER (from earlier conversations; use it to personalise, do not recite it, "
            "and never treat it as live data):\n" + lines)


class MemoryService:
    def __init__(self, repo: Any, embedder: Any, settings: Optional[Settings] = None) -> None:
        self.repo, self.embedder = repo, embedder
        self.settings = settings or get_settings()

    # ---- read ----------------------------------------------------------
    async def recall(self, wallet_id: str, query: str, vector: Optional[List[float]] = None) -> List[Dict[str, Any]]:
        cfg = self.settings
        vector = vector or await self.embedder.aembed_one(query, "query")
        rows = await asyncio.to_thread(
            self.repo.search, wallet_id, vector, max(cfg.memory_top_k * 3, 8), cfg.memory_min_similarity)
        top = rank(rows, cfg.memory_half_life_days)[:cfg.memory_top_k]
        if top:
            await asyncio.to_thread(self.repo.touch, wallet_id, [m["id"] for m in top])
        return top

    # ---- write ---------------------------------------------------------
    async def extract(self, llm: Any, user_text: str, ai_text: str) -> List[MemoryItem]:
        from langchain_core.messages import HumanMessage, SystemMessage

        exchange = f"User: {user_text[:1500]}\n\nAssistant: {ai_text[:2500]}"
        result = await llm.with_structured_output(MemoryExtraction).ainvoke(
            [SystemMessage(content=EXTRACTION_PROMPT), HumanMessage(content=exchange)])
        if isinstance(result, dict):
            result = MemoryExtraction.model_validate(result)
        return list(result.memories)[:5]

    async def store(self, wallet_id: str, conversation_id: Optional[str], items: List[MemoryItem]) -> int:
        """Embed and save. A near-duplicate of an existing memory is merged instead of inserted. Returns new rows."""
        items = [i for i in items if i.content and i.content.strip()]
        if not items:
            return 0
        vectors = await self.embedder.aembed([i.content for i in items], "document")
        inserted = 0
        for item, vector in zip(items, vectors):
            importance = min(max(float(item.importance), 0.0), 1.0)
            content = item.content.strip()[:2000]
            near = await asyncio.to_thread(self.repo.search, wallet_id, vector, 1, self.settings.memory_dedup_similarity)
            if near:
                await asyncio.to_thread(self.repo.merge, wallet_id, near[0]["id"], importance, content, vector)
                continue
            await asyncio.to_thread(self.repo.insert, wallet_id, item.kind, content, importance, vector, conversation_id)
            inserted += 1
        if inserted:
            await asyncio.to_thread(self.repo.prune, wallet_id, MAX_MEMORIES_PER_WALLET)
        return inserted

    async def remember_turn(self, llm: Any, wallet_id: str, conversation_id: Optional[str], user_text: str, ai_text: str) -> int:
        try:
            items = await self.extract(llm, user_text, ai_text)
            return await self.store(wallet_id, conversation_id, items)
        except Exception as exc:  # noqa: BLE001 - memory is best-effort and must never affect the answer
            logger.warning("Could not update long-term memory: %s", exc)
            return 0

    # ---- dashboard (embedding is only needed when the text changes) ---
    async def add_manual(self, wallet_id: str, kind: str, content: str, importance: float = 0.7, pinned: bool = False) -> str:
        vector = await self.embedder.aembed_one(content, "document")
        return await asyncio.to_thread(self.repo.insert, wallet_id, kind, content.strip()[:2000], importance, vector, None, pinned)

    async def edit(self, wallet_id: str, memory_id: str, content: Optional[str] = None, importance: Optional[float] = None,
                   pinned: Optional[bool] = None) -> Optional[Dict[str, Any]]:
        vector = await self.embedder.aembed_one(content, "document") if content else None
        return await asyncio.to_thread(
            self.repo.update, wallet_id, memory_id, content.strip()[:2000] if content else None, importance, pinned, vector)
