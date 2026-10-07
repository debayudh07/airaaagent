"""SIWE parsing/verification, token handling, the auth service and the sign-in endpoints."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from airaa.api import create_app
from airaa.auth import AuthError, AuthService
from airaa.auth import siwe
from airaa.auth.tokens import decode_access_token, issue_access_token
from airaa.config import Settings
from airaa.services import Services

from .helpers import DOMAIN, FakeAuthRepo, new_account, random_nonce, siwe_message, sign

SECRET = "x" * 40


@pytest.fixture
def auth_settings(settings) -> Settings:
    return Settings(gemini_api_key="t", jwt_secret=SECRET, siwe_domains=(DOMAIN,), rate_limit_per_minute=0)


# ----------------------------------------------------------------------- message parsing
def test_parse_message_with_and_without_statement():
    acct = new_account()
    for statement, compact in (("Sign in to AIRAA.", False), (None, False), (None, True)):
        msg = siwe.parse_message(siwe_message(acct.address, "abcdef123456", statement=statement, compact=compact))
        assert msg.address == acct.address and msg.domain == DOMAIN and msg.chain_id == 11155111
        assert msg.nonce == "abcdef123456" and msg.statement == statement


def test_message_exactly_as_viem_builds_it_parses_and_verifies():
    """Byte-for-byte what viem's createSiweMessage emits when no statement is given (two blank lines before URI)."""
    acct = new_account()
    issued = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    text = "\n".join([
        "localhost:3000 wants you to sign in with your Ethereum account:", acct.address, "", "",
        "URI: http://localhost:3000", "Version: 1", "Chain ID: 1", "Nonce: abcdef123456", f"Issued At: {issued}",
    ])
    parsed = siwe.parse_message(text)
    assert parsed.statement is None and parsed.uri == "http://localhost:3000" and parsed.resources == []
    assert siwe.verify_signature(text, sign(acct, text), acct.address, 1) == "eoa"


@pytest.mark.parametrize("mutate", [
    lambda m: m.replace("Version: 1", "Version: 2"),
    lambda m: m.replace("Nonce: ", "Nonce: !!"),
    lambda m: m.replace("Chain ID: 11155111", "Chain ID: abc"),
    lambda m: m.split("\n", 1)[1],                    # header line missing
    lambda m: m.replace("Issued At: ", "Issued At: yesterday #"),
    lambda m: "x" * 5000,
])
def test_malformed_messages_are_rejected(mutate):
    msg = siwe_message(new_account().address, "abcdef123456")
    with pytest.raises(siwe.SiweError):
        siwe.parse_message(mutate(msg))


def test_validation_binds_domain_and_time():
    acct, now = new_account(), datetime.now(timezone.utc)
    ok = siwe.parse_message(siwe_message(acct.address, "abcdef123456"))
    siwe.validate_message(ok, (DOMAIN,))

    with pytest.raises(siwe.SiweError, match="different site"):
        siwe.validate_message(siwe.parse_message(siwe_message(acct.address, "abcdef123456", domain="evil.example")), (DOMAIN,))
    stale = siwe.parse_message(siwe_message(acct.address, "abcdef123456", issued_at=now - timedelta(minutes=30)))
    with pytest.raises(siwe.SiweError, match="expired"):
        siwe.validate_message(stale, (DOMAIN,))
    future = siwe.parse_message(siwe_message(acct.address, "abcdef123456", issued_at=now + timedelta(minutes=30)))
    with pytest.raises(siwe.SiweError, match="future"):
        siwe.validate_message(future, (DOMAIN,))
    expired = siwe.parse_message(siwe_message(acct.address, "abcdef123456", expiration=now - timedelta(minutes=1)))
    with pytest.raises(siwe.SiweError, match="expired"):
        siwe.validate_message(expired, (DOMAIN,))


# ----------------------------------------------------------------------- signatures
def test_eoa_signature_verifies_and_wrong_signer_fails():
    acct, other = new_account(), new_account()
    text = siwe_message(acct.address, "abcdef123456")
    assert siwe.verify_signature(text, sign(acct, text), acct.address, 11155111) == "eoa"
    with pytest.raises(siwe.SiweError):
        siwe.verify_signature(text, sign(other, text), acct.address, 99999999)      # wrong key, no RPC for the chain


