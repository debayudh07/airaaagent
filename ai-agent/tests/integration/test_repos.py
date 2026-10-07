"""The SQL behind every repository, run against a real Postgres + pgvector."""
from __future__ import annotations

import hashlib
import time
import uuid

import pytest

from airaa.db.alerts_repo import AlertsRepo
from airaa.db.auth_repo import AuthRepo
from airaa.db.cache_repo import CacheRepo
from airaa.db.context_repo import ContextRepo
from airaa.db.kb_repo import KbRepo
from airaa.db.memory_repo import MemoryRepo
from airaa.db.store import ConversationStore
from airaa.db.vault_repo import VaultRepo

from ..helpers import FakeEmbedder

E = FakeEmbedder()


def vec(text: str):
    return E.embed_one_sync(text)


# ----------------------------------------------------------------------- conversations
def test_conversation_store_roundtrip_ownership_and_export(pool, make_wallet):
    store, alice, bob = ConversationStore(pool), make_wallet(), make_wallet()
    cid = "conv-" + uuid.uuid4().hex[:12]

    row = store.ensure(cid)                                              # guest conversation
    assert row["wallet_id"] is None
    store.append(cid, [("human", "What is Aave TVL?", {"timestamp": "t"}), ("ai", "About $20B", {"research_data": {"x": 1}})])
    loaded = store.load(cid)
    assert loaded["messages"][1][2] == {"research_data": {"x": 1}} and loaded["message_count"] == 2

    assert store.claim(cid, alice) is True and store.claim(cid, bob) is False     # first claim wins, never reassigned
    assert store.ensure(cid, bob)["wallet_id"] == alice                           # ensure() does not steal either
    listed = store.list_for_wallet(alice)
    assert [c["id"] for c in listed] == [cid] and listed[0]["title"] == "What is Aave TVL?"
    assert store.list_for_wallet(bob) == []
    assert store.export_wallet(alice)[0]["messages"][0]["content"] == "What is Aave TVL?"

    store.save_context(cid, {"last_query": "q"})
    assert store.load(cid)["context"] == {"last_query": "q"}
    assert store.delete(cid) is True and store.load(cid) is None


def test_stale_guest_conversations_are_purged_but_wallet_ones_never(pool, make_wallet):
    store, w = ConversationStore(pool), make_wallet()
    guest, owned, fresh = ("conv-" + uuid.uuid4().hex[:12] for _ in range(3))
    store.ensure(guest)
    store.ensure(owned, w)
    store.ensure(fresh)
    with pool.connection() as conn:
        conn.execute("update conversations set last_activity = now() - interval '45 days' where id = any(%s)", ([guest, owned],))
    store.purge_stale_guests(30)
    assert store.load(guest) is None and store.load(owned) is not None and store.load(fresh) is not None


def test_empty_conversations_are_not_listed(pool, make_wallet):
    store, w = ConversationStore(pool), make_wallet()
    cid = "conv-" + uuid.uuid4().hex[:12]
    store.ensure(cid, w)
    assert store.list_for_wallet(w) == []


# ----------------------------------------------------------------------- auth
def test_nonce_is_single_use_and_expires(pool):
    repo = AuthRepo(pool)
    repo.create_nonce("n1" + uuid.uuid4().hex[:8], 300)
    live = "n2" + uuid.uuid4().hex[:8]
    repo.create_nonce(live, 300)
    assert repo.consume_nonce(live) is True and repo.consume_nonce(live) is False
    stale = "n3" + uuid.uuid4().hex[:8]
    repo.create_nonce(stale, -5)
    assert repo.consume_nonce(stale) is False and repo.consume_nonce("never-issued-nonce") is False


