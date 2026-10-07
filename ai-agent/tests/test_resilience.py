"""Regressions for a real bad answer: junk web results, a model dying mid-answer, and a misleading degraded reply."""
from __future__ import annotations

import asyncio
from typing import Any, List

import pytest

from airaa.agent.context import plain_summary
from airaa.agent.core import Web3ResearchAgent
from airaa.agent.llm import STREAM_RESET, FallbackModel
from airaa.agent.merge import merge_results
from airaa.schemas import Entities, Plan, ResearchRequest
from airaa.tools import web

from .conftest import FakePlannerLLM, FakeSynthesisLLM, FakeTool, run

PLANTS = [{"title": "How Do Plants Adapt to Their Environment? - ScienceInsights", "href": "https://example.org/plants",
           "body": "Biological adaptation in plants is the evolutionary process by which species survive in habitats."},
          {"title": "How Plants Adapt to Their Environment | The Real Dirt", "href": "https://example.org/dirt",
           "body": "Plants have adapted to the specific conditions of their native habitat, including climate and soil."}]
AAVE = [{"title": "What Is Aave? The Popular DeFi Protocol Explained - Ledger", "href": "https://www.ledger.com/academy/topics/defi/what-is-aave",
         "body": "Aave is a decentralised lending protocol where users supply and borrow crypto assets."},
        {"title": "What is Aave? DeFi lending explained", "href": "https://blockspot.io/what-is-aave/", "body": "Aave lets you earn interest."}]
QUERY = "what is Aave protocol explained DeFi"


# ----------------------------------------------------------------------- web search relevance
def test_unrelated_results_are_dropped():
    kept, dropped = web.relevant_results(QUERY, PLANTS + AAVE)
    assert [r["href"] for r in kept] == [r["href"] for r in AAVE] and dropped == 2


def test_everything_irrelevant_leaves_nothing():
    assert web.relevant_results(QUERY, PLANTS) == ([], 2)


def test_asset_aliases_count_as_the_same_topic():
    rows = [{"title": "ETH staking rewards", "href": "https://x/eth", "body": "How staking works"},
            {"title": "Bread recipes", "href": "https://x/bread", "body": "Flour and water"}]
    kept, _ = web.relevant_results("ethereum staking", rows)
    assert [r["href"] for r in kept] == ["https://x/eth"]


def test_multi_word_queries_need_half_of_the_distinctive_words():
    rows = [{"title": "Aave vs Compound lending rates", "href": "https://x/1", "body": ""},
            {"title": "Aave news", "href": "https://x/2", "body": ""},
            {"title": "Cooking pasta", "href": "https://x/3", "body": ""}]
    kept, _ = web.relevant_results("aave compound lending rates comparison", rows)    # 4 distinctive words, 2 needed
    assert [r["href"] for r in kept] == ["https://x/1"]


def test_a_query_with_no_distinctive_words_is_not_judged():
    rows = [{"title": "Anything", "href": "https://x/1", "body": ""}]
    assert web.relevant_results("what is it explained", rows) == (rows, 0)


def test_word_matching_is_not_substring_matching():
    rows = [{"title": "Maave is a village", "href": "https://x/1", "body": "Nothing to do with finance"}]
    assert web.relevant_results("aave", rows) == ([], 1)


class FakeDDGS:
    def __init__(self, *batches):
        self.batches, self.calls = list(batches), 0

    def text(self, term, **kwargs):
        self.calls += 1
        batch = self.batches[min(self.calls - 1, len(self.batches) - 1)]
        if isinstance(batch, Exception):
            raise batch
        return batch


@pytest.fixture
def no_sleep(monkeypatch):
    async def instant(_seconds):
        return None

    monkeypatch.setattr(web.asyncio, "sleep", instant)


def search(monkeypatch, *batches):
    fake = FakeDDGS(*batches)
    monkeypatch.setattr(web, "_ddgs", lambda: fake)
    result = run(web.web_search_tool.ainvoke({"query": QUERY, "search": QUERY}))
    return result, fake


