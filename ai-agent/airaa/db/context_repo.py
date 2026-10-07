"""Watchlist and portfolio snapshots (per wallet)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from .util import as_uuid, jsonb, stringify_ids, vec


class ContextRepo:
    def __init__(self, pool: Any) -> None:
        self.pool = pool

    # ---- watchlist -----------------------------------------------------
    def add_watch(self, wallet_id: str, entity_type: str, entity_id: str, note: Optional[str],
                  embedding: Optional[Sequence[float]]) -> Dict[str, Any]:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                insert into watchlist (wallet_id, entity_type, entity_id, note, embedding)
                values (%s, %s, %s, %s, %s::vector)
                on conflict (wallet_id, entity_type, entity_id)
                do update set note = excluded.note, embedding = coalesce(excluded.embedding, watchlist.embedding)
                returning id, entity_type, entity_id, note, added_at
                """,
                (wallet_id, entity_type, entity_id, note, vec(embedding) if embedding is not None else None),
            ).fetchone()
        return stringify_ids(row)

    def list_watch(self, wallet_id: str) -> List[Dict[str, Any]]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "select id, entity_type, entity_id, note, added_at from watchlist where wallet_id = %s order by added_at desc",
                (wallet_id,),
            ).fetchall()
        return [stringify_ids(r) for r in rows]

    def count_watch(self, wallet_id: str) -> int:
        with self.pool.connection() as conn:
            return conn.execute("select count(*) as n from watchlist where wallet_id = %s", (wallet_id,)).fetchone()["n"]

    def remove_watch(self, wallet_id: str, watch_id: str) -> bool:
        wid = as_uuid(watch_id)
        if wid is None:
            return False
        with self.pool.connection() as conn:
            return conn.execute("delete from watchlist where id = %s and wallet_id = %s", (wid, wallet_id)).rowcount > 0

    def search_watch(self, wallet_id: str, embedding: Sequence[float], k: int, min_similarity: float) -> List[Dict[str, Any]]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "select * from match_watchlist(%s::uuid, %s::vector, %s::int, %s::real)", (wallet_id, vec(embedding), k, min_similarity)
            ).fetchall()
        return [dict(r) for r in rows]

    # ---- portfolio -----------------------------------------------------
    def add_snapshot(self, wallet_id: str, chain: str, holdings: Dict[str, Any], summary: str,
                     embedding: Optional[Sequence[float]]) -> Dict[str, Any]:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                insert into portfolio_snapshots (wallet_id, chain, holdings, summary, embedding)
                values (%s, %s, %s, %s, %s::vector) returning id, chain, fetched_at, summary
                """,
                (wallet_id, chain, jsonb(holdings), summary, vec(embedding) if embedding is not None else None),
            ).fetchone()
            # Keep history short: the latest few snapshots per wallet and chain are enough.
            conn.execute(
                """
                delete from portfolio_snapshots where id in (
                    select id from portfolio_snapshots where wallet_id = %s and chain = %s
                    order by fetched_at desc offset 5)
                """,
                (wallet_id, chain),
            )
        return stringify_ids(row)

    def latest_snapshots(self, wallet_id: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Most recent snapshot per chain."""
        with self.pool.connection() as conn:
            rows = conn.execute(
                """
                select distinct on (chain) id, chain, fetched_at, holdings, summary
                  from portfolio_snapshots where wallet_id = %s
                 order by chain, fetched_at desc
                """,
                (wallet_id,),
            ).fetchall()
        rows = sorted(rows, key=lambda r: r["fetched_at"], reverse=True)[:limit]
        return [stringify_ids(r) for r in rows]
