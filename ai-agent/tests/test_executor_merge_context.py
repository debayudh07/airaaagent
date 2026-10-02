import json

from airaa.agent.context import build_context
from airaa.agent.executor import build_tool_args, run_tools
from airaa.agent.merge import merge_results
from airaa.schemas import Entities, Plan, ResearchRequest

from .conftest import FakeTool, run

ADDRESS = "0x" + "cd" * 20
OK = {"success": True, "data": {}, "source": "x"}


def request(query="q", address=None):
    return ResearchRequest(query=query, address=address, session_id="session-12345")


# ------------------------------------------------------------------ executor
def test_tool_args_carry_planner_entities():
    ents = Entities(symbols=["BTC"], protocols=["aave"], chain="Arbitrum")
    assert build_tool_args("coinmarketcap_tool", request(), ents)["symbols"] == ["BTC"]
    assert build_tool_args("defillama_tool", request(), ents)["protocols"] == ["aave"]
    assert build_tool_args("etherscan_tool", request(address=ADDRESS), ents)["chain"] == "arbitrum"


def test_wallet_address_is_not_passed_to_dune_and_etherscan_needs_one():
    ents = Entities()
    assert "address" not in build_tool_args("dune_analytics_tool", request(address=ADDRESS), ents)
    assert build_tool_args("etherscan_tool", request(), ents) is None


def test_run_tools_traces_success_and_failure(settings, patch_tools):
    good = FakeTool({"success": True, "data": 1, "source": "coinmarketcap"})
    bad = FakeTool({"success": False, "error": "API key missing", "source": "defillama"})
    patch_tools(coinmarketcap_tool=good, defillama_tool=bad)
    events = []

    async def on_event(e):
        events.append(e["type"])

    results = run(run_tools(["coinmarketcap_tool", "defillama_tool"], request(), Entities(), on_event, settings))
    assert [r["success"] for r in results] == [True, False]
    assert all(r["duration_ms"] >= 0 and r["attempts"] == 1 for r in results)
    assert events.count("tool_start") == 2 and events.count("tool_end") == 2
    assert len(bad.calls) == 1  # non-transient failures are not retried


def test_transient_failure_is_retried_once(settings, patch_tools):
    flaky = FakeTool({"success": False, "error": "HTTP 503", "source": "s"}, {"success": True, "data": 1, "source": "s"})
    patch_tools(coinmarketcap_tool=flaky)
    (result,) = run(run_tools(["coinmarketcap_tool"], request(), Entities(), None, settings))
    assert result["success"] and result["attempts"] == 2


def test_timeout_is_reported_not_raised(settings, patch_tools):
    patch_tools(coinmarketcap_tool=FakeTool({"success": True, "source": "s"}, delay=5))
    (result,) = run(run_tools(["coinmarketcap_tool"], request(), Entities(), None, settings))
    assert not result["success"] and "Timed out" in result["error"]


def test_unrunnable_and_unknown_tools_are_skipped(settings, patch_tools):
    patch_tools(etherscan_tool=FakeTool(OK))
    assert run(run_tools(["etherscan_tool", "nope_tool"], request(), Entities(), None, settings)) == []


# ------------------------------------------------------------------ merge
def cmc_quotes(symbol="BTC", price=64321.12345678):
    return {"success": True, "source": "coinmarketcap", "tool": "coinmarketcap_tool", "data": {"data": {symbol: {
        "id": 1, "name": "Bitcoin", "symbol": symbol, "cmc_rank": 1, "circulating_supply": 19e6,
        "quote": {"USD": {"price": price, "market_cap": 1.2e12, "volume_24h": 3e10,
                          "percent_change_24h": 1.5, "percent_change_7d": -2.25}},
    }}}}


def test_merge_quotes_keyed_by_symbol_and_v2_lists():
    merged = merge_results([cmc_quotes()])
    assert merged["primary_data"]["market_BTC"]["price"] == 64321.12345678
    v2 = cmc_quotes("ETH")
    v2["data"]["data"]["ETH"] = [v2["data"]["data"]["ETH"]]
    assert "market_ETH" in merge_results([v2])["primary_data"]


