"""Protocol knowledge base: chunking, incremental ingest and hybrid retrieval."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from typing import Any, Dict, List, Optional

from ..config import Settings, get_settings

logger = logging.getLogger(__name__)

CHUNK_CHARS = 2400      # about 600 tokens
OVERLAP_CHARS = 320     # about 80 tokens


def chunk_text(text: str, size: int = CHUNK_CHARS, overlap: int = OVERLAP_CHARS) -> List[str]:
    """Split on paragraph boundaries into ~``size``-char chunks, carrying ``overlap`` chars of context forward."""
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    if not text:
        return []
    paragraphs: List[str] = []
    for para in text.split("\n\n"):
        while len(para) > size:  # a single huge paragraph: cut at a sentence/space near the limit
            cut = max(para.rfind(". ", 0, size), para.rfind("\n", 0, size), para.rfind(" ", 0, size))
            cut = cut + 1 if cut > size // 2 else size
            paragraphs.append(para[:cut].strip())
            para = para[cut:].strip()
        if para:
            paragraphs.append(para)

    chunks: List[str] = []
    current = ""
    for para in paragraphs:
        if current and len(current) + len(para) + 2 > size:
            chunks.append(current)
            tail = current[-overlap:]
            tail = tail[tail.find(" ") + 1:] if " " in tail else tail   # do not start mid-word
            current = f"{tail}\n\n{para}"
        else:
            current = f"{current}\n\n{para}" if current else para
    if current:
        chunks.append(current)
    return chunks


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class KnowledgeBase:
    def __init__(self, repo: Any, embedder: Any, settings: Optional[Settings] = None) -> None:
        self.repo, self.embedder = repo, embedder
        self.settings = settings or get_settings()

    # ---- ingest (sync: used by the CLI) -------------------------------
    def ingest_document(self, source: str, url: str, title: str, text: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Returns ``"unchanged"``, ``"added"``, ``"updated"`` or ``"empty"``. Unchanged text is not re-embedded."""
        digest = content_hash(text)
        existing = self.repo.get_document(url)
        if existing and existing["content_hash"] == digest:
            return "unchanged"
        pieces = chunk_text(text)
        if not pieces:
            return "empty"
        vectors = self.embedder.embed_sync([f"{title}\n\n{p}" for p in pieces], "document")
        meta = {"source": source, "title": title, "url": url, **(metadata or {})}
        self.repo.replace_document(source, url, title, digest, [(i, p, v, meta) for i, (p, v) in enumerate(zip(pieces, vectors))])
        return "updated" if existing else "added"

    # ---- retrieval -----------------------------------------------------
    async def search(self, query: str, vector: Optional[List[float]] = None) -> List[Dict[str, Any]]:
        cfg = self.settings
        vector = vector or await self.embedder.aembed_one(query, "query")
        rows = await asyncio.to_thread(self.repo.search, vector, query, cfg.kb_top_k)
        return [r for r in rows if float(r["similarity"]) >= cfg.kb_min_similarity]


def format_block(rows: List[Dict[str, Any]], max_chars: int = 900) -> str:
    """Prompt block with citable sources. Empty when there is nothing relevant."""
    if not rows:
        return ""
    seen: Dict[str, int] = {}
    parts: List[str] = []
    for row in rows:
        n = seen.setdefault(row["url"], len(seen) + 1)
        body = row["content"].strip()
        parts.append(f"[{n}] {row['title']} ({row['url']})\n{body[:max_chars]}{'…' if len(body) > max_chars else ''}")
    return ("REFERENCE DOCUMENTATION (retrieved from the knowledge base; ground protocol or API explanations in it and "
            "cite the source title or URL you used; if it does not answer the question, ignore it):\n" + "\n\n".join(parts))


def citations(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen, out = set(), []
    for row in rows:
        if row["url"] not in seen:
            seen.add(row["url"])
            out.append({"title": row["title"], "url": row["url"], "similarity": round(float(row["similarity"]), 3)})
    return out
