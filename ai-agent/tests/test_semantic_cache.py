"""Semantic tool cache: what is cacheable, exact vs semantic hits, and the executor integration."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import pytest

from airaa.agent.executor import run_tools
from airaa.cache import ToolCache
from airaa.config import Settings
from airaa.schemas import Entities, ResearchRequest

from .conftest import FakeTool
from .helpers import FakeEmbedder

ARGS = {"query": "price of ETH", "symbols": ["ETH"]}
OK = {"success": True, "source": "coinmarketcap", "data": {"price": 3000}}


class FakeCacheRepo:
    def __init__(self):
        self.entries: Dict[str, Dict[str, Any]] = {}
        self.fail = False

    def get_exact(self, key_hash):
        if self.fail:
            raise RuntimeError("db down")
        e = self.entries.get(key_hash)
        return {"result": e["result"], "age_seconds": 5} if e else None

    def get_semantic(self, tool, params_hash, embedding, threshold):
        best: Optional[Dict[str, Any]] = None
        for e in self.entries.values():
            if e["tool"] == tool and e["params_hash"] == params_hash and e["embedding"] is not None:
                sim = sum(a * b for a, b in zip(e["embedding"], embedding))
                if sim >= threshold and (best is None or sim > best["similarity"]):
                    best = {"result": e["result"], "similarity": sim, "age_seconds": 9}
        return best

    def put(self, key_hash, tool, params_hash, query_text, embedding, result, ttl_seconds):
        self.entries[key_hash] = {"tool": tool, "params_hash": params_hash, "embedding": embedding, "result": result, "ttl": ttl_seconds}


@pytest.fixture
def cache():
    return ToolCache(FakeCacheRepo(), FakeEmbedder(), Settings(gemini_api_key="t", cache_similarity=0.9))


def lookup(cache, tool, args):
    return asyncio.run(cache.lookup(tool, args))


def store(cache, tool, args, result=OK):
    hit, ticket = lookup(cache, tool, args)
    assert hit is None
    asyncio.run(cache.store(ticket, result))


def test_only_public_tools_are_cacheable(cache):
    assert cache.ttl("coinmarketcap_tool") == 60 and cache.ttl("defillama_tool") == 600
    assert cache.ttl("etherscan_tool") is None and cache.ttl("read_url_tool") is None
    hit, ticket = lookup(cache, "etherscan_tool", {"query": "balance", "address": "0x" + "ab" * 20})
    assert hit is None and ticket is None


def test_exact_hit_after_store_and_ttl_is_passed_through(cache):
    store(cache, "coinmarketcap_tool", ARGS)
    hit, _ = lookup(cache, "coinmarketcap_tool", ARGS)
    assert hit["match"] == "exact" and hit["result"] == OK and hit["age_seconds"] == 5
    assert list(cache.repo.entries.values())[0]["ttl"] == 60


def test_equivalent_arguments_share_an_entry(cache):
    store(cache, "coinmarketcap_tool", {"query": "Price of ETH", "symbols": ["ETH", "BTC"]})
    hit, _ = lookup(cache, "coinmarketcap_tool", {"query": "price of eth  ", "symbols": ["BTC", "ETH"]})
    assert hit is not None                                   # case, whitespace and list order do not matter


def test_semantic_hit_for_a_near_identical_question(cache):
    store(cache, "coinmarketcap_tool", {"query": "what is the price of ETH right now", "symbols": ["ETH"]})
    hit, _ = lookup(cache, "coinmarketcap_tool", {"query": "what is the price of ETH right now please", "symbols": ["ETH"]})
    assert hit["match"] == "semantic" and hit["similarity"] >= 0.9


def test_different_structured_arguments_never_match(cache):
    store(cache, "coinmarketcap_tool", {"query": "price", "symbols": ["ETH"]})
    assert lookup(cache, "coinmarketcap_tool", {"query": "price", "symbols": ["BTC"]})[0] is None   # same words, other coin
    assert lookup(cache, "coingecko_tool", {"query": "price", "symbols": ["ETH"]})[0] is None        # other tool


def test_unrelated_questions_do_not_match_semantically(cache):
    store(cache, "defillama_tool", {"query": "aave total value locked", "protocols": ["aave"]})
    assert lookup(cache, "defillama_tool", {"query": "compare yields stablecoin pools", "protocols": ["aave"]})[0] is None


def test_search_text_is_fuzzy_for_news_and_web_search(cache):
    store(cache, "web_search_tool", {"query": "when is the fusaka upgrade", "search": "ethereum fusaka upgrade date"})
    hit, _ = lookup(cache, "web_search_tool", {"query": "when is the fusaka upgrade", "search": "ethereum fusaka upgrade date today"})
    assert hit is not None and hit["match"] == "semantic"


def test_failures_and_oversize_results_are_not_cached(cache):
    store(cache, "coinmarketcap_tool", ARGS, result={"success": False, "error": "HTTP 500"})
    assert cache.repo.entries == {}
    big = {"success": True, "data": "x" * 500_000}
    store(cache, "coinmarketcap_tool", {"query": "big"}, result=big)
    assert cache.repo.entries == {}


def test_a_broken_cache_never_breaks_a_lookup(cache):
    cache.repo.fail = True
    assert lookup(cache, "coinmarketcap_tool", ARGS)[0] is None


def test_disabled_cache_caches_nothing():
    off = ToolCache(FakeCacheRepo(), FakeEmbedder(), Settings(cache_enabled=False))
    assert off.ttl("coinmarketcap_tool") is None and asyncio.run(off.lookup("coinmarketcap_tool", ARGS)) == (None, None)


# ----------------------------------------------------------------------- executor integration
def test_executor_serves_cached_results_without_calling_the_tool(cache, patch_tools, settings):
    tool = FakeTool(OK)
    patch_tools(coinmarketcap_tool=tool)
    request, entities = ResearchRequest(query="price of ETH", session_id="session-12345"), Entities(symbols=["ETH"])

    first = asyncio.run(run_tools(["coinmarketcap_tool"], request, entities, settings=settings, cache=cache))[0]
    second = asyncio.run(run_tools(["coinmarketcap_tool"], request, entities, settings=settings, cache=cache))[0]

    assert len(tool.calls) == 1                                       # the second run never reached the tool
    assert "cached" not in first and second["cached"]["match"] == "exact"
    assert second["success"] and second["data"] == OK["data"] and second["attempts"] == 0


def test_executor_does_not_cache_failures(cache, patch_tools, settings):
    tool = FakeTool({"success": False, "error": "Etherscan: bad key"}, OK)
    patch_tools(coinmarketcap_tool=tool)
    request, entities = ResearchRequest(query="price of ETH", session_id="session-12345"), Entities(symbols=["ETH"])
    asyncio.run(run_tools(["coinmarketcap_tool"], request, entities, settings=settings, cache=cache))
    again = asyncio.run(run_tools(["coinmarketcap_tool"], request, entities, settings=settings, cache=cache))[0]
    assert len(tool.calls) == 2 and again["success"]


def test_executor_reports_cache_hits_to_listeners(cache, patch_tools, settings):
    patch_tools(coinmarketcap_tool=FakeTool(OK))
    request, entities = ResearchRequest(query="price of ETH", session_id="session-12345"), Entities(symbols=["ETH"])
    events = []

    async def on_event(e):
        events.append(e)

    async def go():
        await run_tools(["coinmarketcap_tool"], request, entities, settings=settings, cache=cache)
        await run_tools(["coinmarketcap_tool"], request, entities, on_event, settings, cache=cache)

    asyncio.run(go())
    assert [e for e in events if e["type"] == "tool_end"][0]["cached"] is True
