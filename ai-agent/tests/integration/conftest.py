"""Real-Postgres fixtures. Skipped unless ``pgserver`` (embedded Postgres + pgvector) is installed,
or ``AIRAA_TEST_DATABASE_URL`` points at a disposable database.

The migrations target Supabase, which provides ``auth.jwt()`` and ``storage.buckets``; both are stubbed here.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

SUPABASE_STUBS = """
create schema if not exists auth;
create or replace function auth.jwt() returns jsonb language sql stable as $$
    select coalesce(nullif(current_setting('request.jwt.claims', true), ''), '{}')::jsonb
$$;
create schema if not exists storage;
create table if not exists storage.buckets (id text primary key, name text, public boolean default false);
"""


@pytest.fixture(scope="session")
def database_url():
    url = os.getenv("AIRAA_TEST_DATABASE_URL")
    server = None
    if not url:
        pgserver = pytest.importorskip("pgserver")
        data_dir = Path(tempfile.mkdtemp(prefix="airaa-pg-"))
        server = pgserver.get_server(data_dir, cleanup_mode="delete")
        url = server.get_uri()

    import psycopg
    from airaa.db.migrate import apply_all

    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(SUPABASE_STUBS)
    apply_all(url)
    yield url
    if server is not None:
        server.cleanup()


@pytest.fixture(scope="session")
def pool(database_url):
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    p = ConnectionPool(database_url, min_size=1, max_size=4, kwargs={"row_factory": dict_row, "prepare_threshold": None}, open=True)
    yield p
    p.close()


@pytest.fixture
def wallet_id(pool):
    """A fresh wallet row per test."""
    import uuid

    address = "0x" + uuid.uuid4().hex + uuid.uuid4().hex[:8]
    with pool.connection() as conn:
        return str(conn.execute("insert into wallets (address) values (%s) returning id", (address,)).fetchone()["id"])


@pytest.fixture
def make_wallet(pool):
    """Factory: ``make_wallet()`` returns a fresh wallet id (a string)."""
    import uuid

    def _make() -> str:
        address = "0x" + (uuid.uuid4().hex + uuid.uuid4().hex)[:40]
        with pool.connection() as conn:
            return str(conn.execute("insert into wallets (address) values (%s) returning id", (address,)).fetchone()["id"])

    return _make
