"""Long-term memories (per wallet)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from .util import as_uuid, stringify_ids, vec

_PUBLIC_COLUMNS = "id, conversation_id, kind, content, importance, pinned, created_at, last_accessed, access_count, expires_at"


class MemoryRepo:
    def __init__(self, pool: Any) -> None:
        self.pool = pool

    def insert(self, wallet_id: str, kind: str, content: str, importance: float, embedding: Sequence[float],
               conversation_id: Optional[str] = None, pinned: bool = False) -> str:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                insert into memories (wallet_id, conversation_id, kind, content, importance, pinned, embedding)
                values (%s, %s, %s, %s, %s, %s, %s::vector) returning id
                """,
                (wallet_id, conversation_id, kind, content, importance, pinned, vec(embedding)),
            ).fetchone()
        return str(row["id"])

    def search(self, wallet_id: str, embedding: Sequence[float], k: int, min_similarity: float) -> List[Dict[str, Any]]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "select * from match_memories(%s::uuid, %s::vector, %s::int, %s::real)", (wallet_id, vec(embedding), k, min_similarity)
            ).fetchall()
        return [stringify_ids(r) for r in rows]

    def merge(self, wallet_id: str, memory_id: str, importance: float, content: str, embedding: Sequence[float]) -> None:
        """A near-duplicate arrived: keep one row, take the newer wording and the higher importance."""
        with self.pool.connection() as conn:
            conn.execute(
                """
                update memories set content = %s, embedding = %s::vector, importance = greatest(importance, %s),
                       last_accessed = now(), access_count = access_count + 1
                 where id = %s and wallet_id = %s
                """,
                (content, vec(embedding), importance, memory_id, wallet_id),
            )

    def touch(self, wallet_id: str, ids: Sequence[str]) -> None:
        if not ids:
            return
        with self.pool.connection() as conn:
            conn.execute(
                "update memories set last_accessed = now(), access_count = access_count + 1 where wallet_id = %s and id = any(%s::uuid[])",
                (wallet_id, list(ids)),
            )

    def list(self, wallet_id: str, kind: Optional[str] = None, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                f"select {_PUBLIC_COLUMNS} from memories where wallet_id = %s and (%s::text is null or kind = %s) "
                "order by pinned desc, created_at desc limit %s offset %s",
                (wallet_id, kind, kind, limit, offset),
            ).fetchall()
        return [stringify_ids(r) for r in rows]

    def count(self, wallet_id: str) -> int:
        with self.pool.connection() as conn:
            return conn.execute("select count(*) as n from memories where wallet_id = %s", (wallet_id,)).fetchone()["n"]

    def update(self, wallet_id: str, memory_id: str, content: Optional[str] = None, importance: Optional[float] = None,
               pinned: Optional[bool] = None, embedding: Optional[Sequence[float]] = None) -> Optional[Dict[str, Any]]:
        mid = as_uuid(memory_id)
        if mid is None:
            return None
        with self.pool.connection() as conn:
            row = conn.execute(
                f"""
                update memories set content = coalesce(%s, content),
                       importance = coalesce(%s, importance),
                       pinned = coalesce(%s, pinned),
                       embedding = coalesce(%s::vector, embedding)
                 where id = %s and wallet_id = %s returning {_PUBLIC_COLUMNS}
                """,
                (content, importance, pinned, vec(embedding) if embedding is not None else None, mid, wallet_id),
            ).fetchone()
        return stringify_ids(row) if row else None

    def delete(self, wallet_id: str, memory_id: str) -> bool:
        mid = as_uuid(memory_id)
        if mid is None:
            return False
        with self.pool.connection() as conn:
            return conn.execute("delete from memories where id = %s and wallet_id = %s", (mid, wallet_id)).rowcount > 0

    def delete_all(self, wallet_id: str) -> int:
        with self.pool.connection() as conn:
            return conn.execute("delete from memories where wallet_id = %s", (wallet_id,)).rowcount

    def prune(self, wallet_id: str, keep: int) -> int:
        """Drop the least valuable unpinned memories beyond ``keep`` (low importance, then oldest)."""
        with self.pool.connection() as conn:
            return conn.execute(
                """
                delete from memories where id in (
                    select id from memories where wallet_id = %s and not pinned
                    order by importance desc, coalesce(last_accessed, created_at) desc
                    offset %s
                )
                """,
                (wallet_id, keep),
            ).rowcount
