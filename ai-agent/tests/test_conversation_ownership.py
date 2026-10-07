"""Wallet-owned conversations: private to their wallet, guests keep working, guest conversations can be claimed."""
from __future__ import annotations

import pytest

from airaa.agent.core import Web3ResearchAgent
from airaa.api import create_app
from airaa.auth import AuthService
from airaa.config import Settings
from airaa.schemas import Entities, Plan
from airaa.services import Services

from .conftest import FakePlannerLLM, FakeSynthesisLLM, FakeTool
from .helpers import DOMAIN, FakeAuthRepo, new_account, siwe_message, sign

CMC_OK = {"success": True, "source": "coinmarketcap", "data": {"data": {"ETH": {
    "id": 2, "name": "Ethereum", "symbol": "ETH", "quote": {"USD": {"price": 3000.5}}}}}}


class SpyRetrieval:
    """Records what the API layer hands the agent."""

    def __init__(self):
        self.requests = []

    async def build(self, request):
        from airaa.retrieval import Retrieved

        self.requests.append(request)
        return Retrieved(summary="- likes L2s", blocks="USER CONTEXT: watches ETH", used={"memories": 1})

    def remember(self, request, answer, llm_factory):
        self.remembered = (request.wallet_id, request.session_id, answer)


@pytest.fixture
def env(monkeypatch, patch_tools, sessions):
    settings = Settings(gemini_api_key="t", jwt_secret="x" * 40, siwe_domains=(DOMAIN,), rate_limit_per_minute=0)
    repo = FakeAuthRepo()
    spy = SpyRetrieval()
    services = Services(settings=settings, auth_repo=repo, auth=AuthService(repo, settings), retrieval=spy)
    patch_tools(coinmarketcap_tool=FakeTool(CMC_OK))
    monkeypatch.setattr("airaa.api.routes.get_session_manager", lambda: sessions)
    synthesis = FakeSynthesisLLM(["ETH is ", "$3,000.50."])

    def factory(session_id):
        return Web3ResearchAgent(
            session_id, sessions=sessions, settings=settings, retrieval=spy, cache=None,
            planner_llm=FakePlannerLLM(plan=Plan(intent="market_data", tools=["coinmarketcap_tool"], entities=Entities(symbols=["ETH"]))),
            synthesis_model=synthesis,
        )

    app = create_app(settings, agent_factory=factory, services=services)
    return app.test_client(), sessions, spy, synthesis


def token_for(client, acct=None):
    acct = acct or new_account()
    nonce = client.get("/api/auth/nonce").get_json()["nonce"]
    text = siwe_message(acct.address, nonce)
    body = client.post("/api/auth/verify", json={"message": text, "signature": sign(acct, text)}).get_json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["wallet"]


def ask(client, session_id, headers=None, query="price of eth"):
    return client.post("/api/research", json={"query": query, "session_id": session_id}, headers=headers or {})


def test_wallet_conversation_is_private_to_the_wallet(env):
    client, sessions, _, _ = env
    alice, wallet = token_for(client)
    bob, _ = token_for(client)
    sid = "alice-conversation-1"

    assert ask(client, sid, alice).status_code == 200
    assert sessions.get(sid)["wallet_id"] == wallet["id"]

    assert client.get(f"/api/conversation/{sid}", headers=alice).status_code == 200
    assert client.get(f"/api/conversation/{sid}").status_code == 404           # a guest holding the id gets nothing
    assert client.get(f"/api/conversation/{sid}", headers=bob).status_code == 404
    assert ask(client, sid, bob).status_code == 404                              # nor can they write to it
    assert ask(client, sid).status_code == 404
    assert client.delete(f"/api/conversation/{sid}", headers=bob).status_code == 404
    assert sessions.get(sid) is not None                                         # still there
    assert client.delete(f"/api/conversation/{sid}", headers=alice).get_json()["deleted"] is True


def test_guest_flow_is_unchanged(env):
    client, sessions, spy, _ = env
    sid = "guest-conversation-1"
    assert ask(client, sid).status_code == 200
    assert sessions.get(sid)["wallet_id"] is None
    assert client.get(f"/api/conversation/{sid}").status_code == 200
    assert spy.requests[-1].wallet_id is None                                    # no personalisation for guests


def test_signing_in_claims_the_guest_conversation_in_use(env):
    client, sessions, _, _ = env
    sid = "guest-then-wallet-1"
    ask(client, sid)
    alice, wallet = token_for(client)

    assert ask(client, sid, alice).status_code == 200                            # continuing it as a wallet claims it
    assert sessions.get(sid)["wallet_id"] == wallet["id"]
    assert client.get(f"/api/conversation/{sid}").status_code == 404             # now private


def test_explicit_claim_and_listing(env):
    client, sessions, _, _ = env
    ask(client, "guest-claim-me-1")
    ask(client, "guest-claim-me-2", query="price of eth again")
    alice, _ = token_for(client)
    bob, _ = token_for(client)

    assert client.post("/api/conversations/claim", json={"session_id": "guest-claim-me-1"}, headers=alice).status_code == 200
    assert client.post("/api/conversations/claim", json={"session_id": "guest-claim-me-1"}, headers=bob).status_code == 404   # taken
    assert client.post("/api/conversations/claim", json={"session_id": "does-not-exist-1"}, headers=alice).status_code == 404
    assert client.post("/api/conversations/claim", json={"session_id": "guest-claim-me-1"}).status_code == 401

    listed = client.get("/api/conversations", headers=alice).get_json()["conversations"]
    assert [c["id"] for c in listed] == ["guest-claim-me-1"] and listed[0]["title"] == "price of eth"
    assert client.get("/api/conversations", headers=bob).get_json()["conversations"] == []
    assert client.get("/api/conversations").status_code == 401


def test_wallet_context_reaches_the_agent_and_the_prompt(env):
    client, _, spy, synthesis = env
    alice, wallet = token_for(client)
    body = ask(client, "personalised-chat-1", alice).get_json()

    request = spy.requests[-1]
    assert request.wallet_id == wallet["id"] and request.memory_enabled is True and request.user_context == "- likes L2s"
    assert body["personalization"] == {"memories": 1}
    human = synthesis.calls[-1][-1].content
    assert "USER CONTEXT: watches ETH" in human                                  # retrieval blocks reach the synthesis prompt
    assert spy.remembered[0] == wallet["id"]                                     # and the turn is handed to memory


def test_memory_setting_is_respected(env):
    client, _, spy, _ = env
    alice, wallet = token_for(client)
    assert client.patch("/api/me/settings", json={"memory_enabled": False}, headers=alice).get_json()["settings"]["memory_enabled"] is False
    ask(client, "no-memory-chat-1", alice)
    assert spy.requests[-1].memory_enabled is False


def test_bad_token_is_a_401_not_a_silent_guest(env):
    client, _, _, _ = env
    res = ask(client, "whatever-session-1", {"Authorization": "Bearer not-a-token"})
    assert res.status_code == 401 and res.get_json()["code"] == "token_invalid"


def test_streaming_endpoint_enforces_ownership_too(env):
    client, _, _, _ = env
    alice, _ = token_for(client)
    ask(client, "stream-owned-1", alice)
    res = client.post("/api/research/stream", json={"query": "price of eth", "session_id": "stream-owned-1"})
    assert res.status_code == 404