def test_wallet_upsert_and_settings(pool):
    repo = AuthRepo(pool)
    address = "0x" + uuid.uuid4().hex + uuid.uuid4().hex[:8]
    a = repo.upsert_wallet(address.upper().replace("0X", "0x"))
    b = repo.upsert_wallet(address)
    assert a["id"] == b["id"] and a["address"] == address.lower()
    assert repo.update_settings(a["id"], {"memory_enabled": False})["memory_enabled"] is False
    assert repo.get_wallet("not-a-uuid") is None


def test_refresh_rotation_is_compare_and_set(pool, make_wallet):
    repo, w = AuthRepo(pool), make_wallet()
    sid = str(uuid.uuid4())
    session = repo.create_session(w, "hash-1", 30, "agent", "ip", session_id=sid)
    assert repo.rotate(sid, "wrong", "hash-2", 30) is False
    assert repo.rotate(sid, "hash-1", "hash-2", 30) is True
    assert repo.rotate(sid, "hash-1", "hash-3", 30) is False                    # replaying the old hash fails
    got = repo.get_session(sid)
    assert got["refresh_hash"] == "hash-2" and got["expired"] is False and got["revoked_at"] is None

    other = repo.create_session(w, "h", 30, session_id=str(uuid.uuid4()))
    repo.revoke_family(session["family_id"])
    assert repo.get_session(sid)["revoked_at"] and repo.get_session(other["id"])["revoked_at"] is None
    assert repo.rotate(sid, "hash-2", "hash-4", 30) is False                    # revoked sessions cannot rotate
    assert repo.get_session("nope") is None


# ----------------------------------------------------------------------- memories
def test_memory_repo_search_is_scoped_ranked_and_editable(pool, make_wallet):
    repo, alice, bob = MemoryRepo(pool), make_wallet(), make_wallet()
    eth = repo.insert(alice, "fact", "The user holds ETH on Arbitrum", 0.9, vec("The user holds ETH on Arbitrum"))
    repo.insert(alice, "preference", "Prefers concise answers", 0.5, vec("Prefers concise answers"))
    repo.insert(bob, "fact", "The user holds ETH on Arbitrum", 0.9, vec("The user holds ETH on Arbitrum"))

    hits = repo.search(alice, vec("my ETH holdings on Arbitrum"), 5, 0.2)
    assert hits[0]["id"] == eth and hits[0]["similarity"] > 0.5
    assert all(h["id"] != "" for h in hits) and len(repo.search(alice, vec("ETH Arbitrum"), 5, 0.0)) == 2
    assert repo.count(alice) == 2 and repo.count(bob) == 1

    repo.merge(alice, eth, 0.3, "The user holds a lot of ETH on Arbitrum", vec("The user holds a lot of ETH on Arbitrum"))
    merged = [m for m in repo.list(alice) if m["id"] == eth][0]
    assert merged["content"].startswith("The user holds a lot") and merged["importance"] == 0.9 and merged["access_count"] == 1

    repo.touch(alice, [eth])
    assert repo.update(alice, eth, pinned=True)["pinned"] is True
    assert repo.update(bob, eth, content="hijack") is None                      # another wallet's memory is untouchable
    assert repo.update(alice, "not-a-uuid", content="x") is None
    assert repo.list(alice)[0]["id"] == eth                                     # pinned first
    assert repo.delete(bob, eth) is False and repo.delete(alice, eth) is True


def test_memory_prune_keeps_the_best_and_all_pinned(pool, make_wallet):
    repo, w = MemoryRepo(pool), make_wallet()
    for i in range(6):
        repo.insert(w, "fact", f"memory number {i}", i / 10, vec(f"memory number {i}"), pinned=(i == 0))
    assert repo.prune(w, keep=2) == 3
    kept = {m["content"] for m in repo.list(w)}
    assert "memory number 0" in kept and "memory number 5" in kept and "memory number 4" in kept and len(kept) == 3
    assert repo.delete_all(w) == 3


