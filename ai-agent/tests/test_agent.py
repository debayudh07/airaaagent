"""End-to-end agent flow with fake LLMs and fake tools."""
from airaa.agent.core import Web3ResearchAgent
from airaa.schemas import Entities, FollowUp, Plan, ResearchRequest

from .conftest import FakePlannerLLM, FakeSynthesisLLM, FakeTool, run

CMC_OK = {"success": True, "source": "coinmarketcap", "data": {"data": {"BTC": {
    "id": 1, "name": "Bitcoin", "symbol": "BTC", "cmc_rank": 1,
    "quote": {"USD": {"price": 64321.5, "market_cap": 1e12, "percent_change_24h": 1.0}}}}}}
LLAMA_OK = {"success": True, "source": "defillama", "data": {"type": "protocol_tvl", "slug": "aave", "name": "Aave", "tvl_usd": 9e9}}


def make_agent(settings, sessions, planner=None, synth=None):
    return Web3ResearchAgent(
        "session-12345", sessions=sessions, settings=settings,
        planner_llm=planner or FakePlannerLLM(plan=Plan(intent="market_data", tools=["coinmarketcap_tool"],
                                                         entities=Entities(symbols=["BTC"]))),
        synthesis_model=synth or FakeSynthesisLLM(),
    )


def ask(agent, query="price of bitcoin", events=None, address=None):
    async def on_event(e):
        events.append(e)

    req = ResearchRequest(query=query, address=address, session_id="session-12345")
    return run(agent.research(req, on_event=on_event if events is not None else None))


def test_happy_path_streams_events_and_returns_grounded_result(settings, sessions, patch_tools):
    tool = FakeTool(CMC_OK)
    patch_tools(coinmarketcap_tool=tool)
    events = []
    out = ask(make_agent(settings, sessions), events=events)

    assert out["success"] and out["query_intent"] == "market_data" and out["planner"] == "llm"
    assert out["result"].startswith("Here is the answer.")
    assert "Sources: CoinMarketCap · 1 of 1 responded" in out["result"]
    assert out["data_quality_score"] == 100.0 and out["data_sources_used"] == ["coinmarketcap"]
    assert out["tool_trace"][0]["tool"] == "coinmarketcap_tool" and out["tool_trace"][0]["round"] == 1
    assert tool.calls[0]["symbols"] == ["BTC"]  # planner entities reach the tool

    kinds = [e["type"] for e in events]
    assert kinds.index("plan") < kinds.index("tool_start") < kinds.index("tool_end") < kinds.index("token")
    assert "".join(e["text"] for e in events if e["type"] == "token") == "Here is the answer."


def test_synthesis_gets_verified_data_and_prior_turns(settings, sessions, patch_tools):
    patch_tools(coinmarketcap_tool=FakeTool(CMC_OK))
    synth = FakeSynthesisLLM()
    agent = make_agent(settings, sessions, synth=synth)
    ask(agent)
    ask(agent, "and the market cap?")

    first, second = synth.calls
    assert "$64,321.50000000" in first[-1].content and "4,078" not in first[-1].content
    # second call: system prompt, the first question, the first answer, then the new context turn
    assert [m.type for m in second] == ["system", "human", "ai", "human"]
    assert "Here is the answer." in second[2].content


def test_failed_tool_is_disclosed_and_conversation_is_remembered(settings, sessions, patch_tools):
    patch_tools(coinmarketcap_tool=FakeTool({"success": False, "error": "Plan limit", "source": "coinmarketcap"}))
    synth = FakeSynthesisLLM()
    out = ask(make_agent(settings, sessions, synth=synth))
    assert "Plan limit" in synth.calls[0][-1].content
    assert "Unavailable: CoinMarketCap (Plan limit)" in out["result"]
    history = sessions.get("session-12345")["chat_history"].messages
    assert [m.type for m in history] == ["human", "ai"]
    assert history[1].additional_kwargs["research_data"]["tool_trace"]


def test_reflection_runs_a_second_round_when_a_tool_fails(settings, sessions, patch_tools):
    patch_tools(
        coinmarketcap_tool=FakeTool({"success": False, "error": "HTTP 500", "source": "coinmarketcap"}),
        defillama_tool=FakeTool(LLAMA_OK),
    )
    planner = FakePlannerLLM(
        plan=Plan(intent="defi", tools=["coinmarketcap_tool"]),
        followup=FollowUp(needs_more=True, tools=["defillama_tool"], entities=Entities(protocols=["aave"]), reason="need TVL"),
    )
    events = []
    out = ask(make_agent(settings, sessions, planner=planner), "aave tvl", events)
    rounds = [(t["tool"], t["round"]) for t in out["tool_trace"]]
    assert ("coinmarketcap_tool", 1) in rounds and ("defillama_tool", 2) in rounds
    assert any(e["type"] == "followup" for e in events)
    assert out["data_sources_used"] == ["defillama"]


