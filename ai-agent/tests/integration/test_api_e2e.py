"""The whole HTTP surface against real services on real Postgres: SIWE sign-in, ownership, memory dashboard, watchlist,
sealed storage, sharing, alerts (including the scheduler hook and the runner), data export and erasure.

Only the LLM, the embedding model and the market-data tools are faked.
"""
from __future__ import annotations

import base64
import time
import uuid

import pytest

from airaa.agent.core import Web3ResearchAgent
from airaa.api import create_app
from airaa.config import Settings
from airaa.memory import SessionManager
from airaa.db.store import ConversationStore
from airaa.schemas import Entities, Plan
from airaa.services import build_services

from ..conftest import FakePlannerLLM, FakeSynthesisLLM, FakeTool
from ..helpers import DOMAIN, FakeEmbedder, new_account, siwe_message, sign

b64 = lambda raw: base64.b64encode(raw).decode()  # noqa: E731
CMC_OK = {"success": True, "source": "coinmarketcap", "data": {"data": {"ETH": {
    "id": 2, "name": "Ethereum", "symbol": "ETH", "quote": {"USD": {"price": 3000.5}}}}}}
CRON = "cron-secret-value"


@pytest.fixture
def env(pool, monkeypatch, patch_tools):
    settings = Settings(gemini_api_key="t", jwt_secret="x" * 40, siwe_domains=(DOMAIN,), rate_limit_per_minute=0,
                        cron_secret=CRON, max_artifact_bytes=4096, memory_min_similarity=0.2, kb_min_similarity=0.2)
    services = build_services(settings, pool)
    embedder = FakeEmbedder()
    services.embedder = embedder
    for part in (services.memories, services.kb, services.cache, services.context, services.vault):
        part.embedder = embedder
    services.retrieval.embedder = embedder
    sessions = SessionManager(max_sessions=50, store=ConversationStore(pool))
    monkeypatch.setattr("airaa.api.routes.get_session_manager", lambda: sessions)
    patch_tools(coinmarketcap_tool=FakeTool(CMC_OK))
    synthesis = FakeSynthesisLLM(["ETH is ", "$3,000.50."])

    def factory(session_id):
        return Web3ResearchAgent(
            session_id, sessions=sessions, settings=settings, retrieval=services.retrieval, cache=services.cache,
            planner_llm=FakePlannerLLM(plan=Plan(intent="market_data", tools=["coinmarketcap_tool"], entities=Entities(symbols=["ETH"]))),
            synthesis_model=synthesis)

    app = create_app(settings, agent_factory=factory, services=services)
    return app.test_client(), services, sessions, synthesis


def sign_in(client, acct=None):
    acct = acct or new_account()
    nonce = client.get("/api/auth/nonce").get_json()["nonce"]
    text = siwe_message(acct.address, nonce)
    res = client.post("/api/auth/verify", json={"message": text, "signature": sign(acct, text)}, headers={"Origin": "http://localhost:3000"})
    assert res.status_code == 200, res.get_json()
    body = res.get_json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["wallet"], acct


# ----------------------------------------------------------------------- sign-in and sessions persist in Postgres
def test_sign_in_refresh_rotation_and_logout_against_postgres(env):
    client, services, _, _ = env
    headers, wallet, _ = sign_in(client)
    assert client.get("/api/me", headers=headers).get_json()["wallet"]["id"] == wallet["id"]
    origin = {"Origin": "http://localhost:3000"}

    old_cookie = client.get_cookie("airaa_refresh", path="/api/auth").value
    assert client.post("/api/auth/refresh", headers=origin).status_code == 200
    assert client.get_cookie("airaa_refresh", path="/api/auth").value != old_cookie                  # rotated
    newest = client.get_cookie("airaa_refresh", path="/api/auth").value

    client.set_cookie("airaa_refresh", old_cookie, path="/api/auth")               # an attacker replays the stolen old token
    assert client.post("/api/auth/refresh", headers=origin).status_code == 401
    client.set_cookie("airaa_refresh", newest, path="/api/auth")                   # the family is burned: the real one is dead too
    assert client.post("/api/auth/refresh", headers=origin).status_code == 401

    other, _, _ = sign_in(client)
    assert client.post("/api/auth/logout", headers=origin).status_code == 200
    assert client.post("/api/auth/refresh", headers=origin).status_code == 401


