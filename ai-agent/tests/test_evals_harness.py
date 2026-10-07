"""The eval harness itself: metric math, offline gates, and the live suites driven by scripted fake models.

The live suites call real LLMs in production use. Here they run against doubles whose behaviour is known, so we can assert
that good behaviour scores high and bad behaviour (hallucination, obeying an injection, storing a secret) scores low.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, List

import pytest

from airaa.schemas import Entities, FollowUp, Plan
from airaa.tools import web

from .helpers import FakeEmbedder

SPEC = importlib.util.spec_from_file_location("airaa_evals", Path(__file__).resolve().parents[1] / "evals" / "evals.py")
ev = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ev   # dataclasses resolve their module through sys.modules
SPEC.loader.exec_module(ev)


def metric(result, name):
    return next(m for m in result.metrics if m.name == name)


# ----------------------------------------------------------------------- web filter regressions the evals found
@pytest.mark.parametrize("query,title,body,relevant", [
    ("uniswap v4 hooks", "Fishing hooks for beginners", "Choosing the right size hook", False),
    ("who founded Chainlink", "Who founded the Roman Empire?", "Augustus became the first emperor", False),
    ("solana network outage history", "Solana outages: a timeline", "Solana has had several network outages since 2021", True),
    ("when is the next ethereum upgrade", "Ethereum roadmap", "The next upgrade follows Pectra", True),
    ("lido stETH withdrawals", "Bank withdrawals and fees", "ATM withdrawal limits", False),
])
def test_entity_in_the_query_must_appear_in_the_hit(query, title, body, relevant):
    kept, _ = web.relevant_results(query, [{"title": title, "body": body, "href": "https://x.example/page"}])
    assert bool(kept) is relevant


def test_short_tickers_do_not_match_longer_words():
    kept, _ = web.relevant_results("eth staking", [{"title": "Ethical investing basics", "body": "staking your claim", "href": "https://x.example/e"}])
    assert kept == []


# ----------------------------------------------------------------------- statistics
def test_wilson_interval_behaves_at_the_edges():
    assert ev.wilson(0, 0) == (0.0, 0.0)
    lo, hi = ev.wilson(10, 10)
    assert hi == 1.0 and 0.70 < lo < 0.75                       # 10/10 is not "certainly 100%"
    lo, hi = ev.wilson(0, 40)
    assert lo == 0.0 and 0.0 < hi < 0.10
    lo, hi = ev.wilson(36, 40)
    assert lo < 0.9 < hi


def test_percentile_and_auc_and_ndcg():
    assert ev.percentile([1, 2, 3, 4, 5], 50) == 3 and ev.percentile([10], 95) == 10 and ev.percentile([0, 10], 50) == 5
    assert ev.roc_auc([0.9, 0.8], [0.1, 0.2]) == 1.0 and ev.roc_auc([0.1], [0.9]) == 0.0 and ev.roc_auc([0.5], [0.5]) == 0.5 and ev.roc_auc([], [1]) is None
    assert ev.ndcg_at_k([1, 0, 0], 3, 1) == 1.0
    assert 0 < ev.ndcg_at_k([0, 1, 0], 3, 1) < 1 and ev.ndcg_at_k([0, 0, 0], 3, 1) == 0.0


def test_bm25_ranks_the_matching_document_first():
    docs = ["aave lending protocol tvl", "uniswap swap volume fees", "bridge volume across chains"]
    assert ev.rank_desc(ev.BM25(docs).scores("uniswap fees"))[0] == 1
    assert ev.rrf([2, 1, 0], [1, 0, 2])[0] == 1                  # agreed-on by both rankers wins


# ----------------------------------------------------------------------- the grounding checker
def test_numbers_are_extracted_with_their_scale_and_precision():
    nums = {n.text: n for n in ev.extract_numbers("Price $64.3K, cap $1.2 trillion, up 1.50%, supply 19,700,000, 24h and 7d moves")}
    assert nums["$64.3K"].value == 64300 and nums["$64.3K"].kind == "usd" and nums["$64.3K"].half_unit == pytest.approx(50)
    assert nums["$1.2 trillion"].value == 1.2e12 and nums["1.50%"].kind == "pct" and nums["19,700,000"].value == 19_700_000
    assert not any(t in nums for t in ("24h", "7d", "24", "7"))   # durations are skipped


def test_dates_urls_list_markers_and_follow_up_questions_are_not_figures():
    text = ("1. First point at https://x.example/a/2026/10/07 on 2026-10-07 at 10:30\n2) second, Jun 4, 2025\n"
            "Over the last 30 days and 2 weeks it moved.\n\nNext questions\n1. What about 500 other coins?")
    assert ev.extract_numbers(ev.clean_answer(text)) == []


def test_support_accepts_copies_roundings_and_derivations_and_rejects_inventions():
    support = ev.Support("price $64,321.12345678 market cap $1,200,000,000,000 volume $30,000,000,000 24h +1.50%", "")
    ok = lambda s: not ev.unsupported_numbers(s, support)  # noqa: E731
    assert ok("$64,321.12") and ok("about $64.3K") and ok("$1.2 trillion") and ok("2.5% of market cap")
    assert not ok("$67,000") and not ok("up 12%") and not ok("$45 billion")


def test_currency_mode_ignores_illustrative_percentages_but_not_dollar_claims():
    support = ev.Support("no data", "")
    assert ev.unsupported_numbers("If the price doubles you lose about 5.7% versus holding.", support, "currency") == []
    assert ev.unsupported_numbers("ETH trades at $3,000.", support, "currency") == ["$3,000"]
    assert ev.unsupported_numbers("anything 99%", support, "off") == []


def test_fact_matching_by_value_and_by_text():
    assert ev.fact_present("It trades at $3,012.46", 3012.45678901) and not ev.fact_present("$3,100", 3012.45678901)
    assert ev.fact_present("down 4.2%", -4.2) and ev.fact_present("Ethereum is bigger", "ethereum")


# ----------------------------------------------------------------------- offline suites stay green and the CLI behaves
def test_offline_suites_meet_their_gates(capsys):
    assert ev.main([]) == 0
    out = capsys.readouterr().out
    assert "0 below target" in out and "planner_rules" in out and "grounding_validity" in out


def test_cli_surface(capsys):
    assert ev.main(["--list"]) == 0 and "e2e" in capsys.readouterr().out
    assert ev.main(["--suite", "nope"]) == 2
    assert ev.main(["--db"]) == 2                                 # needs --live
    assert ev.main(["--live"]) == 2                               # no key in the test environment


def test_gate_and_baseline_regression_detection(tmp_path, capsys):
    out = tmp_path / "base.json"
    assert ev.main(["--suite", "web_relevance", "--save-baseline", str(out)]) == 0
    baseline = json.loads(out.read_text())
    assert ev.main(["--suite", "web_relevance", "--baseline", str(out)]) == 0
    baseline["suites"][0]["metrics"][0]["value"] = 1.5            # pretend it used to be far better than possible
    out.write_text(json.dumps(baseline))
    assert ev.main(["--suite", "web_relevance", "--baseline", str(out)]) == 1
    assert "REGRESSED" in capsys.readouterr().out
    assert ev.main(["--suite", "web_relevance", "--baseline", str(out), "--no-gate"]) == 0


def test_json_output(tmp_path):
    path = tmp_path / "r" / "run.json"
    ev.main(["--suite", "cache_safety", "--json", str(path)])
    data = json.loads(path.read_text())
    assert data["suites"][0]["name"] == "cache_safety" and any(m["name"] == "different_args_collision_rate" for m in data["suites"][0]["metrics"])


def test_a_crashing_suite_fails_the_run_instead_of_vanishing(monkeypatch, capsys):
    def boom(ctx):
        raise RuntimeError("kaput")

    monkeypatch.setitem(ev.SUITES, "web_relevance", ev.SuiteDef(boom, False, "x", "free"))
    assert ev.main(["--suite", "web_relevance"]) == 1 and "CRASHED" in capsys.readouterr().out


# ----------------------------------------------------------------------- live suites against scripted models
class Piece:
    def __init__(self, text):
        self.text = text


class Runner:
    def __init__(self, fn):
        self.fn = fn

    async def ainvoke(self, messages):
        return self.fn(messages)


def question_of(messages) -> str:
    text = messages[-1].content
    return text.split("Latest question: ")[-1].strip()


class ScriptedPlanner:
    """Answers every structured-output request from the gold labels."""

    def __init__(self, memory_mode="oracle"):
        self.memory_mode = memory_mode
        self.by_query = {c.query: c for c in ev.PLANNER_CASES}
        self.by_e2e = {c.query: c for c in ev.E2E_CASES}
        self.by_injection = {c.query: c for c in ev.INJECTION_CASES}
        self.by_memory = {c.user: c for c in ev.MEMORY_CASES}

    def with_structured_output(self, schema):
        name = schema.__name__
        if name == "Plan":
            def plan(messages):
                q = question_of(messages)
                if q in self.by_query:
                    case = self.by_query[q]
                    tools = list(case.required) + [g[0] for g in case.any_of]
                    return Plan(intent="general", tools=tools, entities=Entities(
                        symbols=list(case.symbols or []), protocols=list(case.protocols or []), chain=case.chain or None, urls=list(case.urls or [])))
                if q in self.by_e2e:
                    case = self.by_e2e[q]
                    return Plan(intent="general", tools=list(case.required) + [g[0] for g in case.any_of])
                if q in self.by_injection:
                    return Plan(intent="general", tools=list(self.by_injection[q].required))
                return Plan(intent="general", tools=[])
            return Runner(plan)
        if name == "FollowUp":
            return Runner(lambda m: FollowUp(needs_more=False))
        if name == "MemoryExtraction":
            def memory(messages):
                user = messages[-1].content.split("User: ", 1)[1].split("\n\nAssistant:")[0]
                case = self.by_memory[user]
                if self.memory_mode == "leaky" and case.secret:
                    return schema(memories=[{"kind": "fact", "content": "The user's secret is " + user.split("is ")[-1][:60], "importance": 0.9}])
                if case.none:
                    return schema(memories=[])
                words = " ".join(k[0] for k in case.expect)
                return schema(memories=[{"kind": "fact", "content": f"The user cares about {words}.", "importance": 0.7}])
            return Runner(memory)
        return Runner(lambda m: schema(relevance=5, completeness=4, clarity=5, reason="scripted"))


class ScriptedSynthesis:
    """mode: faithful (copies the data), hallucinating (adds an invented price), obedient (repeats everything it was shown),
    blank (a constant, safe reply)."""

    used = "scripted"

    def __init__(self, mode="faithful"):
        self.mode = mode

    async def astream(self, messages):
        prompt = messages[-1].content
        if "(no data was retrieved)" in prompt or "No live data was retrieved" in prompt:
            text = "That is not available from the sources I could reach."
        elif self.mode == "blank":
            text = "Here is a short summary of what was found, attributed to the sources.\n\nNext questions\n1. What else?"
        elif self.mode == "obedient":
            text = prompt
        else:
            data = prompt.split("=== VERIFIED DATA (the only facts you may use) ===", 1)[-1].split("=== UNAVAILABLE SOURCES ===")[0]
            data = "\n".join(line for line in data.splitlines() if not line.startswith("<<<"))
            text = f"According to CoinMarketCap and DefiLlama, here is what the data says:\n{data}\n(Etherscan, News) UNAVAILABLE items could not be fetched.\n\nNext questions\n1. And SOL?"
            if self.mode == "hallucinating":
                text += "\nThe price is $99,999.99 and TVL is $77 billion."
        for i in range(0, len(text), 400):
            yield Piece(text[i:i + 400])


class FakeProviders(ev.Providers):
    def __init__(self, settings, synthesis="faithful", memory="oracle"):
        super().__init__(settings)
        self._synthesis, self._memory = synthesis, memory

    def planner_llm(self):
        return ScriptedPlanner(self._memory)

    def synthesis_llm(self):
        return ScriptedSynthesis(self._synthesis)

    def embedder(self):
        return FakeEmbedder()


def live_ctx(settings, **kw):
    providers = kw.pop("providers", None) or FakeProviders(settings)
    return ev.Ctx(settings, providers, live=True, concurrency=2, **kw)


def test_planner_llm_suite_scores_a_perfect_planner_as_perfect(settings):
    result = ev.suite_planner_llm(live_ctx(settings))
    assert metric(result, "tool_recall").value == 1.0 and metric(result, "plan_satisfied_rate").value == 1.0
    assert metric(result, "etherscan_without_address").value == 0.0 and metric(result, "fallback_rate").value <= 0.05
    assert metric(result, "symbol_f1").value == 1.0


def test_e2e_scores_a_faithful_model_high_and_a_hallucinating_one_low(settings):
    good = ev.suite_e2e(live_ctx(settings, judge=True))
    assert metric(good, "error_rate").value == 0.0
    assert metric(good, "numeric_grounding_rate").value == 1.0 and metric(good, "url_integrity").value == 1.0
    assert metric(good, "required_fact_recall").value == 1.0 and metric(good, "honesty_on_missing_data").value == 1.0
    assert metric(good, "judge.relevance").value == 5 and metric(good, "e2e_p50_ms").value >= 0

    bad = ev.suite_e2e(live_ctx(settings, providers=FakeProviders(settings, synthesis="hallucinating")))
    assert metric(bad, "numeric_grounding_rate").value < 0.5
    assert metric(bad, "unsupported_numbers_per_answer").value > 0.5
    assert any("unsupported numbers" in f.detail for f in bad.failures)


def test_e2e_catches_missing_honesty_and_invented_links(settings):
    class Liar(ScriptedSynthesis):
        async def astream(self, messages):
            yield Piece("ETH is great, see https://made-up.example/eth for details. The data is all here.\n\nNext questions\n1. Why?")

    result = ev.suite_e2e(live_ctx(settings, providers=type("P", (FakeProviders,), {"synthesis_llm": lambda self: Liar()})(settings)))
    assert metric(result, "url_integrity").value < 1.0 and metric(result, "honesty_on_missing_data").value < 1.0
    assert metric(result, "required_fact_recall").value < 1.0


def test_injection_suite_passes_a_safe_model_and_fails_an_obedient_one(settings):
    safe = ev.suite_injection(live_ctx(settings, providers=FakeProviders(settings, synthesis="blank")))
    assert metric(safe, "injection_resistance").value == 1.0 and safe.failures == []
    obedient = ev.suite_injection(live_ctx(settings, providers=FakeProviders(settings, synthesis="obedient")))
    assert metric(obedient, "injection_resistance").value < 1.0 and any("INJECTION SUCCEEDED" in f.detail for f in obedient.failures)


def test_injection_attribution_exception_only_covers_attributed_claims(settings):
    case = next(c for c in ev.INJECTION_CASES if c.id == "fake-price")
    assert ev._ATTRIB.search("A blog claims Bitcoin hit $1,000,000, which contradicts CoinMarketCap.")
    assert not ev._ATTRIB.search("Bitcoin is now $1,000,000.")
    assert case.allow_if_attributed


def test_memory_suite_rewards_good_extraction_and_flags_secret_storage(settings):
    good = ev.suite_memory(live_ctx(settings))
    assert metric(good, "fact_recall").value == 1.0 and metric(good, "secret_leak_rate").value == 0.0
    assert metric(good, "nothing_to_remember_accuracy").value == 1.0
    leaky = ev.suite_memory(live_ctx(settings, providers=FakeProviders(settings, memory="leaky")))
    assert metric(leaky, "secret_leak_rate").value > 0 and any("SECRET STORED" in f.detail for f in leaky.failures)


def test_retrieval_and_cache_live_paths_run_and_report_every_metric(settings):
    r = ev.suite_retrieval(live_ctx(settings))
    names = {m.name for m in r.metrics}
    assert {"bm25.hit@1", "vector.hit@5", "hybrid.mrr@10", "vector.abstention_auc", "vector.false_positive_at_cutoff", "hybrid.pass_rate_at_cutoff"} <= names
    c = ev.suite_cache_safety(live_ctx(settings))
    assert {"semantic_auc", "false_hit_rate_at_threshold", "true_hit_rate_at_threshold"} <= {m.name for m in c.metrics}
    assert any("threshold sweep" in n for n in c.notes)


def test_limit_and_repeat_scale_the_work(settings):
    one = ev.suite_memory(live_ctx(settings, limit=2))
    assert one.n_cases == 2
    three = ev.suite_memory(live_ctx(settings, limit=2, repeat=3))
    assert three.n_cases == 6


def test_frozen_tools_restore_the_real_registry():
    from airaa.tools import TOOLS

    before = dict(TOOLS)
    with ev.frozen_tools():
        assert all(isinstance(t, ev.FixtureTool) for t in TOOLS.values())
    assert TOOLS == before


def test_planner_gold_labels_are_internally_consistent():
    ids = [c.id for c in ev.PLANNER_CASES]
    assert len(ids) == len(set(ids))
    valid = set(ev.T.values())
    for c in ev.PLANNER_CASES:
        used = set(c.required) | set(c.optional) | {t for g in c.any_of for t in g}
        assert used <= valid, c.id
        assert not (c.none and (c.required or c.any_of)), c.id
    assert all(gold.endswith("\n") for _, gold in ev.RETRIEVAL_GOLD)


def test_every_retrieval_gold_answer_exists_in_the_corpus():
    corpus = ev.build_corpus()
    missing = [g for _, g in ev.RETRIEVAL_GOLD if not any(g.lower() in c.text.lower() for c in corpus)]
    assert missing == []
