"""SessionManager write-through persistence, using an in-memory fake of ConversationStore."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from langchain_core.messages import AIMessage, HumanMessage

from airaa.memory import SessionManager


class FakeStore:
    """Mimics ConversationStore's contract without a database."""

    def __init__(self) -> None:
        self.rows: Dict[str, Dict[str, Any]] = {}
        self.fail = False

    def _check(self) -> None:
        if self.fail:
            raise RuntimeError("db down")

    def ensure(self, conversation_id: str, wallet_id: Optional[str] = None) -> Dict[str, Any]:
        self._check()
        return self.rows.setdefault(conversation_id, {
            "id": conversation_id, "wallet_id": wallet_id, "context": {}, "messages": [],
            "created_at": datetime.now(timezone.utc),
        })

    def load(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        self._check()
        row = self.rows.get(conversation_id)
        return dict(row, messages=list(row["messages"])) if row else None

    def append(self, conversation_id: str, messages: Sequence[Any]) -> None:
        self._check()
        self.rows[conversation_id]["messages"].extend(messages)

    def save_context(self, conversation_id: str, context: Dict[str, Any]) -> None:
        self._check()
        self.rows[conversation_id]["context"] = dict(context)

    def delete(self, conversation_id: str) -> bool:
        self._check()
        return self.rows.pop(conversation_id, None) is not None


def _turn(sessions: SessionManager, sid: str, q: str, a: str) -> None:
    sessions.record_turn(
        sid,
        HumanMessage(content=q, additional_kwargs={"timestamp": "t1"}),
        AIMessage(content=a, additional_kwargs={"timestamp": "t1", "research_data": {"query_intent": "price"}}),
    )


def test_turns_survive_a_restart() -> None:
    store = FakeStore()
    first = SessionManager(store=store)
    sid = first.get_or_create("session-12345")["id"]
    _turn(first, sid, "ETH price?", "About $3k")
    first.update_context(sid, {"last_query": "ETH price?"})

    second = SessionManager(store=store)  # fresh process, same database
    restored = second.get_or_create(sid)
    msgs = restored["chat_history"].messages
    assert [m.content for m in msgs] == ["ETH price?", "About $3k"]
    assert msgs[1].additional_kwargs["research_data"] == {"query_intent": "price"}
    assert restored["research_context"] == {"last_query": "ETH price?"}
    assert restored["message_count"] == 2


def test_get_reads_through_without_creating() -> None:
    store = FakeStore()
    sessions = SessionManager(store=store)
    assert sessions.get("missing-session") is None
    assert "missing-session" not in store.rows

    store.ensure("session-12345")
    assert sessions.get("session-12345")["id"] == "session-12345"


def test_delete_removes_memory_and_database() -> None:
    store = FakeStore()
    sessions = SessionManager(store=store)
    sid = sessions.get_or_create("session-12345")["id"]
    assert sessions.delete(sid) is True
    assert sid not in sessions.sessions and sid not in store.rows
    assert sessions.delete(sid) is False


def test_database_outage_never_breaks_the_request() -> None:
    store = FakeStore()
    sessions = SessionManager(store=store)
    sid = sessions.get_or_create("session-12345")["id"]
    store.fail = True
    _turn(sessions, sid, "hi", "hello")                      # persistence fails, memory still updated
    sessions.update_context(sid, {"k": "v"})
    assert len(sessions.get(sid)["chat_history"].messages) == 2
    assert sessions.get_or_create("another-session")["message_count"] == 0  # load failure falls back to a new session


def test_eviction_does_not_lose_persisted_history() -> None:
    store = FakeStore()
    sessions = SessionManager(max_sessions=1, store=store)
    _ = sessions.get_or_create("session-aaaaaa")
    _turn(sessions, "session-aaaaaa", "q", "a")
    sessions.get_or_create("session-bbbbbb")                 # evicts the first from memory
    assert "session-aaaaaa" not in sessions.sessions
    assert len(sessions.get_or_create("session-aaaaaa")["chat_history"].messages) == 2