def test_conversation_persists_and_is_private(env):
    client, services, sessions, _ = env
    alice, wallet, _ = sign_in(client)
    bob, _, _ = sign_in(client)
    sid = "persisted-" + uuid.uuid4().hex[:10]
    assert client.post("/api/research", json={"query": "price of eth", "session_id": sid}, headers=alice).status_code == 200

    fresh = SessionManager(store=ConversationStore(services.pool))                   # "another worker" with a cold cache
    restored = fresh.get(sid)
    assert restored["wallet_id"] == wallet["id"] and restored["message_count"] == 2
    assert client.get(f"/api/conversation/{sid}", headers=bob).status_code == 404
    assert client.get(f"/api/conversation/{sid}", headers=alice).get_json()["message_count"] == 2
    assert [c["id"] for c in client.get("/api/conversations", headers=alice).get_json()["conversations"]] == [sid]


# ----------------------------------------------------------------------- memory, watchlist, personalisation
def test_memory_dashboard_and_recall_reach_the_prompt(env):
    client, services, _, synthesis = env
    headers, wallet, _ = sign_in(client)
    added = client.post("/api/memories", json={"kind": "fact", "content": "The user holds a large ETH position on Arbitrum", "pinned": True}, headers=headers)
    assert added.status_code == 201
    memory_id = added.get_json()["id"]

    listed = client.get("/api/memories", headers=headers).get_json()
    assert listed["total"] == 1 and listed["memories"][0]["pinned"] is True and "embedding" not in listed["memories"][0]

    body = client.post("/api/research", json={"query": "how is my ETH position on Arbitrum doing", "session_id": "recall-" + uuid.uuid4().hex[:8]},
                       headers=headers).get_json()
    assert body["personalization"]["memories"] == 1
    assert "The user holds a large ETH position on Arbitrum" in synthesis.calls[-1][-1].content

    edited = client.patch(f"/api/memories/{memory_id}", json={"content": "The user now holds SOL", "importance": 0.2}, headers=headers)
    assert edited.get_json()["memory"]["content"] == "The user now holds SOL"
    assert client.patch(f"/api/memories/{memory_id}", json={}, headers=headers).status_code == 400
    assert client.patch(f"/api/memories/{memory_id}", json={"importance": 4}, headers=headers).status_code == 400

    assert client.patch("/api/me/settings", json={"memory_enabled": False}, headers=headers).status_code == 200
    off = client.post("/api/research", json={"query": "how is my ETH position on Arbitrum doing", "session_id": "off-" + uuid.uuid4().hex[:8]}, headers=headers).get_json()
    assert "personalization" not in off                                              # opted out: nothing recalled

    stranger, _, _ = sign_in(client)
    assert client.delete(f"/api/memories/{memory_id}", headers=stranger).status_code == 404
    assert client.delete("/api/memories", json={}, headers=headers).status_code == 400    # needs explicit confirmation
    assert client.delete("/api/memories", json={"confirm": True}, headers=headers).get_json()["deleted"] == 1


def test_watchlist_reaches_the_prompt(env):
    client, _, _, synthesis = env
    headers, _, _ = sign_in(client)
    added = client.post("/api/watchlist", json={"entity_type": "protocol", "entity_id": "Aave", "note": "lending exposure"}, headers=headers)
    assert added.status_code == 201 and added.get_json()["item"]["entity_id"] == "aave"
    assert client.post("/api/watchlist", json={"entity_type": "bogus", "entity_id": "x"}, headers=headers).status_code == 400
    client.post("/api/research", json={"query": "news on aave lending exposure", "session_id": "watch-" + uuid.uuid4().hex[:8]}, headers=headers)
    prompt = synthesis.calls[-1][-1].content
    assert "USER WATCHLIST: protocols: aave" in prompt and "aave: lending exposure" in prompt
    item_id = client.get("/api/watchlist", headers=headers).get_json()["items"][0]["id"]
    assert client.delete(f"/api/watchlist/{item_id}", headers=headers).status_code == 200
    assert client.get("/api/watchlist").status_code == 401