def test_memory_expired_rows_are_not_returned(pool, make_wallet):
    repo, w = MemoryRepo(pool), make_wallet()
    mid = repo.insert(w, "fact", "temporary fact about ETH", 0.5, vec("temporary fact about ETH"))
    with pool.connection() as conn:
        conn.execute("update memories set expires_at = now() - interval '1 hour' where id = %s", (mid,))
    assert repo.search(w, vec("temporary fact about ETH"), 5, 0.0) == []


# ----------------------------------------------------------------------- cache
def test_cache_exact_semantic_and_expiry(pool):
    repo = CacheRepo(pool)
    tool, params = "tool-" + uuid.uuid4().hex[:6], "p" + uuid.uuid4().hex[:6]
    key = hashlib.sha256((tool + "k").encode()).hexdigest()
    repo.put(key, tool, params, "price of eth now", vec("price of eth now"), {"success": True, "n": 1}, 60)

    hit = repo.get_exact(key)
    assert hit["result"] == {"success": True, "n": 1} and hit["age_seconds"] >= 0
    near = repo.get_semantic(tool, params, vec("price of eth now"), 0.9)
    assert near["key_hash"] == key and near["similarity"] > 0.99
    assert repo.get_semantic(tool, params, vec("completely different words here"), 0.9) is None
    assert repo.get_semantic(tool, "other-params", vec("price of eth now"), 0.9) is None
    assert repo.get_semantic("other-tool", params, vec("price of eth now"), 0.9) is None

    repo.put(key, tool, params, "price of eth now", vec("price of eth now"), {"success": True, "n": 2}, 60)   # upsert refreshes
    assert repo.get_exact(key)["result"]["n"] == 2

    expired = hashlib.sha256((tool + "old").encode()).hexdigest()
    repo.put(expired, tool, params, "old", vec("old"), {"success": True}, -10)
    assert repo.get_exact(expired) is None
    assert repo.purge_expired() >= 1
    with pool.connection() as conn:
        assert conn.execute("select hits from tool_cache where key_hash = %s", (key,)).fetchone()["hits"] >= 2


# ----------------------------------------------------------------------- watchlist & portfolio
def test_watchlist_upsert_search_and_isolation(pool, make_wallet):
    repo, a, b = ContextRepo(pool), make_wallet(), make_wallet()
    first = repo.add_watch(a, "token", "eth", None, vec("token eth"))
    again = repo.add_watch(a, "token", "eth", "core holding", None)             # upsert keeps the old embedding
    assert first["id"] == again["id"] and again["note"] == "core holding" and repo.count_watch(a) == 1
    repo.add_watch(a, "protocol", "aave", "lending exposure", vec("protocol aave lending exposure"))
    repo.add_watch(b, "token", "eth", None, vec("token eth"))

    close = repo.search_watch(a, vec("aave lending"), 5, 0.1)
    assert close[0]["entity_id"] == "aave"
    assert {w["entity_id"] for w in repo.list_watch(a)} == {"eth", "aave"} and len(repo.list_watch(b)) == 1
    assert repo.remove_watch(b, first["id"]) is False and repo.remove_watch(a, first["id"]) is True


def test_portfolio_snapshots_keep_history_short_and_latest_per_chain(pool, make_wallet):
    repo, w = ContextRepo(pool), make_wallet()
    for i in range(8):
        repo.add_snapshot(w, "ethereum", {"i": i}, f"snapshot {i}", None)
    repo.add_snapshot(w, "base", {}, "base snapshot", None)
    latest = {s["chain"]: s["summary"] for s in repo.latest_snapshots(w, 5)}
    assert latest == {"ethereum": "snapshot 7", "base": "base snapshot"}
    with pool.connection() as conn:
        assert conn.execute("select count(*) as n from portfolio_snapshots where wallet_id = %s and chain = 'ethereum'", (w,)).fetchone()["n"] == 5


# ----------------------------------------------------------------------- knowledge base
def chunk(i, text):
    return (i, text, vec(text), {"title": "Doc"})