def test_no_reflection_when_all_succeed(settings, sessions, patch_tools):
    patch_tools(coinmarketcap_tool=FakeTool(CMC_OK))
    planner = FakePlannerLLM(plan=Plan(intent="market_data", tools=["coinmarketcap_tool"]),
                             followup=FollowUp(needs_more=True, tools=["defillama_tool"]))
    out = ask(make_agent(settings, sessions, planner=planner))
    assert len(out["tool_trace"]) == 1 and not planner.follow_runner.calls


def test_unrecoverable_failure_alone_does_not_trigger_reflection_if_other_data_exists(settings, sessions, patch_tools):
    patch_tools(
        coinmarketcap_tool=FakeTool({"success": False, "error": "API key not configured", "source": "coinmarketcap"}),
        defillama_tool=FakeTool(LLAMA_OK),
    )
    planner = FakePlannerLLM(plan=Plan(intent="defi", tools=["coinmarketcap_tool", "defillama_tool"]))
    ask(make_agent(settings, sessions, planner=planner))
    assert not planner.follow_runner.calls  # a missing key will not fix itself and we already have data


def test_reflection_can_switch_sources_when_nothing_worked(settings, sessions, patch_tools):
    patch_tools(
        coinmarketcap_tool=FakeTool({"success": False, "error": "API key not configured", "source": "coinmarketcap"}),
        defillama_tool=FakeTool(LLAMA_OK),
    )
    planner = FakePlannerLLM(plan=Plan(intent="defi", tools=["coinmarketcap_tool"]),
                             followup=FollowUp(needs_more=True, tools=["defillama_tool"], reason="use another source"))
    out = ask(make_agent(settings, sessions, planner=planner))
    assert planner.follow_runner.calls and out["data_sources_used"] == ["defillama"]


def test_llm_synthesis_failure_degrades_to_data_summary(settings, sessions, patch_tools):
    patch_tools(coinmarketcap_tool=FakeTool(CMC_OK))
    out = ask(make_agent(settings, sessions, synth=FakeSynthesisLLM(error=RuntimeError("model gone"))))
    assert out["success"] and out["degraded"]
    assert "temporarily unavailable" in out["result"] and "$64,321.50000000" in out["result"]


def test_synthesis_failure_with_no_data_is_an_error(settings, sessions, patch_tools):
    patch_tools(coinmarketcap_tool=FakeTool({"success": False, "error": "HTTP 500", "source": "coinmarketcap"}))
    out = ask(make_agent(settings, sessions, synth=FakeSynthesisLLM(error=RuntimeError("model gone"))))
    assert not out["success"] and "model gone" in out["error"]


def test_planner_outage_still_answers_via_rules(settings, sessions, patch_tools):
    patch_tools(coinmarketcap_tool=FakeTool(CMC_OK))
    planner = FakePlannerLLM(plan_error=RuntimeError("planner down"))
    out = ask(make_agent(settings, sessions, planner=planner), "what is the price of bitcoin")
    assert out["success"] and out["planner"] == "heuristic"


def test_question_needing_no_data_skips_tools(settings, sessions):
    synth = FakeSynthesisLLM()
    agent = make_agent(settings, sessions, synth=synth)
    agent.planner.heuristic_plan = lambda req: Plan(intent="information", tools=[])
    agent.planner._llm = FakePlannerLLM(plan=Plan(intent="information", tools=[]))
    out = ask(agent, "explain proof of stake")
    assert out["success"] and out["tool_trace"] == []
    assert "do not state any prices" in synth.calls[0][-1].content
    assert "Sources:" not in out["result"]


def test_greeting_skips_llm_and_tools(settings, sessions):
    planner = FakePlannerLLM(plan=Plan(intent="general", tools=["coinmarketcap_tool"]))
    out = ask(make_agent(settings, sessions, planner=planner), "hello")
    assert out["query_intent"] == "greeting" and out["tool_trace"] == [] and not planner.plan_runner.calls
