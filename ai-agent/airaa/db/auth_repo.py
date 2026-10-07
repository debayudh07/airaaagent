"""Wallets, SIWE nonces and refresh-token sessions."""
from __future__ import annotations

from typing import Any, Dict, Optional

from .util import as_uuid, jsonb, stringify_ids


class AuthRepo:
    def __init__(self, pool: Any) -> None:
        self.pool = pool

    # ---- nonces --------------------------------------------------------
    def create_nonce(self, nonce: str, ttl_seconds: int = 300) -> None:
        with self.pool.connection() as conn:
            conn.execute("insert into auth_nonces (nonce, expires_at) values (%s, now() + make_interval(secs => %s))", (nonce, ttl_seconds))
            conn.execute("delete from auth_nonces where expires_at < now() - interval '1 day'")  # housekeeping

    def consume_nonce(self, nonce: str) -> bool:
        """Atomically mark a live nonce used. False if unknown, expired or already used."""
        with self.pool.connection() as conn:
            row = conn.execute(
                "update auth_nonces set used_at = now() where nonce = %s and used_at is null and expires_at > now() returning nonce",
                (nonce,),
            ).fetchone()
        return row is not None

    # ---- wallets -------------------------------------------------------
    def upsert_wallet(self, address: str) -> Dict[str, Any]:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                insert into wallets (address) values (%s)
                on conflict (address) do update set last_seen = now()
                returning id, address, plan, settings
                """,
                (address.lower(),),
            ).fetchone()
        return stringify_ids(row)

    def get_wallet(self, wallet_id: str) -> Optional[Dict[str, Any]]:
        wid = as_uuid(wallet_id)
        if wid is None:
            return None
        with self.pool.connection() as conn:
            row = conn.execute("select id, address, plan, settings from wallets where id = %s", (wid,)).fetchone()
        return stringify_ids(row) if row else None

    def update_settings(self, wallet_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        with self.pool.connection() as conn:
            row = conn.execute(
                "update wallets set settings = settings || %s where id = %s returning settings", (jsonb(patch), wallet_id)
            ).fetchone()
        return row["settings"]

    def delete_wallet(self, wallet_id: str) -> bool:
        """Cascades to every wallet-owned table. Storage objects are removed by the caller."""
        with self.pool.connection() as conn:
            return conn.execute("delete from wallets where id = %s", (wallet_id,)).rowcount > 0

    # ---- refresh sessions ---------------------------------------------
    def create_session(self, wallet_id: str, refresh_hash: str, ttl_days: int, user_agent: str = "", ip_hash: str = "",
                       session_id: Optional[str] = None) -> Dict[str, Any]:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                insert into auth_sessions (id, wallet_id, refresh_hash, user_agent, ip_hash, expires_at)
                values (coalesce(%s::uuid, gen_random_uuid()), %s, %s, %s, %s, now() + make_interval(days => %s))
                returning id, family_id, wallet_id, expires_at
                """,
                (session_id, wallet_id, refresh_hash, user_agent[:300], ip_hash, ttl_days),
            ).fetchone()
        return stringify_ids(row)

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        sid = as_uuid(session_id)
        if sid is None:
            return None
        with self.pool.connection() as conn:
            row = conn.execute(
                "select id, wallet_id, family_id, refresh_hash, expires_at, revoked_at, expires_at < now() as expired "
                "from auth_sessions where id = %s",
                (sid,),
            ).fetchone()
        return stringify_ids(row) if row else None

    def rotate(self, session_id: str, old_hash: str, new_hash: str, ttl_days: int) -> bool:
        """Compare-and-set the refresh hash. False if it no longer matches (replay) or the session is dead."""
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                update auth_sessions
                   set refresh_hash = %s, expires_at = now() + make_interval(days => %s)
                 where id = %s and refresh_hash = %s and revoked_at is null and expires_at > now()
                returning id
                """,
                (new_hash, ttl_days, session_id, old_hash),
            ).fetchone()
        return row is not None

    def revoke_session(self, session_id: str) -> None:
        with self.pool.connection() as conn:
            conn.execute("update auth_sessions set revoked_at = coalesce(revoked_at, now()) where id = %s", (session_id,))

    def revoke_family(self, family_id: str) -> None:
        with self.pool.connection() as conn:
            conn.execute("update auth_sessions set revoked_at = coalesce(revoked_at, now()) where family_id = %s", (family_id,))

    def revoke_all_for_wallet(self, wallet_id: str) -> None:
        with self.pool.connection() as conn:
            conn.execute("update auth_sessions set revoked_at = coalesce(revoked_at, now()) where wallet_id = %s", (wallet_id,))