def test_kb_hybrid_search_replace_and_cascade(pool):
    repo = KbRepo(pool)
    url = f"https://docs.test/{uuid.uuid4().hex}"
    repo.replace_document("docs", url, "Aave Docs", "hash1", [
        chunk(0, "Aave is a decentralised lending protocol where users supply and borrow crypto assets"),
        chunk(1, "Liquidations happen when the health factor of a position drops below one"),
        chunk(2, "Governance proposals are voted on by AAVE token holders")])

    vector_hit = repo.search(vec("how does lending and borrowing work"), "how does lending and borrowing work", 3)
    assert vector_hit[0]["url"] == url and "lending protocol" in vector_hit[0]["content"] and vector_hit[0]["similarity"] > 0.2
    keyword_hit = repo.search(vec("unrelated embedding text"), "health factor", 3)       # found by full-text even if the vector misses
    assert any("health factor" in r["content"] for r in keyword_hit)
    assert repo.get_document(url)["content_hash"] == "hash1"

    repo.replace_document("docs", url, "Aave Docs v2", "hash2", [chunk(0, "Only one chunk remains about flash loans")])
    stats_before = repo.stats()
    after = repo.search(vec("flash loans"), "flash loans", 5)
    assert [r["content"] for r in after if r["url"] == url] == ["Only one chunk remains about flash loans"]
    assert repo.delete_document(url) is True and repo.get_document(url) is None
    assert repo.stats()["chunks"] == stats_before["chunks"] - 1                     # chunks go with the document


# ----------------------------------------------------------------------- vault, artifacts, shares
def test_vault_keys_artifacts_blobs_and_isolation(pool, make_wallet):
    from airaa.config import Settings
    from airaa.vault import DbBlobStore, VaultError, VaultService
    import base64

    repo = VaultRepo(pool)
    service = VaultService(repo, DbBlobStore(pool), FakeEmbedder(), Settings(gemini_api_key="t", max_artifact_bytes=2048))
    alice, bob = make_wallet(), make_wallet()
    b64 = lambda raw: base64.b64encode(raw).decode()  # noqa: E731

    with pytest.raises(VaultError, match="Set up your vault"):
        service.create_artifact(alice, {"ciphertext": b64(b"x" * 40), "wrapped_cek": b64(b"k" * 40)})

    service.put_key(alice, "signature", {"wrapped_dek": b64(b"d" * 48), "kdf": {"salt": "abc"}})
    service.put_key(alice, "passphrase", {"wrapped_dek": b64(b"e" * 48), "kdf": {"iterations": 600000}})
    assert [k["wrapper_type"] for k in service.list_keys(alice)] == ["signature", "passphrase"]
    assert service.list_keys(bob) == []
    service.delete_key(alice, "passphrase")
    with pytest.raises(VaultError, match="only way"):
        service.delete_key(alice, "signature")                                    # can never lock yourself out

    aid = str(uuid.uuid4())
    ciphertext = bytes(range(256)) * 2
    made = service.create_artifact(alice, {"id": aid, "ciphertext": b64(ciphertext), "wrapped_cek": b64(b"c" * 48),
                                           "meta_enc": b64(b"meta" * 8), "index_summary": "Aave lending risk report"})
    assert made["id"] == aid and made["size_bytes"] == 512
    with pytest.raises(Exception):
        service.create_artifact(alice, {"id": aid, "ciphertext": b64(ciphertext), "wrapped_cek": b64(b"c" * 48)})   # duplicate id
    assert DbBlobStore(pool).get(f"sealed/{alice}/{aid}") == ciphertext          # only ciphertext is stored

    row = service.get_artifact(alice, aid)
    assert service.read_blob(row) == ciphertext and row["wrapped_cek"] == b"c" * 48
    assert [a["id"] for a in service.list_artifacts(alice)] == [aid] and service.list_artifacts(bob) == []
    with pytest.raises(VaultError):
        service.get_artifact(bob, aid)                                            # not yours = not found
    with pytest.raises(VaultError):
        service.delete_artifact(bob, aid)

    assert service.search(alice, "lending risk")[0]["id"] == aid                  # opt-in summary is searchable
    assert service.search(bob, "lending risk") == []

    for bad in ({"ciphertext": "!!!", "wrapped_cek": b64(b"k")}, {"ciphertext": b64(b"x" * 5000), "wrapped_cek": b64(b"k")},
                {"ciphertext": b64(b"x" * 10), "wrapped_cek": b64(b"k")}, {"id": "nope", "ciphertext": b64(b"x" * 40), "wrapped_cek": b64(b"k")}):
        with pytest.raises(VaultError):
            service.create_artifact(alice, bad)

    service.delete_artifact(alice, aid)
    assert DbBlobStore(pool).get(f"sealed/{alice}/{aid}") is None
    service.create_artifact(alice, {"ciphertext": b64(ciphertext), "wrapped_cek": b64(b"c" * 48)})
    service.purge_blobs(alice)
    assert repo.storage_paths(alice) and all(DbBlobStore(pool).get(p) is None for p in repo.storage_paths(alice))


