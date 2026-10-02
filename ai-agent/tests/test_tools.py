"""Tool tests against a mocked HTTP layer (no network)."""
import httpx
import pytest

from airaa.tools.coinmarketcap import coinmarketcap_tool
from airaa.tools.defillama import defillama_tool
from airaa.tools.dune import dune_analytics_tool
from airaa.tools.etherscan import etherscan_tool

from .conftest import run

ADDRESS = "0x" + "12" * 20


@pytest.fixture(autouse=True)
def _keys(monkeypatch):
    monkeypatch.setenv("COINMARKETCAP_API_KEY", "k")
    monkeypatch.setenv("ETHERSCAN_API_KEY", "e")
    monkeypatch.setenv("DUNE_API_KEY", "d")


def json_response(payload, status=200):
    return httpx.Response(status, json=payload)


# ------------------------------------------------------------------ DefiLlama
def test_defillama_selects_only_requested_sections(mock_http):
    def handler(req):
        if "v2/chains" in req.url.path:
            return json_response([{"name": "Ethereum", "tvl": 100}, {"name": "Tron", "tvl": 50}])
        return json_response({}, 404)

    seen = mock_http(handler)
    out = run(defillama_tool.ainvoke({"query": "total value locked by chain"}))
    hosts = {r.url.host for r in seen}
    assert out["success"] and out["data"]["tvl"]["top_chains"][0]["name"] == "Ethereum"
    assert "yields.llama.fi" not in hosts and "stablecoins.llama.fi" not in hosts  # no wasted downloads


def test_defillama_parses_stablecoins_and_yields_shapes(mock_http):
    def handler(req):
        if req.url.host == "stablecoins.llama.fi":
            return json_response({"peggedAssets": [
                {"name": "Tether", "symbol": "USDT", "circulating": {"peggedUSD": 100}},
                {"name": "USD Coin", "symbol": "USDC", "circulating": {"peggedUSD": 200}}]})
        return json_response({"status": "success", "data": [
            {"project": "a", "chain": "Ethereum", "symbol": "X", "apy": 12.3456, "tvlUsd": 6e6, "stablecoin": True},
            {"project": "flagged", "chain": "Ethereum", "symbol": "F", "apy": 99, "tvlUsd": 9e6, "stablecoin": True, "outlier": True},
            {"project": "dust", "chain": "Ethereum", "symbol": "Y", "apy": 900, "tvlUsd": 10, "stablecoin": False},
            {"project": "b", "chain": "Base", "symbol": "Z", "apy": 8, "tvlUsd": 6e6, "stablecoin": False}]})

    mock_http(handler)
    out = run(defillama_tool.ainvoke({"query": "best stablecoin yield apy"}))
    stable, yields = out["data"]["stablecoins"], out["data"]["yields"]
    assert stable["top_assets"][0]["symbol"] == "USDC"          # sorted by circulating supply
    assert [p["project"] for p in yields["top_pools"]] == ["a"]  # dust, outlier-flagged and non-stable pools filtered


def test_defillama_protocol_summary(mock_http):
    series = [{"date": i, "totalLiquidityUSD": 100 + i} for i in range(10)]

    def handler(req):
        if req.url.path == "/protocol/aave":
            return json_response({"name": "Aave", "category": "Lending", "chains": ["Ethereum"], "tvl": series,
                                  "currentChainTvls": {"Ethereum": 109}, "mcap": 5})
        return json_response({}, 404)

    mock_http(handler)
    out = run(defillama_tool.ainvoke({"query": "aave tvl", "protocols": ["aave"]}))
    data = out["data"]
    assert data["type"] == "protocol_tvl" and data["tvl_usd"] == 109
    assert data["tvl_change_7d_pct"] == round((109 - 102) / 102 * 100, 2)


def test_defillama_rejects_path_injection_slug(mock_http):
    mock_http(lambda r: json_response({}))
    out = run(defillama_tool.ainvoke({"query": "tvl", "protocols": ["../../etc/passwd"]}))
    assert not out["success"] and "Invalid protocol slug" in out["error"]


def test_defillama_compares_multiple_protocols(mock_http):
    mock_http(lambda r: json_response({"name": r.url.path.rsplit("/", 1)[-1], "tvl": [{"totalLiquidityUSD": 1}]}))
    out = run(defillama_tool.ainvoke({"query": "compare", "protocols": ["aave", "lido"]}))
    assert out["data"]["type"] == "protocol_tvl_list" and len(out["data"]["protocols"]) == 2