def test_knowledge_base_passages_are_cited_in_the_prompt(env):
    client, services, _, synthesis = env
    services.kb.ingest_document("docs", "https://docs.test/liquidations", "Liquidations", "A position is liquidated when its health factor falls below one.")
    body = client.post("/api/research", json={"query": "when is a position liquidated health factor", "session_id": "kb-" + uuid.uuid4().hex[:8]}).get_json()
    assert body["knowledge_sources"][0]["url"] == "https://docs.test/liquidations"
    assert "REFERENCE DOCUMENTATION" in synthesis.calls[-1][-1].content


def test_semantic_cache_serves_the_second_identical_question(env, patch_tools):
    client, services, _, _ = env
    tool = FakeTool(CMC_OK)
    patch_tools(coinmarketcap_tool=tool)
    query = "cache probe price of ETH " + uuid.uuid4().hex[:6]
    for _ in range(2):
        client.post("/api/research", json={"query": query, "session_id": "cache-" + uuid.uuid4().hex[:8]})
    assert len(tool.calls) == 1


# ----------------------------------------------------------------------- sealed storage and sharing
def test_vault_roundtrip_ownership_and_link_share(env):
    client, services, sessions, _ = env
    alice, _, _ = sign_in(client)
    bob, _, _ = sign_in(client)

    assert client.get("/api/vault", headers=alice).get_json()["initialized"] is False
    no_vault = client.post("/api/artifacts", json={"ciphertext": b64(b"x" * 64), "wrapped_cek": b64(b"k" * 40)}, headers=alice)
    assert no_vault.status_code == 409

    assert client.put("/api/vault/keys/signature", json={"wrapped_dek": b64(b"d" * 48), "kdf": {"v": 1}}, headers=alice).status_code == 200
    assert client.put("/api/vault/keys/nonsense", json={"wrapped_dek": b64(b"d" * 48)}, headers=alice).status_code == 404
    vault = client.get("/api/vault", headers=alice).get_json()
    assert vault["initialized"] and vault["keys"][0]["wrapped_dek"] == b64(b"d" * 48)
    assert client.get("/api/vault", headers=bob).get_json()["keys"] == []

    aid, ciphertext = str(uuid.uuid4()), bytes(range(200))
    created = client.post("/api/artifacts", json={"id": aid, "ciphertext": b64(ciphertext), "wrapped_cek": b64(b"c" * 48),
                                                  "meta_enc": b64(b"m" * 30)}, headers=alice)
    assert created.status_code == 201
    assert client.get(f"/api/artifacts/{aid}/blob", headers=alice).data == ciphertext
    assert client.get(f"/api/artifacts/{aid}/blob", headers=bob).status_code == 404
    assert client.get(f"/api/artifacts/{aid}/blob").status_code == 401
    assert [a["id"] for a in client.get("/api/artifacts", headers=alice).get_json()["artifacts"]] == [aid]
    too_big = client.post("/api/artifacts", json={"ciphertext": b64(b"x" * 5000), "wrapped_cek": b64(b"k" * 40)}, headers=alice)
    assert too_big.status_code == 400

    share = client.post("/api/shares", json={"resource_type": "artifact", "resource_id": aid, "wrapped_key": b64(b"w" * 48), "ttl_hours": 2}, headers=alice)
    assert share.status_code == 201
    token, share_id = share.get_json()["share"]["token"], share.get_json()["share"]["id"]
    opened = client.get(f"/api/share/{token}").get_json()                              # no auth: anyone with the link
    assert opened["type"] == "artifact" and opened["ciphertext"] == b64(ciphertext) and opened["wrapped_key"] == b64(b"w" * 48)
    assert client.get(f"/api/share/{token}x").status_code == 404
    assert client.post("/api/shares", json={"resource_type": "artifact", "resource_id": aid, "wrapped_key": b64(b"w" * 48)}, headers=bob).status_code == 404
    assert client.post("/api/shares", json={"resource_type": "artifact", "resource_id": aid, "mode": "wallet",
                                            "recipient_address": "0x" + "ab" * 20, "wrapped_key": b64(b"w")}, headers=alice).status_code == 400
    assert client.delete(f"/api/shares/{share_id}", headers=bob).status_code == 404
    assert client.delete(f"/api/shares/{share_id}", headers=alice).status_code == 200
    assert client.get(f"/api/share/{token}").status_code == 404                        # revoked

    assert client.delete(f"/api/artifacts/{aid}", headers=bob).status_code == 404
    assert client.delete(f"/api/artifacts/{aid}", headers=alice).status_code == 200
    assert client.get(f"/api/artifacts/{aid}/blob", headers=alice).status_code == 404