def test_shares_link_wallet_revoke_and_expiry(pool, make_wallet):
    repo, owner = VaultRepo(pool), make_wallet()
    from airaa.config import Settings
    from airaa.vault import DbBlobStore, VaultService

    service = VaultService(repo, DbBlobStore(pool), None, Settings())
    share = service.create_link_share(owner, "artifact", str(uuid.uuid4()), b"wrapped-key", False, 24)
    token = share["token"]
    found = repo.get_link_share(token)
    assert found["wrapped_key"] == b"wrapped-key" and found["resource_type"] == "artifact"
    assert repo.get_link_share(token + "x") is None
    with pool.connection() as conn:
        assert conn.execute("select token_hash from shares where id = %s", (share["id"],)).fetchone()["token_hash"] != token   # only the hash is stored
    assert repo.revoke_share(owner, share["id"]) is True and repo.get_link_share(token) is None
    assert repo.revoke_share(make_wallet(), share["id"]) is False

    short = service.create_link_share(owner, "conversation", "conv-abcdef12", None, True, 1)
    with pool.connection() as conn:
        conn.execute("update shares set expires_at = now() - interval '1 minute' where id = %s", (short["id"],))
    assert repo.get_link_share(short["token"]) is None                              # expired links stop working

    recipient = "0x" + "cd" * 20
    repo.create_share(owner, "conversation", "conv-abcdef12", "wallet", recipient, None, None, True, None)
    assert repo.get_wallet_share("conversation", "conv-abcdef12", recipient.upper().replace("0X", "0x"))["redact_research_data"] is True
    assert repo.get_wallet_share("conversation", "conv-abcdef12", "0x" + "ee" * 20) is None
    assert repo.list_received(recipient)[0]["resource_id"] == "conv-abcdef12"
    with pytest.raises(Exception):                                                   # wallet-to-wallet artifact shares are blocked by a CHECK
        repo.create_share(owner, "artifact", str(uuid.uuid4()), "wallet", recipient, None, b"k", False, None)


# ----------------------------------------------------------------------- alerts
def test_alert_rules_claim_due_and_inbox(pool, make_wallet):
    repo, alice, bob = AlertsRepo(pool), make_wallet(), make_wallet()
    rule = repo.create_rule(alice, "TVL watch", "Aave TVL change", "TVL dropped more than 10%", 60)
    other = repo.create_rule(bob, "Bob's rule", "ETH price", None, 60)
    assert repo.count_rules(alice) == 1 and repo.list_rules(bob)[0]["id"] == other["id"]
    assert repo.update_rule(bob, rule["id"], name="hijack") is None and repo.update_rule(alice, rule["id"], enabled=False)["enabled"] is False
    assert repo.update_rule(alice, rule["id"]) is None and repo.update_rule(alice, "not-uuid", name="x") is None

    ours = {rule["id"], other["id"]}
    due = lambda: {r["id"] for r in repo.claim_due(50, 24)} & ours   # noqa: E731 - other tests share this database
    assert due() == {other["id"]}                                    # alice's rule is disabled
    repo.update_rule(alice, rule["id"], enabled=True)
    assert due() == {rule["id"]}                                     # bob's was pushed into the future by its own claim
    assert due() == set()                                            # and alice's now is too
    assert repo.list_rules(alice)[0]["runs_today"] == 1