def test_search_tool_returns_only_relevant_hits(monkeypatch):
    result, fake = search(monkeypatch, PLANTS + AAVE)
    assert result["success"] and fake.calls == 1
    assert [r["url"] for r in result["data"]["results"]] == [r["href"] for r in AAVE]
    assert result["metadata"]["filtered_out"] == 2


def test_search_tool_retries_once_when_the_first_answer_is_junk(monkeypatch, no_sleep):
    result, fake = search(monkeypatch, PLANTS, AAVE)
    assert result["success"] and fake.calls == 2 and len(result["data"]["results"]) == 2


def test_search_tool_reports_failure_rather_than_passing_junk_on(monkeypatch, no_sleep):
    result, fake = search(monkeypatch, PLANTS)
    assert not result["success"] and fake.calls == 2
    assert "no relevant web results" in result["error"].lower()


def test_search_tool_survives_an_engine_error_then_recovers(monkeypatch, no_sleep):
    result, fake = search(monkeypatch, RuntimeError("blocked"), AAVE)
    assert result["success"] and fake.calls == 2
    failed, _ = search(monkeypatch, RuntimeError("blocked"))
    assert not failed["success"] and "Web search failed" in failed["error"]


# ----------------------------------------------------------------------- model fallback chain
class Piece:
    def __init__(self, text: str):
        self.text = text


class ScriptedModel:
    """Stands in for one chat model: yields scripted pieces, then optionally fails or hangs."""

    def __init__(self, name: str, pieces: List[str] = (), then: Any = None, hang_first: bool = False):
        self.model, self.pieces, self.then, self.hang_first = name, list(pieces), then, hang_first

    async def astream(self, messages):
        if self.hang_first:
            await asyncio.sleep(60)
        for text in self.pieces:
            yield Piece(text)
        if self.then is not None:
            raise self.then


def collect(chain: FallbackModel):
    async def go():
        out = []
        async for chunk in chain.astream(["hi"]):
            out.append("<RESET>" if chunk is STREAM_RESET else chunk.text)
        return out

    return run(go())


def test_the_first_healthy_model_is_used():
    chain = FallbackModel([ScriptedModel("a", ["Hello ", "world"]), ScriptedModel("b", ["unused"])])
    assert collect(chain) == ["Hello ", "world"] and chain.used == "a"


def test_a_model_that_fails_before_any_text_hands_over_silently():
    chain = FallbackModel([ScriptedModel("a", then=RuntimeError("503 UNAVAILABLE")), ScriptedModel("b", ["ok"])])
    assert collect(chain) == ["ok"] and chain.used == "b"


def test_an_empty_answer_is_a_failure_not_a_success():
    chain = FallbackModel([ScriptedModel("a", [""]), ScriptedModel("b", ["real answer"])])
    assert collect(chain) == ["", "real answer"] and chain.used == "b"


def test_thinking_chunks_without_text_do_not_count_as_an_answer():
    chain = FallbackModel([ScriptedModel("a", ["", "", ""], then=RuntimeError("503")), ScriptedModel("b", ["fine"])])
    out = collect(chain)
    assert "<RESET>" not in out and out[-1] == "fine"       # nothing was shown yet, so no reset is needed


def test_a_model_dying_mid_answer_triggers_a_reset_and_a_fresh_answer():
    chain = FallbackModel([ScriptedModel("a", ["Aave is a ", "lending"], then=RuntimeError("503")), ScriptedModel("b", ["Aave is a lending protocol."])])
    assert collect(chain) == ["Aave is a ", "lending", "<RESET>", "Aave is a lending protocol."]
    assert chain.used == "b"


def test_a_stalled_model_is_abandoned_after_the_first_token_budget():
    chain = FallbackModel([ScriptedModel("slow", ["never"], hang_first=True), ScriptedModel("b", ["quick"])], first_token_timeout=0.1)
    assert collect(chain) == ["quick"] and chain.used == "b"


