"""Shared semantic tool-result cache."""
from __future__ import annotations

import random
from typing import Any, Dict, Optional, Sequence

from .util import jsonb, vec


class CacheRepo:
    def __init__(self, pool: Any) -> None:
        self.pool = pool

    def get_exact(self, key_hash: str) -> Optional[Dict[str, Any]]:
        with self.pool.connection() as conn:
            row = conn.execute(
                "update tool_cache set hits = hits + 1 where key_hash = %s and expires_at > now() "
                "returning result, created_at, extract(epoch from now() - created_at)::int as age_seconds",
                (key_hash,),
            ).fetchone()
        return dict(row) if row else None

    def get_semantic(self, tool: str, params_hash: str, embedding: Sequence[float], threshold: float) -> Optional[Dict[str, Any]]:
        with self.pool.connection() as conn:
            row = conn.execute(
                "select key_hash, result, similarity, extract(epoch from now() - created_at)::int as age_seconds "
                "from match_tool_cache(%s::text, %s::text, %s::vector, %s::real)",
                (tool, params_hash, vec(embedding), threshold),
            ).fetchone()
            if row:
                conn.execute("update tool_cache set hits = hits + 1 where key_hash = %s", (row["key_hash"],))
        return dict(row) if row else None

    def put(self, key_hash: str, tool: str, params_hash: str, query_text: str, embedding: Optional[Sequence[float]],
            result: Dict[str, Any], ttl_seconds: int) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                """
                insert into tool_cache (key_hash, tool, params_hash, query_text, embedding, result, expires_at)
                values (%s, %s, %s, %s, %s::vector, %s, now() + make_interval(secs => %s))
                on conflict (key_hash) do update set result = excluded.result, embedding = excluded.embedding,
                    created_at = now(), expires_at = excluded.expires_at
                """,
                (key_hash, tool, params_hash, query_text[:1000], vec(embedding) if embedding is not None else None,
                 jsonb(result), ttl_seconds),
            )
            if random.random() < 0.01:   # keep the table small without a scheduler
                conn.execute("delete from tool_cache where expires_at < now() - interval '1 hour'")

    def purge_expired(self) -> int:
        with self.pool.connection() as conn:
            return conn.execute("delete from tool_cache where expires_at < now()").rowcount