def test_merge_listings_and_global_metrics():
    listing = {"success": True, "source": "coinmarketcap", "data": {"data": [
        {"id": 1, "name": "Bitcoin", "symbol": "BTC", "quote": {"USD": {"price": 1}}}]}}
    global_ = {"success": True, "source": "coinmarketcap", "data": {"data": {
        "active_cryptocurrencies": 10, "btc_dominance": 55.5, "quote": {"USD": {"total_market_cap": 5}}}}}
    merged = merge_results([listing, global_])
    assert "market_BTC" in merged["primary_data"]
    assert merged["supplementary_data"]["global_metrics"]["bitcoin_dominance"] == 55.5


def test_merge_etherscan_balance_and_transactions():
    balance = {"success": True, "source": "etherscan", "metadata": {"address": ADDRESS, "chain": "ethereum"},
               "data": {"result": str(2 * 10 ** 18)}}
    txs = {"success": True, "source": "etherscan", "metadata": {"query_type": "txlist", "chain": "ethereum"},
           "data": {"result": [{"hash": "0x1", "from": "a", "to": "b", "value": str(10 ** 18), "timeStamp": "1"}]}}
    sup = merge_results([balance, txs])["supplementary_data"]
    assert sup["wallet_balance"]["balance_native"] == 2.0
    assert sup["transactions"]["transactions"][0]["value_native"] == 1.0


def test_merge_defillama_shapes():
    aggregate = {"success": True, "source": "defillama", "data": {"aggregate": True, "tvl": {"type": "tvl_overview"}, "yields": {}}}
    protocol = {"success": True, "source": "defillama", "data": {"type": "protocol_tvl", "slug": "aave"}}
    sup = merge_results([aggregate, protocol])["supplementary_data"]
    assert "defillama_tvl" in sup and "defillama_yields" not in sup and "protocol_aave" in sup


def test_completeness_is_the_share_of_sources_that_responded():
    failed = {"success": False, "source": "etherscan", "tool": "etherscan_tool", "error": "HTTP 500"}
    merged = merge_results([cmc_quotes(), failed])
    meta = merged["metadata"]
    assert meta["completeness_score"] == 50.0 and meta["data_quality"] == "partial"
    assert meta["failed_sources"][0]["error"] == "HTTP 500"
    assert merge_results([failed])["metadata"]["data_quality"] == "none"


def test_followup_results_accumulate_into_existing_merge():
    first = merge_results([{"success": False, "source": "defillama", "tool": "defillama_tool", "error": "HTTP 502"}])
    second = merge_results([{"success": True, "source": "defillama", "data": {"type": "protocol_tvl", "slug": "lido"}}], first)
    assert second["metadata"]["tools_attempted"] == 2 and "protocol_lido" in second["supplementary_data"]


# ------------------------------------------------------------------ context
def test_context_contains_exact_values_and_no_hardcoded_prices():
    merged = merge_results([cmc_quotes("SOL", price=151.23456789)])
    text = build_context(request("price of sol"), Plan(intent="market_data", tools=["coinmarketcap_tool"]), merged)
    assert "$151.23456789" in text and "(SOL)" in text
    assert "4,078" not in text and "492,302" not in text  # the old prompt hard-coded an ETH price


def test_context_lists_unavailable_sources():
    failed = {"success": False, "source": "etherscan", "tool": "etherscan_tool", "error": "Etherscan API key not configured"}
    text = build_context(request(), Plan(intent="general", tools=["etherscan_tool"]), merge_results([failed]))
    assert "UNAVAILABLE SOURCES" in text and "Etherscan API key not configured" in text
    assert "(no data was retrieved)" in text


def test_merged_data_is_json_serialisable():
    json.dumps(merge_results([cmc_quotes()]))


def test_context_flags_stale_dune_data_and_passes_fresh_data_through():
    from datetime import datetime, timedelta, timezone

    def dune(as_of):
        return {"success": True, "source": "dune_analytics", "metadata": {"chain": "ethereum", "as_of": as_of},
                "data": [{"token_pair": "A-B", "one_day_volume": 5, "seven_day_volume": 6, "usd_liquidity": 7}]}

    plan = Plan(intent="technical", tools=["dune_analytics_tool"])
    stale = build_context(request(), plan, merge_results([dune("2026-08-03T03:40:04Z")]))
    assert "STALE" in stale and "A-B" in stale
    fresh_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    assert "STALE" not in build_context(request(), plan, merge_results([dune(fresh_ts)]))
