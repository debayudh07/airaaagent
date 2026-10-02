"""In-memory conversation sessions with TTL and size limits.

State lives in process memory, so it is lost on restart and not shared between gunicorn
workers. That is acceptable for this deployment; swap :class:`SessionManager` for a Redis-backed
implementation if you scale out.
"""
from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

logger = logging.getLogger(__name__)


class SessionManager:
    def __init__(self, max_sessions: int = 200, ttl_hours: int = 24) -> None:
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.max_sessions = max_sessions
        self.ttl = timedelta(hours=ttl_hours)
        self._lock = threading.RLock()

    # ---- lifecycle -----------------------------------------------------
    def get_or_create(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            session_id = session_id or str(uuid.uuid4())
            self._evict()
            now = datetime.now()
            session = self.sessions.get(session_id)
            if session is None:
                session = {
                    "id": session_id,
                    "chat_history": InMemoryChatMessageHistory(),
                    "created_at": now,
                    "last_activity": now,
                    "message_count": 0,
                    "research_context": {},
                }
                self.sessions[session_id] = session
                logger.info("Created session %s", session_id)
            else:
                session["last_activity"] = now
            return session

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self.sessions.get(session_id)

    def delete(self, session_id: str) -> bool:
        with self._lock:
            return self.sessions.pop(session_id, None) is not None

    def update_context(self, session_id: str, context: Dict[str, Any]) -> None:
        with self._lock:
            session = self.sessions.get(session_id)
            if session:
                session["research_context"].update(context)
                session["last_activity"] = datetime.now()

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

            cfg = get_settings()
            _default = SessionManager(max_sessions=cfg.max_sessions, ttl_hours=cfg.session_ttl_hours)
        return _default