def test_garbage_signatures_are_rejected():
    acct = new_account()
    text = siwe_message(acct.address, "abcdef123456")
    for bad in ("nothex", "0x", "0xzz", "0x" + "00" * 65):
        with pytest.raises(siwe.SiweError):
            siwe.verify_signature(text, bad, acct.address, 99999999)


def test_erc1271_smart_wallet_signature(monkeypatch):
    wallet_address = "0x" + "ab" * 20
    text = siwe_message(wallet_address, "abcdef123456")
    seen = {}

    class Resp:
        def json(self):
            return {"result": "0x1626ba7e" + "00" * 28}

    def fake_post(url, json=None, timeout=None):
        seen["url"], seen["call"] = url, json["params"][0]
        return Resp()

    monkeypatch.setattr(siwe.httpx, "post", fake_post)
    signature = "0x" + "11" * 100       # smart wallets produce non-65-byte, non-recoverable signatures
    assert siwe.verify_signature(text, signature, wallet_address, 84532) == "erc1271"
    assert seen["url"] == "https://sepolia.base.org" and seen["call"]["to"] == wallet_address
    data = seen["call"]["data"]
    assert data.startswith("0x1626ba7e" + siwe.message_hash(text).hex())                 # selector + digest
    assert int(data[2 + 8 + 64: 2 + 8 + 128], 16) == 64 and int(data[2 + 8 + 128: 2 + 8 + 192], 16) == 100   # offset, length


def test_erc1271_rejection_and_rpc_failure(monkeypatch):
    address = "0x" + "ab" * 20
    text = siwe_message(address, "abcdef123456")

    class Rejects:
        def json(self):
            return {"result": "0xffffffff" + "00" * 28}

    monkeypatch.setattr(siwe.httpx, "post", lambda *a, **k: Rejects())
    with pytest.raises(siwe.SiweError, match="does not match"):
        siwe.verify_signature(text, "0x" + "11" * 100, address, 84532)

    def boom(*a, **k):
        raise siwe.httpx.ConnectError("down")

    monkeypatch.setattr(siwe.httpx, "post", boom)
    with pytest.raises(siwe.SiweError, match="try again"):
        siwe.verify_signature(text, "0x" + "11" * 100, address, 84532)


def test_undeployed_smart_wallet_gets_a_clear_message():
    address = "0x" + "ab" * 20
    with pytest.raises(siwe.SiweError, match="not deployed"):
        siwe.verify_signature(siwe_message(address, "abcdef123456"), "0x" + "11" * 40 + "6492" * 16, address, 8453)


def test_rpc_override_from_settings():
    assert siwe.rpc_url_for(8453, '{"8453": "https://my.rpc"}') == "https://my.rpc"
    assert siwe.rpc_url_for(8453, "not json") == siwe.DEFAULT_RPC_URLS[8453]
    assert siwe.rpc_url_for(424242) is None


# ----------------------------------------------------------------------- tokens
def test_access_token_roundtrip_and_tamper(auth_settings):
    token, ttl = issue_access_token(auth_settings, "wallet-1", "0xABC", 1, "sess-1")
    claims = decode_access_token(auth_settings, token)
    assert claims["sub"] == "wallet-1" and claims["wallet"] == "0xabc" and claims["aud"] == "authenticated" and ttl == 900

    from airaa.auth.tokens import TokenError

    with pytest.raises(TokenError):
        decode_access_token(auth_settings, token[:-3] + "abc")
    with pytest.raises(TokenError, match="expired"):
        expired, _ = issue_access_token(auth_settings, "w", "0x1", 1, "s", now=1_000_000)
        decode_access_token(auth_settings, expired)
    with pytest.raises(TokenError):
        decode_access_token(Settings(jwt_secret="y" * 40), token)       # signed with a different secret


# ----------------------------------------------------------------------- service
def make_service(auth_settings):
    repo = FakeAuthRepo()
    return AuthService(repo, auth_settings), repo


def login(service, acct, **msg_kwargs):
    nonce = service.issue_nonce()
    text = siwe_message(acct.address, nonce, **msg_kwargs)
    return service.login(text, sign(acct, text)), text


def test_login_creates_wallet_and_session(auth_settings):
    service, repo = make_service(auth_settings)
    acct = new_account()
    result, _ = login(service, acct)
    assert result.wallet["address"] == acct.address.lower()
    assert service.authenticate(result.access_token).address == acct.address.lower()
    assert len(repo.sessions) == 1
    again, _ = login(service, acct)
    assert again.wallet["id"] == result.wallet["id"] and len(repo.wallets) == 1      # same wallet, new session


