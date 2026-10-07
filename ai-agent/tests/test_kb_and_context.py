"""Knowledge base chunking/ingest/formatting, and the watchlist + portfolio context service."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from airaa import context_service
from airaa.config import Settings
from airaa.context_service import ContextError, ContextService, build_portfolio_summary
from airaa.kb import chunk_text
from airaa.kb import service as kb_service
from airaa.kb.ingest import API_DOCS, html_to_text, load_path, openapi_documents
from airaa.kb.service import KnowledgeBase

from .helpers import FakeEmbedder

ADDRESS = "0x" + "ab" * 20


# ----------------------------------------------------------------------- chunking
def test_chunk_text_respects_size_and_keeps_everything():
    paragraphs = [f"Paragraph {i}. " + "word " * 120 for i in range(30)]
    chunks = chunk_text("\n\n".join(paragraphs), size=1200, overlap=150)
    assert len(chunks) > 5 and all(len(c) <= 1200 + 200 for c in chunks)          # size plus the carried overlap
    joined = "\n".join(chunks)
    assert all(f"Paragraph {i}." in joined for i in range(30))                    # nothing dropped


def test_chunk_text_overlaps_and_splits_huge_paragraphs():
    chunks = chunk_text("alpha. " * 1000, size=500, overlap=100)
    assert len(chunks) > 5 and all(len(c) <= 700 for c in chunks)
    assert chunk_text("") == [] and chunk_text("   \n\n  ") == [] and chunk_text("short") == ["short"]


# ----------------------------------------------------------------------- loaders
def test_real_defillama_spec_becomes_documents_per_tag():
    docs = load_path(API_DOCS / "defillama-api.json")
    assert len(docs) >= 5
    urls = [d[0] for d in docs]
    assert len(set(urls)) == len(urls) and all(u.startswith("https://api-docs.defillama.com/#") for u in urls)
    text = "\n".join(d[2] for d in docs)
    assert "GET https://api.llama.fi/protocols" in text and "Parameter protocol (path, required)" in text


def test_openapi_documents_minimal():
    spec = {"info": {"title": "T"}, "servers": [{"url": "https://x"}], "paths": {
        "/a": {"get": {"tags": ["Alpha"], "summary": "Do A", "parameters": [{"name": "q", "in": "query", "description": "query"}],
                       "responses": {"200": {"description": "ok"}}}}}}
    [(url, title, text)] = openapi_documents(spec, "https://docs")
    assert url == "https://docs#alpha" and title == "T: Alpha"
    assert "GET https://x/a" in text and "Do A" in text and "Returns: ok" in text


def test_html_to_text_drops_chrome_and_keeps_content():
    title, text = html_to_text("<html><head><title>Aave Docs</title><style>x{}</style></head><body><nav>menu</nav>"
                               "<h1>Pools</h1><p>Supply assets to earn yield.</p><script>evil()</script></body></html>")
    assert title == "Aave Docs" and "Supply assets to earn yield." in text and "menu" not in text and "evil" not in text


# ----------------------------------------------------------------------- ingest
class FakeKbRepo:
    def __init__(self):
        self.docs = {}

    def get_document(self, url):
        d = self.docs.get(url)
        return {"id": "1", "content_hash": d["hash"]} if d else None

    def replace_document(self, source, url, title, content_hash, chunks):
        self.docs[url] = {"hash": content_hash, "chunks": chunks, "title": title, "source": source}
        return "1"


def test_ingest_is_incremental():
    embedder = FakeEmbedder()
    kb = KnowledgeBase(FakeKbRepo(), embedder, Settings(gemini_api_key="t"))
    text = "Aave lets users supply and borrow assets.\n\n" * 3
    assert kb.ingest_document("docs", "https://d/aave", "Aave", text) == "added"
    calls = len(embedder.calls)
    assert kb.ingest_document("docs", "https://d/aave", "Aave", text) == "unchanged"
    assert len(embedder.calls) == calls                                           # no embedding call for unchanged text
    assert kb.ingest_document("docs", "https://d/aave", "Aave", text + "More.") == "updated"
    assert kb.ingest_document("docs", "https://d/empty", "Empty", "  ") == "empty"
    stored = kb.repo.docs["https://d/aave"]["chunks"][0]
    assert stored[0] == 0 and stored[3]["url"] == "https://d/aave" and stored[3]["title"] == "Aave"


class FakeSearchRepo:
    def __init__(self, rows):
        self.rows = rows

    def search(self, embedding, query_text, k):
        return self.rows[:k]


def test_search_filters_weak_matches_and_formats_citations():
    rows = [{"id": "1", "content": "Aave V3 supports e-mode.", "title": "Aave", "url": "https://d/aave", "similarity": 0.8},
            {"id": "2", "content": "Unrelated text", "title": "Other", "url": "https://d/other", "similarity": 0.2},
            {"id": "3", "content": "Aave risk parameters.", "title": "Aave", "url": "https://d/aave", "similarity": 0.7}]
    kb = KnowledgeBase(FakeSearchRepo(rows), FakeEmbedder(), Settings(gemini_api_key="t", kb_min_similarity=0.5, kb_top_k=4))
    hits = asyncio.run(kb.search("aave e-mode"))
    assert [h["id"] for h in hits] == ["1", "3"]
    block = kb_service.format_block(hits)
    assert block.startswith("REFERENCE DOCUMENTATION") and "[1] Aave (https://d/aave)" in block and "[2]" not in block
    assert kb_service.citations(hits) == [{"title": "Aave", "url": "https://d/aave", "similarity": 0.8}]
    assert kb_service.format_block([]) == ""


# ----------------------------------------------------------------------- portfolio
def etherscan(result):
    return {"success": True, "data": {"result": result}}


def test_portfolio_summary_from_etherscan_data():
    transfers = [
        {"tokenSymbol": "USDC", "tokenDecimal": "6", "value": "2500000000", "to": ADDRESS, "from": "0x" + "cd" * 20, "contractAddress": "0xusdc"},
        {"tokenSymbol": "USDC", "tokenDecimal": "6", "value": "500000000", "to": "0x" + "cd" * 20, "from": ADDRESS, "contractAddress": "0xusdc"},
        {"tokenSymbol": "AAVE", "tokenDecimal": "18", "value": str(3 * 10**18), "to": ADDRESS.upper().replace("0X", "0x"), "from": "0x" + "ee" * 20},
    ]
    built = build_portfolio_summary("ethereum", ADDRESS, etherscan(str(2 * 10**18)), etherscan(transfers))
    assert "native balance 2.0000 ETH" in built["summary"]
    assert "USDC +2,000.00 (2 transfers)" in built["summary"] and "AAVE +3.00" in built["summary"]
    assert "not a balance" in built["summary"]                                    # token flow must never read as a balance
    assert built["holdings"]["native"] == {"symbol": "ETH", "balance": 2.0}


def test_portfolio_summary_handles_missing_data_and_chain_native_tokens():
    with pytest.raises(ContextError):
        build_portfolio_summary("ethereum", ADDRESS, {"success": False}, {"success": False})
    only_native = build_portfolio_summary("bsc", ADDRESS, etherscan(str(10**18)), {"success": False})
    assert "1.0000 BNB" in only_native["summary"] and only_native["holdings"]["tokens"] == []
    with pytest.raises(ContextError):          # malformed rows (and a non-dict one) must be skipped, leaving nothing to say
        build_portfolio_summary("polygon", ADDRESS, etherscan("12abc"), etherscan([{"tokenDecimal": "x", "value": "y"}, "bad"]))


# ----------------------------------------------------------------------- watchlist
class FakeContextRepo:
    def __init__(self):
        self.items = []

    def count_watch(self, wallet_id):
        return len(self.items)

    def list_watch(self, wallet_id):
        return list(self.items)

    def add_watch(self, wallet_id, entity_type, entity_id, note, embedding):
        self.items = [i for i in self.items if (i["entity_type"], i["entity_id"]) != (entity_type, entity_id)]
        item = {"id": str(len(self.items) + 1), "entity_type": entity_type, "entity_id": entity_id, "note": note, "has_vector": embedding is not None}
        self.items.append(item)
        return item


@pytest.fixture
def ctx():
    return ContextService(FakeContextRepo(), FakeEmbedder(), Settings(gemini_api_key="t", max_watchlist_items=3))


def test_watchlist_normalises_and_validates(ctx):
    item = ctx.add_watch("w1", " TOKEN ", " ETH ", "  core holding  ")
    assert item["entity_type"] == "token" and item["entity_id"] == "eth" and item["note"] == "core holding" and item["has_vector"]
    for bad in [("coin", "eth"), ("token", ""), ("token", "ETH!!"), ("token", "x" * 81)]:
        with pytest.raises(ContextError):
            ctx.add_watch("w1", *bad)


def test_watchlist_limit_allows_updates_but_not_growth(ctx):
    for sym in ("eth", "btc", "sol"):
        ctx.add_watch("w1", "token", sym)
    with pytest.raises(ContextError, match="full"):
        ctx.add_watch("w1", "token", "avax")
    assert ctx.add_watch("w1", "token", "eth", "updated note")["note"] == "updated note"      # editing an existing item is fine


def test_watchlist_works_without_embeddings():
    class Down(FakeEmbedder):
        def embed_one_sync(self, *a, **k):
            raise RuntimeError("no key")

    svc = ContextService(FakeContextRepo(), Down(), Settings(gemini_api_key="t"))
    assert svc.add_watch("w1", "protocol", "aave")["has_vector"] is False


def test_context_block_formatting():
    now = datetime.now(timezone.utc)
    block = context_service.format_block({
        "watchlist": [{"entity_type": "token", "entity_id": "eth"}, {"entity_type": "protocol", "entity_id": "aave"}],
        "close": [{"entity_id": "eth", "note": "core holding"}],
        "snapshots": [{"summary": "Wallet 0xab on ethereum: native balance 2 ETH.", "fetched_at": (now - timedelta(days=3)).isoformat()}],
    }, now)
    assert "tokens: ETH" in block and "protocols: aave" in block and "eth: core holding" in block
    assert "PORTFOLIO SNAPSHOT (3 day(s) old)" in block and "never as live data" in block
    assert context_service.format_block({"watchlist": [], "close": [], "snapshots": []}) == ""
