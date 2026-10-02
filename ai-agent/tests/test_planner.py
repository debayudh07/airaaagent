from airaa.agent.planner import Planner
from airaa.schemas import Entities, FollowUp, Plan, ResearchRequest

from .conftest import FakePlannerLLM, run

ADDRESS = "0x" + "ab" * 20


def make(settings, sessions, llm=None):
    return Planner(sessions, llm=llm, settings=settings)


def req(query, address=None, session_id="session-12345"):
    return ResearchRequest(query=query, address=address, session_id=session_id)


# ------------------------------------------------------------------ heuristic
def test_price_question_uses_only_coinmarketcap(settings, sessions):
    plan = make(settings, sessions).heuristic_plan(req("what is the price of bitcoin?"))
    assert plan.tools == ["coinmarketcap_tool"]
    assert plan.entities.symbols == ["BTC"]


def test_protocol_question_uses_defillama_with_slug(settings, sessions):
    plan = make(settings, sessions).heuristic_plan(req("TVL of aave on ethereum"))
    assert plan.tools == ["defillama_tool"]
    assert plan.entities.protocols == ["aave"] and plan.entities.chain == "Ethereum"


def test_wallet_question_needs_an_address(settings, sessions):
    planner = make(settings, sessions)
    assert "etherscan_tool" in planner.heuristic_plan(req("show my wallet transactions", ADDRESS)).tools
    assert "etherscan_tool" not in planner.heuristic_plan(req("show my wallet transactions")).tools


def test_heuristic_never_invents_an_address(settings, sessions):
    plan = make(settings, sessions).heuristic_plan(req("analyze ethereum investment"))
    assert "etherscan_tool" not in plan.tools


def test_short_followup_inherits_previous_symbols(settings, sessions):
    sessions.get_or_create("session-12345")
    sessions.update_context("session-12345", {"last_query": "price of solana"})
    plan = make(settings, sessions).heuristic_plan(req("and what about that one?"))
    assert plan.entities.symbols == ["SOL"]


# ------------------------------------------------------------------ LLM planner
def test_llm_plan_is_used_and_sanitised(settings, sessions):
    llm = FakePlannerLLM(plan=Plan(
        intent="comparison", tools=["coinmarketcap_tool", "coinmarketcap_tool", "etherscan_tool"],
        entities=Entities(symbols=["btc", "sol"], protocols=["Aave"]), rationale="compare two coins",
    ))
    out = run(make(settings, sessions, llm).plan(req("compare btc and sol")))
    assert out["planner"] == "llm"
    plan = out["plan"]
    assert plan.tools == ["coinmarketcap_tool"]  # deduped; etherscan dropped (no address)
    assert plan.entities.symbols == ["BTC", "SOL"] and plan.entities.protocols == ["aave"]


def test_llm_failure_falls_back_to_rules(settings, sessions):
    llm = FakePlannerLLM(plan_error=RuntimeError("model unavailable"))
    out = run(make(settings, sessions, llm).plan(req("price of ethereum")))
    assert out["planner"] == "heuristic" and out["plan"].tools == ["coinmarketcap_tool"]


def test_llm_timeout_falls_back_to_rules(settings, sessions):
    llm = FakePlannerLLM(plan=Plan(intent="general", tools=["defillama_tool"]), delay=5)
    out = run(make(settings, sessions, llm).plan(req("price of ethereum")))
    assert out["planner"] == "heuristic"


def test_empty_llm_plan_falls_back(settings, sessions):
    llm = FakePlannerLLM(plan=Plan(intent="general", tools=[]))
    out = run(make(settings, sessions, llm).plan(req("tvl of lido")))
    assert out["planner"] == "heuristic" and out["plan"].tools == ["defillama_tool"]


# ------------------------------------------------------------------ reflection
def test_reflection_returns_followup(settings, sessions):
    decision = FollowUp(needs_more=True, tools=["defillama_tool"], reason="TVL missing")
    llm = FakePlannerLLM(followup=decision)
    plan = Plan(intent="defi", tools=["coinmarketcap_tool"])
    got = run(make(settings, sessions, llm).reflect(req("aave tvl"), plan, [{"tool": "coinmarketcap_tool", "success": True}]))
    assert got.needs_more and got.tools == ["defillama_tool"]


def test_reflection_drops_etherscan_without_address(settings, sessions):
    llm = FakePlannerLLM(followup=FollowUp(needs_more=True, tools=["etherscan_tool"]))
    got = run(make(settings, sessions, llm).reflect(req("hi there"), Plan(intent="general", tools=[]), []))
    assert got.tools == []


def test_reflection_failure_means_no_followup(settings, sessions):
    class Broken:
        def with_structured_output(self, schema):
            raise RuntimeError("boom")

    assert run(make(settings, sessions, Broken()).reflect(req("x"), Plan(intent="general", tools=[]), [])) is None
