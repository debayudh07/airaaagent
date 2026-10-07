"""Long-term memory: ranking, recall, extraction, dedup, and the retrieval wrapper that never breaks a request."""
from __future__ import annotations

import asyncio
import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pytest

from airaa import memory_store
from airaa.config import Settings
from airaa.memory_store import MemoryExtraction, MemoryItem, MemoryService, format_block, rank
from airaa.retrieval import Retrieval
from airaa.schemas import ResearchRequest

from .conftest import FakeStructured
from .helpers import FakeEmbedder

NOW = datetime.now(timezone.utc)


def row(content, similarity, importance=0.5, age_days=0.0, pinned=False, id=None):
    return {"id": id or str(uuid.uuid4()), "content": content, "similarity": similarity, "importance": importance,
            "pinned": pinned, "created_at": (NOW - timedelta(days=age_days)).isoformat(), "last_accessed": None}


# ----------------------------------------------------------------------- ranking
def test_rank_blends_similarity_recency_and_importance():
    rows = [row("old but very similar", 0.9, age_days=400), row("fresh and similar", 0.85, age_days=0),
            row("fresh, less similar", 0.5, age_days=0)]
    ordered = [r["content"] for r in rank(rows, half_life_days=30, now=NOW)]
    # recency breaks near-ties in similarity, but a year-old strong match still beats a fresh weak one
    assert ordered == ["fresh and similar", "old but very similar", "fresh, less similar"]


def test_rank_recency_decays_by_half_life():
    fresh, month, year = (rank([row("x", 0.5, importance=0, age_days=d)], 30, NOW)[0]["score"] for d in (0, 30, 365))
    assert math.isclose(fresh - month, memory_store._W_RECENCY * 0.5, abs_tol=0.01)  # one half-life halves the recency term
    assert month > year


def test_pinned_and_important_memories_rise():
    rows = [row("plain", 0.6), row("important", 0.6, importance=1.0), row("pinned", 0.6, pinned=True)]
    ordered = [r["content"] for r in rank(rows, 30, NOW)]
    assert ordered[0] == "pinned" and ordered.index("important") < ordered.index("plain")


def test_format_block():
    assert format_block([]) == ""
    block = format_block([{"content": "The user holds ETH."}, {"content": "Prefers short answers."}])
    assert "- The user holds ETH." in block and "never treat it as live data" in block


# ----------------------------------------------------------------------- repo fake
class FakeMemoryRepo:
    def __init__(self):
        self.rows: Dict[str, Dict[str, Any]] = {}
        self.touched: List[str] = []
        self.pruned = None

    @staticmethod
    def _cos(a, b):
        return sum(x * y for x, y in zip(a, b))

    def search(self, wallet_id, embedding, k, min_similarity):
        hits = [dict(r, similarity=self._cos(r["embedding"], embedding)) for r in self.rows.values() if r["wallet_id"] == wallet_id]
        hits = [h for h in hits if h["similarity"] >= min_similarity]
        return sorted(hits, key=lambda h: -h["similarity"])[:k]

    def insert(self, wallet_id, kind, content, importance, embedding, conversation_id=None, pinned=False):
        rid = str(uuid.uuid4())
        self.rows[rid] = {"id": rid, "wallet_id": wallet_id, "kind": kind, "content": content, "importance": importance,
                          "embedding": embedding, "pinned": pinned, "created_at": NOW.isoformat(), "last_accessed": None}
        return rid

    def merge(self, wallet_id, memory_id, importance, content, embedding):
        r = self.rows[memory_id]
        r.update(content=content, embedding=embedding, importance=max(r["importance"], importance))

    def touch(self, wallet_id, ids):
        self.touched += list(ids)

    def prune(self, wallet_id, keep):
        self.pruned = keep
        return 0


@pytest.fixture
def service():
    cfg = Settings(gemini_api_key="t", memory_min_similarity=0.3, memory_top_k=3, memory_dedup_similarity=0.8)
    return MemoryService(FakeMemoryRepo(), FakeEmbedder(), cfg)


def test_store_then_recall_finds_the_relevant_memory(service):
    items = [MemoryItem(kind="fact", content="The user holds a large ETH position on Arbitrum", importance=0.9),
             MemoryItem(kind="preference", content="The user prefers concise bullet point answers", importance=0.6)]
    assert asyncio.run(service.store("w1", "conv-1", items)) == 2

    recalled = asyncio.run(service.recall("w1", "what is happening with my ETH on Arbitrum"))
    assert recalled and recalled[0]["content"].startswith("The user holds a large ETH")
    assert service.repo.touched == [recalled[0]["id"]] or recalled[0]["id"] in service.repo.touched
    assert asyncio.run(service.recall("someone-else", "ETH Arbitrum")) == []          # memories are per wallet


def test_near_duplicates_are_merged_not_inserted(service):
    first = MemoryItem(kind="fact", content="The user holds ETH on Arbitrum", importance=0.4)
    assert asyncio.run(service.store("w1", None, [first])) == 1
    second = MemoryItem(kind="fact", content="The user holds ETH on Arbitrum", importance=0.9)
    assert asyncio.run(service.store("w1", None, [second])) == 0                       # merged
    rows = list(service.repo.rows.values())
    assert len(rows) == 1 and rows[0]["importance"] == 0.9


