"""Protocol knowledge base: documents, chunks, hybrid search."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from .util import jsonb, vec

# (chunk_index, content, embedding, metadata)
ChunkRow = Tuple[int, str, Sequence[float], Dict[str, Any]]


class KbRepo:
    def __init__(self, pool: Any) -> None:
        self.pool = pool

    def get_document(self, url: str) -> Optional[Dict[str, Any]]:
        with self.pool.connection() as conn:
            row = conn.execute("select id, content_hash from kb_documents where url = %s", (url,)).fetchone()
        return {"id": str(row["id"]), "content_hash": row["content_hash"]} if row else None

    def replace_document(self, source: str, url: str, title: str, content_hash: str, chunks: Sequence[ChunkRow]) -> str:
        """Upsert the document and swap its chunks atomically."""
        with self.pool.connection() as conn:
            with conn.transaction():
                row = conn.execute(
                    """
                    insert into kb_documents (source, url, title, content_hash) values (%s, %s, %s, %s)
                    on conflict (url) do update set source = excluded.source, title = excluded.title,
                        content_hash = excluded.content_hash, fetched_at = now()
                    returning id
                    """,
                    (source, url, title, content_hash),
                ).fetchone()
                doc_id = row["id"]
                conn.execute("delete from kb_chunks where document_id = %s", (doc_id,))
                with conn.cursor() as cur:
                    cur.executemany(
                        "insert into kb_chunks (document_id, chunk_index, content, embedding, metadata) values (%s, %s, %s, %s::vector, %s)",
                        [(doc_id, idx, content, vec(emb), jsonb(meta)) for idx, content, emb, meta in chunks],
                    )
        return str(doc_id)

    def delete_document(self, url: str) -> bool:
        with self.pool.connection() as conn:
            return conn.execute("delete from kb_documents where url = %s", (url,)).rowcount > 0

    def search(self, embedding: Sequence[float], query_text: str, k: int) -> List[Dict[str, Any]]:
        with self.pool.connection() as conn:
            rows = conn.execute("select * from match_kb(%s::vector, %s::text, %s::int)", (vec(embedding), query_text, k)).fetchall()
        return [{**r, "id": str(r["id"])} for r in rows]

    def stats(self) -> Dict[str, int]:
        with self.pool.connection() as conn:
            docs = conn.execute("select count(*) as n from kb_documents").fetchone()["n"]
            chunks = conn.execute("select count(*) as n from kb_chunks").fetchone()["n"]
        return {"documents": docs, "chunks": chunks}
