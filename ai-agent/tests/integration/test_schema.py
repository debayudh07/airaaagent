"""The migrations apply to a real Postgres, and row-level security isolates wallets."""
from __future__ import annotations

import uuid

import psycopg
import pytest

VEC = "[" + ",".join(["0.1"] * 768) + "]"


def test_all_migrations_applied(pool):
    with pool.connection() as conn:
        names = [r["name"] for r in conn.execute("select name from public.schema_migrations order by name").fetchall()]
        tables = {r["tablename"] for r in conn.execute("select tablename from pg_tables where schemaname = 'public'").fetchall()}
    assert names[0].endswith("_core") and names[-1].endswith("_alerts") and len(names) == 7
    assert {"wallets", "auth_sessions", "conversations", "messages", "memories", "tool_cache", "watchlist",
            "portfolio_snapshots", "kb_documents", "kb_chunks", "vault_keys", "artifacts", "shares",
            "alert_rules", "inbox"} <= tables


def test_migrations_are_idempotent(database_url):
    """Hand-running a file in the Supabase SQL editor twice must not fail."""
    from airaa.db.migrate import migration_files

    with psycopg.connect(database_url, autocommit=True) as conn:
        for path in migration_files():
            conn.execute(path.read_text(encoding="utf-8"))


def test_rls_isolates_wallets(database_url, pool, wallet_id):
    other = str(uuid.uuid4())
    with pool.connection() as conn:
        conn.execute("insert into wallets (id, address) values (%s, %s)", (other, "0x" + "ab" * 20))
        conn.execute(
            "insert into memories (wallet_id, kind, content, embedding) values (%s, 'fact', 'mine', %s::vector)",
            (wallet_id, VEC),
        )
        conn.execute(
            "insert into memories (wallet_id, kind, content, embedding) values (%s, 'fact', 'theirs', %s::vector)",
            (other, VEC),
        )
        conn.execute("do $$ begin if not exists (select 1 from pg_roles where rolname = 'app_user') then create role app_user; end if; end $$")
        conn.execute("grant select, insert, update, delete on all tables in schema public to app_user")
        conn.execute("grant usage on schema auth to app_user")
        conn.execute("grant execute on all functions in schema auth to app_user")

    with psycopg.connect(database_url, autocommit=False) as conn:
        conn.execute("set local role app_user")
        conn.execute("select set_config('request.jwt.claims', %s, true)", (f'{{"sub": "{wallet_id}"}}',))
        rows = [r[0] for r in conn.execute("select content from memories").fetchall()]
        assert rows == ["mine"]
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                "insert into memories (wallet_id, kind, content, embedding) values (%s, 'fact', 'forged', %s::vector)",
                (other, VEC),
            )
        conn.rollback()

        conn.execute("set local role app_user")
        conn.execute("select set_config('request.jwt.claims', '{}', true)")
        assert conn.execute("select count(*) from memories").fetchone()[0] == 0   # anonymous sees nothing