def test_nonce_is_single_use_and_signature_must_match(auth_settings):
    service, _ = make_service(auth_settings)
    acct = new_account()
    nonce = service.issue_nonce()
    text = siwe_message(acct.address, nonce)
    signature = sign(acct, text)
    service.login(text, signature)
    with pytest.raises(AuthError, match="already used"):
        service.login(text, signature)                                           # replay

    nonce2 = service.issue_nonce()
    text2 = siwe_message(acct.address, nonce2)
    with pytest.raises(AuthError):
        service.login(text2, sign(new_account(), text2))                         # someone else's signature
    with pytest.raises(AuthError, match="different site"):
        n3 = service.issue_nonce()
        t3 = siwe_message(acct.address, n3, domain="evil.example")
        service.login(t3, sign(acct, t3))
    with pytest.raises(AuthError):
        unknown = siwe_message(acct.address, "neverissued1234")
        service.login(unknown, sign(acct, unknown))                              # nonce the server never issued


def test_refresh_rotates_and_reuse_revokes_the_family(auth_settings):
    service, repo = make_service(auth_settings)
    first, _ = login(service, new_account())
    second = service.refresh(first.refresh_token)
    assert second.refresh_token != first.refresh_token
    service.authenticate(second.access_token)

    with pytest.raises(AuthError, match="reused"):
        service.refresh(first.refresh_token)                                     # the old token again = theft signal
    with pytest.raises(AuthError):
        service.refresh(second.refresh_token)                                    # so the legitimate token is dead too


def test_logout_revokes_and_bad_refresh_tokens_fail(auth_settings):
    service, _ = make_service(auth_settings)
    result, _ = login(service, new_account())
    service.logout(result.refresh_token)
    with pytest.raises(AuthError, match="expired"):
        service.refresh(result.refresh_token)
    for bad in ("", "nodot", "a.b", "00000000-0000-0000-0000-000000000000.xyz"):
        with pytest.raises(AuthError):
            service.refresh(bad)
    service.logout("garbage")                                                    # never raises


def test_allowed_domains_derive_from_origins():
    from airaa.auth import allowed_domains

    assert allowed_domains(Settings(allowed_origins="https://app.example.com,http://localhost:3000")) == ("app.example.com", "localhost:3000")
    assert "localhost:3000" in allowed_domains(Settings(allowed_origins="*"))
    assert allowed_domains(Settings(siwe_domains=("a.example",), allowed_origins="https://b.example")) == ("a.example",)


# ----------------------------------------------------------------------- endpoints
@pytest.fixture
def client(auth_settings):
    repo = FakeAuthRepo()
    services = Services(settings=auth_settings, auth_repo=repo, auth=AuthService(repo, auth_settings))
    return create_app(auth_settings, services=services).test_client()


def sign_in(client, acct=None, origin="http://localhost:3000"):
    acct = acct or new_account()
    nonce = client.get("/api/auth/nonce").get_json()["nonce"]
    text = siwe_message(acct.address, nonce)
    return client.post("/api/auth/verify", json={"message": text, "signature": sign(acct, text)}, headers={"Origin": origin}), acct


def test_sign_in_flow_over_http(client):
    res, acct = sign_in(client)
    body = res.get_json()
    assert res.status_code == 200 and body["wallet"]["address"] == acct.address.lower() and body["expires_in"] == 900
    cookie = res.headers.get("Set-Cookie")
    assert "airaa_refresh=" in cookie and "HttpOnly" in cookie and "Path=/api/auth" in cookie

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.get_json()["wallet"]["address"] == acct.address.lower()

    refreshed = client.post("/api/auth/refresh", headers={"Origin": "http://localhost:3000"})   # cookie jar carries the cookie
    assert refreshed.status_code == 200 and refreshed.get_json()["access_token"]

    out = client.post("/api/auth/logout", headers={"Origin": "http://localhost:3000"})
    assert out.status_code == 200
    assert client.post("/api/auth/refresh", headers={"Origin": "http://localhost:3000"}).status_code == 401


def test_endpoints_reject_bad_input_and_missing_auth(client):
    assert client.post("/api/auth/verify", json={"message": "x"}).status_code == 400
    assert client.post("/api/auth/verify", json={"message": "x", "signature": "0x00"}).status_code == 401
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer nonsense"}).status_code == 401
    assert client.post("/api/auth/refresh").status_code == 401