def test_conversation_shares_by_link_and_by_wallet(env):
    client, services, sessions, _ = env
    alice, _, _ = sign_in(client)
    bob, _, bob_acct = sign_in(client)
    carol, _, _ = sign_in(client)
    sid = "shared-" + uuid.uuid4().hex[:10]
    client.post("/api/research", json={"query": "price of eth", "session_id": sid}, headers=alice)

    assert client.post("/api/shares", json={"resource_type": "conversation", "resource_id": sid}, headers=bob).status_code == 404

    link = client.post("/api/shares", json={"resource_type": "conversation", "resource_id": sid, "redact_research_data": True}, headers=alice).get_json()["share"]
    page = client.get(f"/api/share/{link['token']}").get_json()
    assert page["type"] == "conversation" and page["message_count"] == 2
    assert all("research_data" not in m for m in page["messages"])                      # redacted

    wallet_share = client.post("/api/shares", json={"resource_type": "conversation", "resource_id": sid, "mode": "wallet",
                                                    "recipient_address": bob_acct.address}, headers=alice)
    assert wallet_share.status_code == 201
    assert client.get(f"/api/shared/conversation/{sid}", headers=bob).get_json()["message_count"] == 2
    assert client.get(f"/api/shared/conversation/{sid}", headers=carol).status_code == 404
    assert client.get("/api/shares/received", headers=bob).get_json()["shares"][0]["resource_id"] == sid
    assert client.get(f"/api/conversation/{sid}", headers=bob).status_code == 404       # sharing grants a read view, not ownership


# ----------------------------------------------------------------------- alerts
def test_alert_rules_scheduler_hook_and_inbox(env, pool, monkeypatch):
    client, services, sessions, _ = env
    headers, wallet, _ = sign_in(client)

    assert client.post("/api/alerts", json={"name": "x", "query_text": "ETH", "interval_minutes": 5}, headers=headers).status_code == 400
    made = client.post("/api/alerts", json={"name": "ETH check", "query_text": "price of eth", "interval_minutes": 15,
                                            "condition_text": "price above 100"}, headers=headers)
    assert made.status_code == 201
    rule_id = made.get_json()["alert"]["id"]
    assert client.patch(f"/api/alerts/{rule_id}", json={"interval_minutes": 60}, headers=headers).get_json()["alert"]["interval_minutes"] == 60
    assert client.get("/api/alerts", headers=headers).get_json()["alerts"][0]["id"] == rule_id

    assert client.post("/api/internal/alerts/run").status_code == 403                    # wrong/missing secret
    assert client.post("/api/internal/alerts/run", headers={"X-Cron-Secret": "wrong"}).status_code == 403

    # Run the scheduler hook for real; the agent and judge are the test doubles wired into the services.
    from airaa.alerts import runner

    def fake_agent(session_id, svc):
        return Web3ResearchAgent(
            session_id, sessions=SessionManager(), settings=svc.settings, retrieval=svc.retrieval, cache=None,
            planner_llm=FakePlannerLLM(plan=Plan(intent="market_data", tools=["coinmarketcap_tool"], entities=Entities(symbols=["ETH"]))),
            synthesis_model=FakeSynthesisLLM(["ETH is $3,000."]))

    class Judge:
        class Runner:
            async def ainvoke(self, messages):
                from airaa.alerts.runner import Verdict
                return Verdict(notify=True, reason="Price is above 100.")

        def with_structured_output(self, schema):
            return self.Runner()

    with pool.connection() as conn:
        conn.execute("update alert_rules set next_run_at = now() - interval '1 minute' where id = %s", (rule_id,))
    counts = runner.run_due(services, make_agent=fake_agent, judge_llm=Judge())
    assert counts["claimed"] >= 1 and counts["notified"] >= 1 and counts["failed"] == 0

    inbox = client.get("/api/inbox", headers=headers).get_json()
    assert inbox["unread"] == 1 and inbox["items"][0]["title"] == "ETH check" and "Price is above 100." in inbox["items"][0]["summary"]
    assert not any(s["id"].startswith("alert-") for s in client.get("/api/conversations", headers=headers).get_json()["conversations"])   # no chat clutter
    assert client.get("/api/memories", headers=headers).get_json()["total"] == 0          # automated runs never write memory
    item_id = inbox["items"][0]["id"]
    assert client.post("/api/inbox/read", json={"id": item_id}, headers=headers).get_json()["updated"] == 1
    assert client.get("/api/inbox/unread-count", headers=headers).get_json()["unread"] == 0
    assert client.delete(f"/api/inbox/{item_id}", headers=headers).status_code == 200
    assert client.delete(f"/api/alerts/{rule_id}", headers=headers).status_code == 200

    started = client.post("/api/internal/alerts/run", headers={"X-Cron-Secret": CRON})
    assert started.status_code == 202 and started.get_json()["status"] in ("started", "already_running")
    time.sleep(0.3)                                                                      # let the background thread finish cleanly