def test_when_every_model_fails_the_error_names_each_one():
    chain = FallbackModel([ScriptedModel("a", then=RuntimeError("boom")), ScriptedModel("b", [""])])
    with pytest.raises(RuntimeError) as err:
        collect(chain)
    assert "a:" in str(err.value) and "b: empty answer" in str(err.value)


# ----------------------------------------------------------------------- the agent around it
class ResettingLLM:
    """Yields a partial draft, the reset marker, then the real answer."""

    used = "second"

    async def astream(self, messages):
        yield Piece("A broken, partial dra")
        yield STREAM_RESET
        yield Piece("The real ")
        yield Piece("answer.")


def agent(sessions, settings, synthesis, **kw):
    return Web3ResearchAgent(
        "session-12345", sessions=sessions, settings=settings, retrieval=kw.get("retrieval"), cache=None,
        planner_llm=FakePlannerLLM(plan=Plan(intent="general", tools=["web_search_tool"], entities=Entities(search_query=QUERY))),
        synthesis_model=synthesis)


WEB_OK = {"success": True, "source": "web_search", "data": {"search": QUERY, "results": [
    {"title": "What is Aave?", "url": "https://example.com/aave", "snippet": "Aave is a lending protocol."}]}}


def test_a_mid_answer_model_switch_discards_the_partial_draft(settings, sessions, patch_tools):
    patch_tools(web_search_tool=FakeTool(WEB_OK))
    events = []

    async def on_event(e):
        events.append(e)

    result = run(agent(sessions, settings, ResettingLLM()).research(
        ResearchRequest(query=QUERY, session_id="session-12345"), on_event))
    assert result["success"] and result["result"].startswith("The real answer.") and "partial" not in result["result"]
    types = [e["type"] for e in events]
    assert "reset" in types and types.index("reset") > types.index("token")          # the client is told to clear its draft


PASSAGES = [{"title": "Liquidations | Aave Protocol Documentation", "url": "https://aave.com/docs/concepts/liquidations",
             "content": "A position is liquidated when its health factor falls below one. " * 4},
            {"title": "Liquidations | Aave Protocol Documentation", "url": "https://aave.com/docs/concepts/liquidations", "content": "duplicate url"}]


def test_degraded_answer_hides_prompt_fences_and_shows_the_docs():
    request = ResearchRequest(query=QUERY, session_id="session-12345", kb_passages=PASSAGES)
    merged = merge_results([WEB_OK])
    text = plain_summary(request, Plan(intent="general", tools=["web_search_tool"]), merged)
    assert "UNTRUSTED" not in text and "<<<" not in text                              # internal markers never reach the user
    assert "What is Aave?" in text and "https://example.com/aave" in text
    assert "**From the documentation:**" in text and text.count("aave.com/docs/concepts/liquidations") == 1   # de-duplicated
    assert "health factor" in text


def test_degraded_answer_with_no_data_leads_with_the_docs():
    request = ResearchRequest(query=QUERY, session_id="session-12345", kb_passages=PASSAGES)
    failed = merge_results([{"success": False, "source": "web_search", "tool": "web_search_tool", "error": "No relevant web results"}])
    text = plain_summary(request, Plan(intent="general", tools=["web_search_tool"]), failed)
    assert "(no data was retrieved)" not in text and "health factor" in text


class RecordingRetrieval:
    """Hands the agent a personalised context and docs, as the real one does for a signed-in wallet."""

    async def build(self, request):
        from airaa.retrieval import Retrieved

        return Retrieved(summary="- watches Aave", blocks="USER CONTEXT: watches Aave", used={"memories": 1, "documents": 1},
                         citations=[{"title": "Liquidations | Aave Protocol Documentation", "url": PASSAGES[0]["url"], "similarity": 0.8}],
                         passages=PASSAGES[:1])

    def remember(self, *a, **k):
        pass