# ------------------------------------------------------------------ CoinMarketCap
def test_cmc_quotes_every_requested_symbol(mock_http):
    seen = mock_http(lambda r: json_response({"data": {}}))
    out = run(coinmarketcap_tool.ainvoke({"query": "compare", "symbols": ["btc", "sol"]}))
    assert out["success"] and out["metadata"]["symbols"] == ["BTC", "SOL"]
    assert seen[0].url.params["symbol"] == "BTC,SOL" and seen[0].headers["X-CMC_PRO_API_KEY"] == "k"


def test_cmc_requires_a_key(monkeypatch):
    monkeypatch.delenv("COINMARKETCAP_API_KEY", raising=False)
    out = run(coinmarketcap_tool.ainvoke({"query": "price of btc"}))
    assert not out["success"] and "not configured" in out["error"]


def test_cmc_surfaces_api_error_message(mock_http):
    mock_http(lambda r: json_response({"status": {"error_message": "Plan limit"}}, 403))
    out = run(coinmarketcap_tool.ainvoke({"query": "price of eth"}))
    assert out["error"] == "Plan limit"


def test_cmc_picks_listings_without_symbols(mock_http):
    seen = mock_http(lambda r: json_response({"data": []}))
    run(coinmarketcap_tool.ainvoke({"query": "global market overview"}))
    assert seen[0].url.path.endswith("/global-metrics/quotes/latest")


# ------------------------------------------------------------------ Etherscan
def test_etherscan_uses_v2_with_chainid(mock_http):
    seen = mock_http(lambda r: json_response({"status": "1", "message": "OK", "result": "5"}))
    out = run(etherscan_tool.ainvoke({"query": "balance", "address": ADDRESS, "chain": "base"}))
    assert out["success"]
    assert seen[0].url.path == "/v2/api" and seen[0].url.params["chainid"] == "8453"
    assert seen[0].url.params["action"] == "balance"


def test_etherscan_maps_api_level_errors(mock_http):
    mock_http(lambda r: json_response({"status": "0", "message": "NOTOK", "result": "Invalid API Key"}))
    out = run(etherscan_tool.ainvoke({"query": "transactions", "address": ADDRESS}))
    assert not out["success"] and "Invalid API Key" in out["error"]


def test_etherscan_empty_history_is_not_an_error(mock_http):
    mock_http(lambda r: json_response({"status": "0", "message": "No transactions found", "result": []}))
    assert run(etherscan_tool.ainvoke({"query": "transactions", "address": ADDRESS}))["success"]


def test_etherscan_validates_address_and_chain(mock_http):
    mock_http(lambda r: json_response({}))
    assert "valid 0x" in run(etherscan_tool.ainvoke({"query": "balance", "address": "nope"}))["error"]
    assert "not supported" in run(etherscan_tool.ainvoke({"query": "balance", "address": ADDRESS, "chain": "solana"}))["error"]


# ------------------------------------------------------------------ Dune
def test_dune_reads_the_dex_pairs_query_with_chain_filter(mock_http):
    seen = mock_http(lambda r: json_response({
        "execution_ended_at": "2026-08-03T03:40:04Z", "result": {"rows": [{"token_pair": "A-B", "one_day_volume": 1}]}}))
    out = run(dune_analytics_tool.ainvoke({"query": "dex trading pairs on bsc"}))
    assert out["success"] and out["metadata"]["as_of"] == "2026-08-03T03:40:04Z"
    req = seen[0]
    assert req.url.path == "/api/v1/query/3568055/results"
    assert req.url.params["filters"] == "chain = 'bnb'" and req.url.params["sort_by"] == "one_day_volume desc"


def test_dune_validates_token_address_before_building_a_filter(mock_http):
    seen = mock_http(lambda r: json_response({"result": {"rows": [{"token_pair": "A-B"}]}}))
    bad = run(dune_analytics_tool.ainvoke({"query": "dex pairs for this token address", "address": "'; drop"}))
    assert not bad["success"] and "Invalid token address" in bad["error"] and not seen
    good = run(dune_analytics_tool.ainvoke({"query": "dex pairs for this token address", "address": "0x" + "AB" * 20}))
    assert good["success"] and ("token_a_address = '0x" + "ab" * 20 + "'") in seen[0].url.params["filters"]


def test_dune_reports_chains_without_data(mock_http):
    mock_http(lambda r: json_response({}))
    out = run(dune_analytics_tool.ainvoke({"query": "dex volume", "chain": "tron"}))
    assert not out["success"] and "not available for chain" in out["error"]


def test_dune_rejects_unsupported_questions(mock_http):
    mock_http(lambda r: json_response({}))
    out = run(dune_analytics_tool.ainvoke({"query": "tell me a joke"}))
    assert not out["success"] and "only supports" in out["error"]