def test_cookie_endpoints_check_origin_when_configured(auth_settings):
    settings = Settings(gemini_api_key="t", jwt_secret=SECRET, siwe_domains=("app.example.com",),
                        allowed_origins="https://app.example.com", rate_limit_per_minute=0)
    repo = FakeAuthRepo()
    c = create_app(settings, services=Services(settings=settings, auth_repo=repo, auth=AuthService(repo, settings))).test_client()
    assert c.post("/api/auth/logout", headers={"Origin": "https://evil.example"}).status_code == 403
    assert c.post("/api/auth/logout", headers={"Origin": "https://app.example.com"}).status_code == 200
    assert c.post("/api/auth/logout").status_code == 403          # no Origin at all is not accepted either


def test_auth_is_503_when_not_configured(settings):
    c = create_app(settings, services=Services(settings=settings)).test_client()
    assert c.get("/api/auth/nonce").status_code == 503
    assert c.get("/api/health").get_json()["features"]["wallet_auth"] is False


# ----------------------------------------------------------------------- CORS (what makes cookie sign-in work cross-site)
def preflight(client, path, origin, method="POST", headers="authorization,content-type"):
    return client.options(path, headers={"Origin": origin, "Access-Control-Request-Method": method, "Access-Control-Request-Headers": headers})


def test_explicit_origins_get_credentialed_cors_for_listed_origin_only():
    settings = Settings(gemini_api_key="t", allowed_origins="https://app.example.com", rate_limit_per_minute=0)
    client = create_app(settings, services=Services(settings=settings)).test_client()

    ok = preflight(client, "/api/auth/refresh", "https://app.example.com")
    assert ok.headers["Access-Control-Allow-Origin"] == "https://app.example.com"
    assert ok.headers["Access-Control-Allow-Credentials"] == "true"
    assert "authorization" in ok.headers["Access-Control-Allow-Headers"].lower()
    assert "Access-Control-Allow-Origin" not in preflight(client, "/api/auth/refresh", "https://evil.example").headers

    patch = preflight(client, "/api/memories/abc", "https://app.example.com", method="PATCH")
    assert "PATCH" in patch.headers["Access-Control-Allow-Methods"] and "PUT" in patch.headers["Access-Control-Allow-Methods"]


def test_open_default_allows_bearer_calls_everywhere_but_cookie_calls_only_from_localhost():
    settings = Settings(gemini_api_key="t", allowed_origins="*", rate_limit_per_minute=0)
    client = create_app(settings, services=Services(settings=settings)).test_client()

    anywhere = preflight(client, "/api/research", "https://anywhere.example")
    assert anywhere.headers["Access-Control-Allow-Origin"] in ("*", "https://anywhere.example")   # flask-cors may echo the origin
    assert "Access-Control-Allow-Credentials" not in anywhere.headers                               # ...but never with credentials

    dev = preflight(client, "/api/auth/refresh", "http://localhost:3000")
    assert dev.headers["Access-Control-Allow-Origin"] == "http://localhost:3000" and dev.headers["Access-Control-Allow-Credentials"] == "true"
    assert "Access-Control-Allow-Origin" not in preflight(client, "/api/auth/refresh", "https://anywhere.example").headers


def test_artifact_upload_gets_a_larger_body_limit_than_everything_else(auth_settings):
    settings = Settings(gemini_api_key="t", jwt_secret=SECRET, siwe_domains=(DOMAIN,), rate_limit_per_minute=0, max_artifact_bytes=300_000)
    repo = FakeAuthRepo()

    class StubVault:
        def create_artifact(self, wallet_id, body):
            return {"id": "stored", "size": len(body["ciphertext"])}

    services = Services(settings=settings, auth_repo=repo, auth=AuthService(repo, settings), vault=StubVault())
    client = create_app(settings, services=services).test_client()
    token = sign_in(client)[0].get_json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    big = "x" * 100_000

    assert client.post("/api/research", json={"query": big}).status_code == 413                                 # 64 KB cap
    assert client.post("/api/alerts", json={"name": big}, headers=headers).status_code == 413                   # ... on every other route
    res = client.post("/api/artifacts", json={"ciphertext": big}, headers=headers)
    assert res.status_code == 201 and res.get_json()["artifact"]["size"] == 100_000                              # the larger cap applies here
    assert client.post("/api/artifacts", json={"ciphertext": "x" * 1_000_000}, headers=headers).status_code == 413   # but still bounded