def test_degraded_reply_does_not_claim_personalisation_but_does_show_its_docs(settings, sessions, patch_tools):
    patch_tools(web_search_tool=FakeTool(WEB_OK))
    result = run(agent(sessions, settings, FakeSynthesisLLM(error=RuntimeError("503 UNAVAILABLE")), retrieval=RecordingRetrieval()).research(
        ResearchRequest(query=QUERY, session_id="session-12345", wallet_id="w1")))
    assert result["success"] and result["degraded"] is True
    assert "personalization" not in result                                            # the answer did not use it, so do not say so
    assert result["knowledge_sources"][0]["url"] == PASSAGES[0]["url"]                # ...but the docs are in the text
    assert "health factor" in result["result"] and "UNTRUSTED" not in result["result"]


def test_a_healthy_reply_still_reports_what_it_used(settings, sessions, patch_tools):
    patch_tools(web_search_tool=FakeTool(WEB_OK))
    result = run(agent(sessions, settings, FakeSynthesisLLM(["Aave is a lending protocol."]), retrieval=RecordingRetrieval()).research(
        ResearchRequest(query=QUERY, session_id="session-12345", wallet_id="w1")))
    assert result["degraded"] is False and result["personalization"] == {"memories": 1, "documents": 1}


def test_docs_alone_are_enough_to_answer_when_the_model_is_down_and_no_tool_ran(settings, sessions):
    plan_llm = FakePlannerLLM(plan=Plan(intent="general", tools=[]))
    a = Web3ResearchAgent("session-12345", sessions=sessions, settings=settings, retrieval=RecordingRetrieval(), cache=None,
                          planner_llm=plan_llm, synthesis_model=FakeSynthesisLLM(error=RuntimeError("503")))
    result = run(a.research(ResearchRequest(query="what is aave", session_id="session-12345", wallet_id="w1")))
    assert result["success"] and "health factor" in result["result"]


# ----------------------------------------------------------------------- embedding retries
def _embedder_with(client, monkeypatch):
    from airaa import embeddings
    from airaa.config import Settings

    waits = []
    monkeypatch.setattr(embeddings.time, "sleep", lambda seconds: waits.append(round(seconds)))
    return embeddings.Embedder(Settings(gemini_api_key="t"), client=client), waits


class _Resp:
    def __init__(self, n):
        self.embeddings = [type("E", (), {"values": [1.0] + [0.0] * 767})() for _ in range(n)]


class _Models:
    def __init__(self, *errors):
        self.errors, self.calls = list(errors), 0

    def embed_content(self, model, contents, config):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return _Resp(len(contents))


def test_embedder_waits_out_a_rate_limit_instead_of_failing_in_a_second(monkeypatch):
    models = _Models(RuntimeError("429 RESOURCE_EXHAUSTED quota exceeded"), RuntimeError("429 RESOURCE_EXHAUSTED"))
    embedder, waits = _embedder_with(type("C", (), {"models": models})(), monkeypatch)
    assert len(embedder.embed_sync(["a", "b"])) == 2 and models.calls == 3
    assert waits[0] >= 4 and waits[1] >= 12                       # backs off for seconds, not milliseconds


def test_embedder_retries_ordinary_errors_quickly_and_names_a_rate_limit_when_it_gives_up(monkeypatch):
    from airaa.embeddings import EmbeddingUnavailable

    blip = _Models(RuntimeError("connection reset"))
    embedder, waits = _embedder_with(type("C", (), {"models": blip})(), monkeypatch)
    assert embedder.embed_sync(["a"]) and waits == [0] or waits[0] < 2

    always = _Models(*[RuntimeError("429 quota")] * 10)
    embedder, _ = _embedder_with(type("C", (), {"models": always})(), monkeypatch)
    with pytest.raises(EmbeddingUnavailable, match="rate limited"):
        embedder.embed_sync(["a"])
