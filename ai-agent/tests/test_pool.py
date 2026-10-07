"""LazyPool: per-process creation and the fail-fast circuit breaker."""
from __future__ import annotations

import os
import time

import pytest

from airaa.db import pool as pool_module
from airaa.db.pool import LazyPool, PoolUnavailable


class Conn:
    pass


class CM:
    def __init__(self, owner):
        self.owner = owner

    def __enter__(self):
        if self.owner.fail:
            from psycopg_pool import PoolTimeout

            raise PoolTimeout("no connection")
        return self.owner.conn

    def __exit__(self, *exc):
        self.owner.exits.append(exc[0])
        return False


class FakeRealPool:
    def __init__(self):
        self.conn, self.fail, self.exits = Conn(), False, []

    def connection(self):
        return CM(self)


def test_pool_is_created_on_first_use_not_at_construction():
    made = []
    lazy = LazyPool(lambda: made.append(1) or FakeRealPool())
    assert made == []
    with lazy.connection() as conn:
        assert isinstance(conn, Conn)
    with lazy.connection():
        pass
    assert made == [1]                                          # reused across calls


def test_a_pool_inherited_across_fork_is_replaced(monkeypatch):
    made = []
    lazy = LazyPool(lambda: made.append(1) or FakeRealPool())
    with lazy.connection():
        pass
    real_pid = os.getpid()
    monkeypatch.setattr(pool_module.os, "getpid", lambda: real_pid + 1)       # "we are now a forked worker"
    with lazy.connection():
        pass
    assert made == [1, 1]


def test_body_exceptions_propagate_and_release_the_connection():
    real = FakeRealPool()
    lazy = LazyPool(lambda: real)
    with pytest.raises(ValueError):
        with lazy.connection():
            raise ValueError("boom")
    assert real.exits == [ValueError]                           # the real pool saw the exception (so it can roll back)
    lazy.connection  # noqa: B018 - and a body error does not trip the breaker
    with lazy.connection():
        pass


def test_breaker_fails_fast_then_recovers(monkeypatch):
    real = FakeRealPool()
    real.fail = True
    lazy = LazyPool(lambda: real)
    with pytest.raises(PoolUnavailable):
        with lazy.connection():
            pass
    real.fail = False
    started = time.monotonic()
    with pytest.raises(PoolUnavailable, match="temporarily"):
        with lazy.connection():                                  # even though the DB is back, we are still paused
            pass
    assert time.monotonic() - started < 0.1                      # immediately, no waiting for a timeout

    lazy._down_until = 0                                         # the pause elapses
    with lazy.connection() as conn:
        assert isinstance(conn, Conn)


def test_get_pool_is_none_without_a_database_url():
    assert pool_module.get_pool() is None


def test_get_pool_does_not_connect_when_configured(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:1/db")
    pool = pool_module.get_pool()
    assert isinstance(pool, LazyPool) and pool._pool is None


# ----------------------------------------------------------------------- DATABASE_URL shared with Prisma
from airaa.config import normalize_database_url  # noqa: E402


def test_prisma_only_url_parameters_are_stripped():
    raw = "postgresql://postgres.abc:pw@aws-0-ap-south-1.pooler.supabase.com:6543/postgres?pgbouncer=true&connection_limit=1&sslmode=require&application_name=airaa"
    assert normalize_database_url(raw) == "postgresql://postgres.abc:pw@aws-0-ap-south-1.pooler.supabase.com:6543/postgres?sslmode=require&application_name=airaa"
    assert normalize_database_url("postgresql://u:p@h:6543/postgres?pgbouncer=true") == "postgresql://u:p@h:6543/postgres"


def test_urls_without_prisma_parameters_are_untouched():
    for url in ("", "postgresql://u:p@h:5432/postgres", "postgresql://u:p%40x@h/db?sslmode=require"):
        assert normalize_database_url(url) == url
    assert normalize_database_url("  postgresql://u:p@h/db  ") == "postgresql://u:p@h/db"


def test_settings_apply_the_normalisation(monkeypatch):
    from airaa.config import Settings

    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:6543/postgres?pgbouncer=true")
    assert Settings().database_url == "postgresql://u:p@h:6543/postgres"


def test_new_style_supabase_secret_key_is_sent_as_apikey_only():
    from airaa.config import Settings
    from airaa.vault.blobstore import SupabaseBlobStore

    new = SupabaseBlobStore(Settings(supabase_url="https://x.supabase.co", supabase_service_key="sb_secret_abc123"))
    assert new.headers == {"apikey": "sb_secret_abc123"}
    legacy = SupabaseBlobStore(Settings(supabase_url="https://x.supabase.co", supabase_service_key="eyJhbGciOi.legacy.jwt"))
    assert legacy.headers == {"Authorization": "Bearer eyJhbGciOi.legacy.jwt", "apikey": "eyJhbGciOi.legacy.jwt"}
