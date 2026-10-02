import json

import pytest

from airaa.agent.core import Web3ResearchAgent
from airaa.api import create_app
from airaa.config import Settings
from airaa.schemas import Entities, Plan

from .conftest import FakePlannerLLM, FakeSynthesisLLM, FakeTool

ADDRESS = "0x" + "ef" * 20
CMC_OK = {"success": True, "source": "coinmarketcap", "data": {"data": {"ETH": {
    "id": 2, "name": "Ethereum", "symbol": "ETH", "quote": {"USD": {"price": 3000.5}}}}}}


@pytest.fixture
def client(settings, sessions, patch_tools, monkeypatch):
    patch_tools(coinmarketcap_tool=FakeTool(CMC_OK))
    monkeypatch.setattr("airaa.api.routes.get_session_manager", lambda: sessions)

    def factory(session_id):
        return Web3ResearchAgent(
            session_id, sessions=sessions, settings=settings,
            planner_llm=FakePlannerLLM(plan=Plan(intent="market_data", tools=["coinmarketcap_tool"], entities=Entities(symbols=["ETH"]))),
            synthesis_model=FakeSynthesisLLM(["ETH is ", "$3,000.50."]),
        )

    return create_app(settings, agent_factory=factory).test_client()


def post(client, payload, path="/api/research"):
    return client.post(path, json=payload)


# ------------------------------------------------------------------ validation
@pytest.mark.parametrize("payload,fragment", [
    ({}, "query"),
    ({"query": "   "}, "query"),
    ({"query": "x" * 1001}, "at most"),
    ({"query": "hi", "address": "0x123"}, "address"),
    ({"query": "hi", "time_range": "forever"}, "time_range"),
    ({"query": "hi", "session_id": "bad id!"}, "session_id"),
    ([], "JSON object"),
])
def test_bad_requests_are_rejected_with_400(client, payload, fragment):
    res = post(client, payload)
    assert res.status_code == 400 and fragment in res.get_json()["error"]


def test_empty_address_and_session_are_treated_as_absent(client):
    res = post(client, {"query": "price of eth", "address": "", "session_id": ""})
    assert res.status_code == 200


# ------------------------------------------------------------------ research
def test_research_returns_result_and_session(client):
    body = post(client, {"query": "price of eth", "session_id": "web-1700000000-abc123", "address": ADDRESS}).get_json()
    assert body["success"] and body["session_id"] == "web-1700000000-abc123"
    assert body["result"].startswith("ETH is $3,000.50.") and body["tool_trace"][0]["success"]


def test_stream_emits_sse_events_ending_with_result(client):
    res = post(client, {"query": "price of eth"}, "/api/research/stream")
    assert res.status_code == 200 and res.mimetype == "text/event-stream"
    events = [json.loads(line[6:]) for line in res.get_data(as_text=True).splitlines() if line.startswith("data: ")]
    kinds = [e["type"] for e in events]
    assert kinds[0] == "status" and kinds[-1] == "result" and "plan" in kinds and "token" in kinds
    assert events[-1]["result"]["success"]


def test_stream_validates_before_streaming(client):
    assert post(client, {}, "/api/research/stream").status_code == 400


def test_conversation_roundtrip_and_delete(client):
    sid = "web-1700000000-roundtrip"
    post(client, {"query": "price of eth", "session_id": sid})
    conv = client.get(f"/api/conversation/{sid}").get_json()
    assert conv["message_count"] == 2 and conv["messages"][1]["research_data"]["success"]
    assert client.delete(f"/api/conversation/{sid}").get_json()["deleted"] is True
    assert client.get(f"/api/conversation/{sid}").status_code == 404
    assert client.get("/api/conversation/bad id").status_code in (400, 404)


# ------------------------------------------------------------------ meta + safety
def test_health_reports_models_and_configured_sources_but_no_secrets(client):
    body = client.get("/api/health").get_json()
    assert body["status"] == "ok" and body["models"]["synthesis"]
    assert body["sources"]["defillama"] is True
    assert all(isinstance(v, bool) for v in body["sources"].values())


def test_tools_listing(client):
    names = {t["name"] for t in client.get("/api/tools").get_json()["tools"]}
    assert "coinmarketcap_tool" in names


def test_session_listing_is_disabled_without_admin_token(client):
    assert client.get("/api/sessions").status_code == 404


def test_session_listing_requires_the_admin_token(settings, sessions, monkeypatch):
    monkeypatch.setattr("airaa.api.routes.get_session_manager", lambda: sessions)
    cfg = Settings(**{**settings.__dict__, "admin_token": "s3cret"})
    c = create_app(cfg, agent_factory=lambda sid: None).test_client()
    assert c.get("/api/sessions").status_code == 403
    assert c.get("/api/sessions", headers={"X-Admin-Token": "nope"}).status_code == 403
    assert c.get("/api/sessions", headers={"X-Admin-Token": "s3cret"}).get_json()["success"]


def test_rate_limit_returns_429_with_retry_after(settings, sessions, monkeypatch):
    monkeypatch.setattr("airaa.api.routes.get_session_manager", lambda: sessions)
    cfg = Settings(**{**settings.__dict__, "rate_limit_per_minute": 2})
    c = create_app(cfg, agent_factory=lambda sid: None).test_client()
    for _ in range(2):
        assert c.post("/api/research", json={}).status_code == 400  # counted, then rejected by validation
    limited = c.post("/api/research", json={})
    assert limited.status_code == 429 and int(limited.headers["Retry-After"]) >= 1


def test_cors_allows_configured_origin_only(settings):
    cfg = Settings(**{**settings.__dict__, "allowed_origins": "https://app.example"})
    c = create_app(cfg, agent_factory=lambda sid: None).test_client()
    ok = c.get("/api/health", headers={"Origin": "https://app.example"})
    bad = c.get("/api/health", headers={"Origin": "https://evil.example"})
    assert ok.headers.get("Access-Control-Allow-Origin") == "https://app.example"
    assert "Access-Control-Allow-Origin" not in bad.headers


def test_unknown_route_is_json_404(client):
    res = client.get("/nope")
    assert res.status_code == 404 and res.get_json()["success"] is False
