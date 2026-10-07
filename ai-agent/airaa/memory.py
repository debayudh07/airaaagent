"""Conversation sessions: a bounded in-process cache with optional write-through to Postgres.

Live conversations are served from memory (TTL and size limits apply). When a
:class:`~airaa.db.store.ConversationStore` is configured every turn is also persisted, and a
conversation that is not in memory (restart, eviction, another gunicorn worker) is reloaded from it.
Database failures are logged and never fail the request: the in-memory copy stays authoritative.
"""
from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

if TYPE_CHECKING:
    from .db.store import ConversationStore

logger = logging.getLogger(__name__)


class SessionManager:
    def __init__(self, max_sessions: int = 200, ttl_hours: int = 24, store: Optional["ConversationStore"] = None) -> None:
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.max_sessions = max_sessions
        self.ttl = timedelta(hours=ttl_hours)
        self.store = store
        self._lock = threading.RLock()

    # ---- persistence ---------------------------------------------------
    def _load_persisted(self, session_id: str, create: bool, wallet_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Rebuild a session from the store (creating its row if asked). Call outside the lock."""
        if self.store is None:
            return None
        try:
            row = self.store.load(session_id)
            if row is None and create:
                self.store.ensure(session_id, wallet_id)
                row = self.store.load(session_id)
        except Exception:
            logger.exception("Could not load session %s from the database", session_id)
            return None
        if row is None:
            return None
        history = InMemoryChatMessageHistory()
        for role, content, extra in row["messages"]:
            cls = AIMessage if role == "ai" else HumanMessage
            history.add_message(cls(content=content, additional_kwargs=dict(extra)))
        return {
            "id": session_id,
            "wallet_id": row.get("wallet_id"),
            "chat_history": history,
            "created_at": row["created_at"].astimezone().replace(tzinfo=None),
            "last_activity": datetime.now(),
            "message_count": len(history.messages),
            "research_context": dict(row["context"] or {}),
        }

    def _persist(self, action: str, session_id: str, fn: Callable[..., Any], *args: Any) -> None:
        try:
            fn(session_id, *args)
        except Exception:
            logger.exception("Could not %s session %s in the database", action, session_id)

    # ---- lifecycle -----------------------------------------------------
    def get_or_create(self, session_id: Optional[str] = None, wallet_id: Optional[str] = None) -> Dict[str, Any]:
        """Return the session, creating it (owned by ``wallet_id`` if given) when it does not exist.

        Existing sessions are returned as they are: ownership is never changed here, see :meth:`claim`.
        """
        session_id = session_id or str(uuid.uuid4())
        with self._lock:
            self._evict()
            session = self.sessions.get(session_id)
            if session is not None:
                session["last_activity"] = datetime.now()
                return session
        loaded = self._load_persisted(session_id, create=True, wallet_id=wallet_id)  # database I/O outside the lock
        with self._lock:
            session = self.sessions.get(session_id)  # another thread may have won the race
            if session is None:
                now = datetime.now()
                session = loaded or {
                    "id": session_id,
                    "wallet_id": wallet_id,
                    "chat_history": InMemoryChatMessageHistory(),
                    "created_at": now,
                    "last_activity": now,
                    "message_count": 0,
                    "research_context": {},
                }
                self.sessions[session_id] = session
                logger.info("%s session %s", "Restored" if loaded else "Created", session_id)
            else:
                session["last_activity"] = datetime.now()
            return session

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            session = self.sessions.get(session_id)
        if session is not None or self.store is None:
            return session
        loaded = self._load_persisted(session_id, create=False)
        if loaded is None:
            return None
        with self._lock:
            return self.sessions.setdefault(session_id, loaded)

    def claim(self, session_id: str, wallet_id: str) -> bool:
        """Attach a guest conversation to ``wallet_id``. True if it now belongs to that wallet."""
        session = self.get(session_id)
        if session is None:
            return False
        with self._lock:
            owner = session.get("wallet_id")
            if owner == wallet_id:
                return True
            if owner is not None:
                return False
            session["wallet_id"] = wallet_id
        if self.store is not None:
            try:
                if not self.store.claim(session_id, wallet_id):
                    # Lost a race (or the row is gone): trust the database.
                    row = self.store.load(session_id)
                    with self._lock:
                        session["wallet_id"] = row["wallet_id"] if row else None
                    return bool(row) and row["wallet_id"] == wallet_id
            except Exception:
                logger.exception("Could not claim session %s in the database", session_id)
        return True

    def list_for_wallet(self, wallet_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Conversations owned by ``wallet_id``, newest first (database if configured, else this process)."""
        if self.store is not None:
            try:
                return self.store.list_for_wallet(wallet_id, limit)
            except Exception:
                logger.exception("Could not list conversations for %s", wallet_id)
        with self._lock:
            owned = [s for s in self.sessions.values() if s.get("wallet_id") == wallet_id and s["message_count"] > 0]
        owned.sort(key=lambda s: s["last_activity"], reverse=True)
        rows = []
        for s in owned[:limit]:
            first = next((m.content for m in s["chat_history"].messages if m.type == "human"), "")
            rows.append({"id": s["id"], "title": str(first)[:80] or None, "message_count": s["message_count"],
                         "created_at": s["created_at"].isoformat(), "last_activity": s["last_activity"].isoformat()})
        return rows

    def delete(self, session_id: str) -> bool:
        with self._lock:
            removed = self.sessions.pop(session_id, None) is not None
        if self.store is not None:
            try:
                removed = self.store.delete(session_id) or removed
            except Exception:
                logger.exception("Could not delete session %s from the database", session_id)
        return removed

    def update_context(self, session_id: str, context: Dict[str, Any]) -> None:
        with self._lock:
            session = self.sessions.get(session_id)
            if not session:
                return
            session["research_context"].update(context)
            session["last_activity"] = datetime.now()
            snapshot = dict(session["research_context"])
        if self.store is not None:
            self._persist("save context for", session_id, self.store.save_context, snapshot)

    def _evict(self) -> None:
        now = datetime.now()
        for sid in [s for s, v in self.sessions.items() if now - v["last_activity"] > self.ttl]:
            del self.sessions[sid]
        overflow = len(self.sessions) - self.max_sessions + 1  # leave room for the new one
        if overflow > 0:
            for sid, _ in sorted(self.sessions.items(), key=lambda kv: kv[1]["last_activity"])[:overflow]:
                del self.sessions[sid]

    # ---- history -------------------------------------------------------
    def record_turn(self, session_id: str, user: HumanMessage, ai: AIMessage) -> None:
        with self._lock:
            session = self.sessions.get(session_id)
            if not session:
                return
            history: InMemoryChatMessageHistory = session["chat_history"]
            history.add_message(user)
            history.add_message(ai)
            session["message_count"] = len(history.messages)
            session["last_activity"] = datetime.now()
        if self.store is not None:
            self._persist("record turn for", session_id, self.store.append, [
                ("human", str(user.content), dict(user.additional_kwargs or {})),
                ("ai", str(ai.content), dict(ai.additional_kwargs or {})),
            ])

    def recent_messages(self, session_id: str, limit: int, max_chars: int = 1500) -> List[BaseMessage]:
        """Last ``limit`` messages as LLM input. Long AI answers are trimmed to save tokens."""
        with self._lock:
            session = self.sessions.get(session_id)
            messages = list(session["chat_history"].messages[-limit:]) if session else []
        trimmed: List[BaseMessage] = []
        for m in messages:
            text = m.content if isinstance(m.content, str) else str(m.content)
            if len(text) > max_chars:
                text = text[:max_chars] + " …[truncated]"
            trimmed.append(AIMessage(content=text) if isinstance(m, AIMessage) else HumanMessage(content=text))
        return trimmed

    def history_digest(self, session_id: str, limit: int = 6) -> str:
        """Compact text view of recent turns, for planner prompts."""
        lines = []
        for m in self.recent_messages(session_id, limit, max_chars=200):
            role = "User" if isinstance(m, HumanMessage) else "Assistant"
            lines.append(f"{role}: {m.content}")
        return "\n".join(lines)


_default: Optional[SessionManager] = None
_default_lock = threading.Lock()


def get_session_manager() -> SessionManager:
    """Process-wide session store, created on first use from settings."""
    global _default
    with _default_lock:
        if _default is None:
            from .config import get_settings
            from .db import get_conversation_store

            cfg = get_settings()
            _default = SessionManager(
                max_sessions=cfg.max_sessions, ttl_hours=cfg.session_ttl_hours, store=get_conversation_store()
            )
        return _default
