"""Gemini text embeddings (one client for memory, tool cache, watchlist, knowledge base and artifact search).

Vectors are truncated to ``settings.embedding_dim`` (768, matching the ``vector(768)`` columns) via the API's
``output_dimensionality`` and then L2-normalised, because truncated Gemini embeddings are not unit length and
the SQL uses cosine distance.
"""
from __future__ import annotations

import asyncio
import logging
import math
import random
import time
from typing import Any, List, Optional, Sequence

from .config import Settings, get_settings

logger = logging.getLogger(__name__)

BATCH_SIZE = 100          # the API accepts up to 100 texts per call
MAX_CHARS = 8000          # ~2k tokens; longer inputs are truncated rather than rejected
_RETRIES = 3


class EmbeddingUnavailable(RuntimeError):
    """No API key, or the embedding service kept failing."""


def _normalise(vector: Sequence[float]) -> List[float]:
    norm = math.sqrt(sum(v * v for v in vector))
    return [v / norm for v in vector] if norm else list(vector)


def _clean(texts: Sequence[str]) -> List[str]:
    return [(t or " ").strip()[:MAX_CHARS] or " " for t in texts]


class Embedder:
    """``embed_*`` take ``task``: ``"document"`` (stored text), ``"query"`` (a search string) or
    ``"similarity"`` (symmetric text-to-text comparison, used by the tool cache)."""

    def __init__(self, settings: Optional[Settings] = None, client: Any = None) -> None:
        self.settings = settings or get_settings()
        self._client = client  # tests inject a fake with .models.embed_content / .aio.models.embed_content

    @property
    def available(self) -> bool:
        return self._client is not None or bool(self.settings.gemini_api_key)

    def _sync_client(self) -> Any:
        if self._client is None:
            if not self.settings.gemini_api_key:
                raise EmbeddingUnavailable("GEMINI_API_KEY is not configured")
            from google import genai

            self._client = genai.Client(api_key=self.settings.gemini_api_key)
        return self._client

    def _config(self, task: str) -> Any:
        from google.genai import types

        task_type = {"query": "RETRIEVAL_QUERY", "similarity": "SEMANTIC_SIMILARITY"}.get(task, "RETRIEVAL_DOCUMENT")
        return types.EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=self.settings.embedding_dim,
        )

    def _parse(self, response: Any, expected: int) -> List[List[float]]:
        vectors = [_normalise(e.values) for e in (response.embeddings or [])]
        if len(vectors) != expected or any(len(v) != self.settings.embedding_dim for v in vectors):
            raise EmbeddingUnavailable("Embedding service returned an unexpected shape")
        return vectors

    # ---- sync (Flask handlers, ingest script) -------------------------
    def embed_sync(self, texts: Sequence[str], task: str = "document") -> List[List[float]]:
        client = self._sync_client()
        out: List[List[float]] = []
        for start in range(0, len(texts), BATCH_SIZE):
            batch = _clean(texts[start:start + BATCH_SIZE])
            for attempt in range(_RETRIES):
                try:
                    response = client.models.embed_content(model=self.settings.embedding_model, contents=batch, config=self._config(task))
                    out.extend(self._parse(response, len(batch)))
                    break
                except EmbeddingUnavailable:
                    raise
                except Exception as exc:  # noqa: BLE001 - quota/availability errors are retried, then surfaced
                    if attempt == _RETRIES - 1:
                        raise EmbeddingUnavailable(f"Embedding failed: {type(exc).__name__}") from exc
                    time.sleep(0.5 * (2 ** attempt) + random.random() * 0.2)
        return out

    def embed_one_sync(self, text: str, task: str = "query") -> List[float]:
        return self.embed_sync([text], task)[0]

    # ---- async (agent pipeline) ---------------------------------------
    async def aembed(self, texts: Sequence[str], task: str = "document") -> List[List[float]]:
        """Runs the sync client in a worker thread: one cached client, safe across the per-request event loops."""
        return await asyncio.to_thread(self.embed_sync, list(texts), task)

    async def aembed_one(self, text: str, task: str = "query") -> List[float]:
        return (await self.aembed([text], task))[0]


_default: Optional[Embedder] = None


def get_embedder() -> Optional[Embedder]:
    """Shared embedder, or ``None`` when no Gemini key is configured."""
    global _default
    if _default is None:
        candidate = Embedder(get_settings())
        if not candidate.available:
            return None
        _default = candidate
    return _default