def test_alert_limits_are_enforced(env):
    client, services, _, _ = env
    headers, _, _ = sign_in(client)
    for i in range(services.settings.max_alert_rules):
        assert client.post("/api/alerts", json={"name": f"r{i}", "query_text": "ETH"}, headers=headers).status_code == 201
    assert client.post("/api/alerts", json={"name": "one too many", "query_text": "ETH"}, headers=headers).status_code == 409


def test_scheduler_hook_is_disabled_without_a_secret(pool):
    settings = Settings(gemini_api_key="t", jwt_secret="x" * 40, rate_limit_per_minute=0)
    client = create_app(settings, services=build_services(settings, pool)).test_client()
    assert client.post("/api/internal/alerts/run", headers={"X-Cron-Secret": ""}).status_code == 404


# ----------------------------------------------------------------------- export and erasure
def test_export_and_account_erasure(env, pool):
    client, services, _, _ = env
    headers, wallet, _ = sign_in(client)
    sid = "erase-" + uuid.uuid4().hex[:10]
    client.post("/api/research", json={"query": "price of eth", "session_id": sid}, headers=headers)
    client.post("/api/memories", json={"content": "The user likes DeFi"}, headers=headers)
    client.post("/api/watchlist", json={"entity_type": "token", "entity_id": "eth"}, headers=headers)
    client.put("/api/vault/keys/signature", json={"wrapped_dek": b64(b"d" * 48)}, headers=headers)
    aid = str(uuid.uuid4())
    client.post("/api/artifacts", json={"id": aid, "ciphertext": b64(b"z" * 64), "wrapped_cek": b64(b"c" * 40)}, headers=headers)

    exported = client.get("/api/me/export", headers=headers)
    assert exported.headers["Content-Disposition"].startswith("attachment")
    data = exported.get_json()
    assert data["wallet"] == wallet["address"] and data["conversations"][0]["id"] == sid
    assert data["memories"][0]["content"] == "The user likes DeFi" and data["watchlist"][0]["entity_id"] == "eth"
    assert data["sealed_files"][0]["id"] == aid and "ciphertext" not in str(data["sealed_files"])

    assert client.delete("/api/me", json={}, headers=headers).status_code == 400            # needs explicit confirmation
    assert client.delete("/api/me", json={"confirm": "DELETE"}, headers=headers).status_code == 200
    with pool.connection() as conn:
        for table, col in (("wallets", "id"), ("conversations", "wallet_id"), ("memories", "wallet_id"), ("watchlist", "wallet_id"),
                           ("artifacts", "wallet_id"), ("vault_keys", "wallet_id"), ("auth_sessions", "wallet_id")):
            assert conn.execute(f"select count(*) as n from {table} where {col} = %s", (wallet["id"],)).fetchone()["n"] == 0
        assert conn.execute("select count(*) as n from artifact_blobs where path like %s", (f"sealed/{wallet['id']}/%",)).fetchone()["n"] == 0