def test_claim_due_respects_the_daily_cap_and_skips_disabled(pool, make_wallet):
    repo, w = AlertsRepo(pool), make_wallet()
    rule = repo.create_rule(w, "capped", "ETH", None, 15)
    for _ in range(2):
        with pool.connection() as conn:
            conn.execute("update alert_rules set next_run_at = now() - interval '1 minute' where id = %s", (rule["id"],))
        got = repo.claim_due(50, 2)
        assert any(r["id"] == rule["id"] for r in got)
    with pool.connection() as conn:
        conn.execute("update alert_rules set next_run_at = now() - interval '1 minute' where id = %s", (rule["id"],))
    assert all(r["id"] != rule["id"] for r in repo.claim_due(50, 2))                  # cap of 2 runs/day reached
    repo.update_rule(w, rule["id"], enabled=False)
    with pool.connection() as conn:
        conn.execute("update alert_rules set next_run_at = now() - interval '1 minute', runs_today = 0 where id = %s", (rule["id"],))
    assert all(r["id"] != rule["id"] for r in repo.claim_due(50, 99))                  # disabled rules never run


def test_inbox_lifecycle_and_isolation(pool, make_wallet):
    repo, a, b = AlertsRepo(pool), make_wallet(), make_wallet()
    first = repo.add_inbox(a, None, "Alert 1", "summary one", {"k": 1})
    repo.add_inbox(a, None, "Alert 2", "summary two", None)
    repo.add_inbox(b, None, "Bob", "private", None)
    assert repo.unread_count(a) == 2 and [i["title"] for i in repo.list_inbox(a)] == ["Alert 2", "Alert 1"]
    assert repo.mark_read(b, first["id"]) == 0 and repo.mark_read(a, first["id"]) == 1 and repo.unread_count(a) == 1
    assert [i["title"] for i in repo.list_inbox(a, unread_only=True)] == ["Alert 2"]
    assert repo.mark_read(a) == 1 and repo.unread_count(a) == 0
    assert repo.delete_inbox(b, first["id"]) is False and repo.delete_inbox(a, first["id"]) is True


def test_inbox_is_bounded(pool, make_wallet):
    repo, w = AlertsRepo(pool), make_wallet()
    for i in range(203):
        repo.add_inbox(w, None, f"t{i}", "s", None)
    assert len(repo.list_inbox(w, limit=100)) == 100
    with pool.connection() as conn:
        assert conn.execute("select count(*) as n from inbox where wallet_id = %s", (w,)).fetchone()["n"] == 200


def test_deleting_a_wallet_cascades_everywhere(pool, make_wallet):
    w = make_wallet()
    MemoryRepo(pool).insert(w, "fact", "x", 0.5, vec("x"))
    ContextRepo(pool).add_watch(w, "token", "eth", None, None)
    AlertsRepo(pool).create_rule(w, "r", "q", None, 60)
    ConversationStore(pool).ensure("conv-" + uuid.uuid4().hex[:12], w)
    VaultRepo(pool).put_key(w, "signature", b"k", {})
    assert AuthRepo(pool).delete_wallet(w) is True
    with pool.connection() as conn:
        for table in ("memories", "watchlist", "alert_rules", "conversations", "vault_keys"):
            assert conn.execute(f"select count(*) as n from {table} where wallet_id = %s", (w,)).fetchone()["n"] == 0
