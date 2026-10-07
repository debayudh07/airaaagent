"""Wires repositories and services together from settings.

Everything is optional: with no ``DATABASE_URL`` the container is empty and the app behaves as it did before
persistence existed (in-memory guest sessions). Individual features also switch off on their own prerequisites:
wallet sign-in needs ``AIRAA_JWT_SECRET``; memory, knowledge base and semantic search need ``GEMINI_API_KEY``.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .config import Settings, get_settings

logger = logging.getLogger(__name__)

MIN_JWT_SECRET_CHARS = 32


@dataclass
class Services:
    settings: Settings
    pool: Any = None
    auth_repo: Any = None
    auth: Any = None
    embedder: Any = None
    memory_repo: Any = None
    memories: Any = None
    context_repo: Any = None
    context: Any = None
    kb_repo: Any = None
    kb: Any = None
    cache_repo: Any = None
    cache: Any = None
    vault_repo: Any = None
    vault: Any = None
    alerts_repo: Any = None
    retrieval: Any = None

    def features(self) -> Dict[str, Any]:
        """What is switched on, for ``/api/health`` and the UI."""
        return {
            "database": self.pool is not None,
            "wallet_auth": self.auth is not None,
            "memory": self.memories is not None,
            "watchlist": self.context is not None,
            "knowledge_base": self.kb is not None,
            "semantic_cache": self.cache is not None,
            "sealed_storage": self.vault is not None,
            "sealed_storage_backend": getattr(getattr(self.vault, "blobs", None), "name", None),
            "alerts": self.alerts_repo is not None,
        }


def build_services(settings: Settings, pool: Any = None) -> Services:
    from .db import get_pool

    pool = pool if pool is not None else get_pool()
    if pool is None:
        return Services(settings=settings)

    from .auth import AuthService
    from .cache import ToolCache
    from .context_service import ContextService
    from .db.alerts_repo import AlertsRepo
    from .db.auth_repo import AuthRepo
    from .db.cache_repo import CacheRepo
    from .db.context_repo import ContextRepo
    from .db.kb_repo import KbRepo
    from .db.memory_repo import MemoryRepo
    from .db.vault_repo import VaultRepo
    from .embeddings import Embedder
    from .kb import KnowledgeBase
    from .memory_store import MemoryService
    from .retrieval import Retrieval
    from .vault import VaultService, make_blob_store

    embedder = Embedder(settings) if settings.gemini_api_key else None
    s = Services(settings=settings, pool=pool, embedder=embedder)

    s.auth_repo = AuthRepo(pool)
    if len(settings.jwt_secret) >= MIN_JWT_SECRET_CHARS:
        s.auth = AuthService(s.auth_repo, settings)
    elif settings.jwt_secret:
        logger.warning("AIRAA_JWT_SECRET is shorter than %d characters; wallet sign-in is disabled", MIN_JWT_SECRET_CHARS)

    s.context_repo = ContextRepo(pool)
    s.context = ContextService(s.context_repo, embedder, settings)
    s.cache_repo = CacheRepo(pool)
    s.cache = ToolCache(s.cache_repo, embedder, settings) if settings.cache_enabled else None
    s.vault_repo = VaultRepo(pool)
    s.vault = VaultService(s.vault_repo, make_blob_store(settings, pool), embedder, settings)
    s.alerts_repo = AlertsRepo(pool)
    s.memory_repo = MemoryRepo(pool)
    s.kb_repo = KbRepo(pool)
    if embedder is not None:      # these need embeddings; listing and deleting memories does not
        s.memories = MemoryService(s.memory_repo, embedder, settings)
        s.kb = KnowledgeBase(s.kb_repo, embedder, settings)
    s.retrieval = Retrieval(embedder, s.memories, s.context, s.kb, settings)
    return s


_services: Optional[Services] = None
_lock = threading.Lock()


def get_services(settings: Optional[Settings] = None) -> Services:
    """Process-wide container, built on first use."""
    global _services
    with _lock:
        if _services is None:
            _services = build_services(settings or get_settings())
        return _services


def reset_services() -> None:
    """For tests."""
    global _services
    with _lock:
        _services = None