def test_store_ignores_blank_items_and_clamps_importance(service):
    items = [MemoryItem(kind="fact", content="   ", importance=0.5), MemoryItem(kind="fact", content="Likes DeFi yields", importance=7)]
    assert asyncio.run(service.store("w1", None, items)) == 1
    assert list(service.repo.rows.values())[0]["importance"] == 1.0
    assert service.repo.pruned == memory_store.MAX_MEMORIES_PER_WALLET


class FakeLLM:
    def __init__(self, result=None, error=None):
        self.runner = FakeStructured(result, error)

    def with_structured_output(self, schema):
        assert schema is MemoryExtraction
        return self.runner


def test_remember_turn_extracts_and_stores(service):
    llm = FakeLLM(MemoryExtraction(memories=[MemoryItem(kind="preference", content="The user is risk averse", importance=0.8)]))
    assert asyncio.run(service.remember_turn(llm, "w1", "conv-1", "I hate risk", "Understood.")) == 1
    prompt = llm.runner.calls[0]
    assert "I hate risk" in prompt[1].content and "Never store private keys" in prompt[0].content


def test_remember_turn_never_raises(service):
    assert asyncio.run(service.remember_turn(FakeLLM(error=RuntimeError("quota")), "w1", None, "q", "a")) == 0
    assert service.repo.rows == {}


# ----------------------------------------------------------------------- retrieval wrapper
class StubSource:
    def __init__(self, value=None, error=None, delay=0.0):
        self.value, self.error, self.delay = value, error, delay

    async def recall(self, wallet_id, query, vector=None):
        return await self._go()

    async def relevant(self, wallet_id, vector):
        return await self._go()

    async def search(self, query, vector=None):
        return await self._go()

    async def _go(self):
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return self.value


def request(**kw):
    return ResearchRequest(query="eth outlook", session_id="session-12345", wallet_id="w1", **kw)


def test_retrieval_combines_all_sources():
    memories = StubSource([{"id": "1", "content": "The user holds ETH."}])
    context = StubSource({"watchlist": [{"entity_type": "token", "entity_id": "eth", "note": None}], "close": [], "snapshots": []})
    kb = StubSource([{"content": "Aave is a lending protocol.", "title": "Aave docs", "url": "https://docs/aave", "similarity": 0.8}])
    got = asyncio.run(Retrieval(FakeEmbedder(), memories, context, kb).build(request()))
    assert "The user holds ETH." in got.blocks and "USER WATCHLIST" in got.blocks and "REFERENCE DOCUMENTATION" in got.blocks
    assert "Watchlist: eth" in got.summary and got.used == {"memories": 1, "watchlist": 1, "snapshots": 0, "documents": 1}
    assert got.citations == [{"title": "Aave docs", "url": "https://docs/aave", "similarity": 0.8}]


def test_a_failing_source_is_skipped_not_fatal():
    memories = StubSource(error=RuntimeError("db down"))
    kb = StubSource([{"content": "text", "title": "T", "url": "u", "similarity": 0.9}])
    got = asyncio.run(Retrieval(FakeEmbedder(), memories, None, kb).build(request()))
    assert "REFERENCE DOCUMENTATION" in got.blocks and got.used["memories"] == 0


def test_retrieval_times_out_open(monkeypatch):
    monkeypatch.setattr("airaa.retrieval.BUILD_TIMEOUT_SECONDS", 0.05)
    got = asyncio.run(Retrieval(FakeEmbedder(), StubSource([], delay=1.0), None, None).build(request()))
    assert got.blocks == "" and got.summary == ""


def test_embedding_failure_degrades_to_no_semantic_retrieval():
    class Broken(FakeEmbedder):
        async def aembed_one(self, *a, **k):
            raise RuntimeError("quota")

    got = asyncio.run(Retrieval(Broken(), StubSource([{"id": "1", "content": "x"}]), None, None).build(request()))
    assert got.blocks == ""


def test_memory_is_skipped_for_guests_and_opt_outs():
    memories = StubSource([{"id": "1", "content": "secret"}])
    guest = ResearchRequest(query="q", session_id="session-12345")
    assert asyncio.run(Retrieval(FakeEmbedder(), memories, None, None).build(guest)).blocks == ""
    assert asyncio.run(Retrieval(FakeEmbedder(), memories, None, None).build(request(memory_enabled=False))).blocks == ""


def test_remember_is_gated_and_runs_in_the_background():
    done = []

    class Memories:
        async def remember_turn(self, llm, wallet_id, conversation_id, user_text, ai_text):
            done.append((wallet_id, conversation_id, user_text, ai_text))

    r = Retrieval(FakeEmbedder(), Memories(), None, None)
    r.remember(ResearchRequest(query="q", session_id="session-12345"), "a", lambda: None)                 # guest: nothing
    r.remember(request(store_memory=False), "a", lambda: None)                                            # alert run: nothing
    r.remember(request(memory_enabled=False), "a", lambda: None)                                          # opted out: nothing
    r.remember(request(), "the answer", lambda: "llm")
    from airaa import retrieval

    retrieval._background.shutdown(wait=True)
    retrieval._background = retrieval.ThreadPoolExecutor(max_workers=2, thread_name_prefix="airaa-memory")
    assert done == [("w1", "session-12345", "eth outlook", "the answer")]
