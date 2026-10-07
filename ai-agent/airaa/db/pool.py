"""Connection pool: lazy, per-process, and fail-fast.

* Lazy and pid-aware, because gunicorn runs with ``preload_app`` (the app is imported in the master and then forked):
  a pool created before the fork would be shared by every worker. The real pool is created on first use *in each
  process*, so the master never opens a connection.
* Circuit breaker: when the database cannot be reached, calls fail immediately for a short while instead of each
  waiting out the pool timeout. Callers already treat database errors as non-fatal (see ``SessionManager``).
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Iterator, Optional

from ..config import get_settings

logger = logging.getLogger(__name__)

BREAKER_SECONDS = 15.0
CONNECT_TIMEOUT_SECONDS = 5.0


class PoolUnavailable(RuntimeError):
    """The database is unreachable (or recently was); try again later."""


class LazyPool:
    """Quacks like ``psycopg_pool.ConnectionPool`` for the one method the repositories use: ``connection()``."""

    def __init__(self, factory: Callable[[], Any]) -> None:
        self._factory = factory
        self._pool: Optional[Any] = None
        self._pid: Optional[int] = None
        self._down_until = 0.0
        self._lock = threading.Lock()

    def _get(self) -> Any:
        with self._lock:
            if self._pool is None or self._pid != os.getpid():
                # A pool inherited across fork() is abandoned, not closed: closing would tear down the parent's sockets.
                self._pool, self._pid = self._factory(), os.getpid()
            return self._pool

    def _trip(self, exc: BaseException) -> None:
        self._down_until = time.monotonic() + BREAKER_SECONDS
        logger.error("Database unavailable (%s); pausing database calls for %.0fs", type(exc).__name__, BREAKER_SECONDS)

    @contextmanager
    def connection(self) -> Iterator[Any]:
        from psycopg import OperationalError
        from psycopg_pool import PoolTimeout

        if time.monotonic() < self._down_until:
            raise PoolUnavailable("database temporarily unavailable")
        try:
            cm = self._get().connection()
            conn = cm.__enter__()
        except (PoolTimeout, OperationalError) as exc:
            self._trip(exc)
            raise PoolUnavailable("database unavailable") from exc
        try:
            yield conn
        except BaseException:
            if not cm.__exit__(*sys.exc_info()):   # commits/rolls back and returns the connection to the pool
                raise
        else:
            cm.__exit__(None, None, None)

    def close(self) -> None:
        with self._lock:
            if self._pool is not None and self._pid == os.getpid():
                self._pool.close()
            self._pool = None


_pool: Optional[LazyPool] = None
_failed = False
_lock = threading.Lock()


def _make_real_pool(url: str, size: int) -> Any:
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    # Supabase's transaction pooler (port 6543) does not support server-side prepared statements.
    pool = ConnectionPool(
        url, min_size=1, max_size=size, open=False, timeout=CONNECT_TIMEOUT_SECONDS,
        kwargs={"row_factory": dict_row, "prepare_threshold": None, "connect_timeout": 5},
    )
    pool.open(wait=False)
    logger.info("Database pool opened in pid %d (max_size=%d)", os.getpid(), size)
    return pool


def get_pool() -> Optional[LazyPool]:
    """Shared pool, or ``None`` when no database is configured. Does not connect until first use."""
    global _pool, _failed
    with _lock:
        if _pool is not None or _failed:
            return _pool
        cfg = get_settings()
        if not cfg.database_url:
            _failed = True
            return None
        url, size = cfg.database_url, cfg.db_pool_size
        _pool = LazyPool(lambda: _make_real_pool(url, size))
        return _pool
