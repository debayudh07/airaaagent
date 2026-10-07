"""Conversation persistence: the Postgres half of :class:`airaa.memory.SessionManager`.

The session manager keeps hot conversations in process memory and writes through to this store, so a
restart or another gunicorn worker can reload them. Methods raise on database errors; the caller decides
whether that is fatal (it is not: the in-memory copy stays authoritative for the live request).

Ownership: ``wallet_id`` is NULL for guest conversations (anyone holding the id may use them, as before)
and set once a signed-in wallet creates or claims the conversation.
"""
from __future__ import annotations

import random
import threading
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .pool import get_pool
from .util import jsonb, stringify_ids

# (role, content, extra) where role is "human" | "ai" and extra is the message's additional_kwargs.
StoredMessage = Tuple[str, str, Dict[str, Any]]

GUEST_RETENTION_DAYS = 30
_PURGE_PROBABILITY = 0.005   # roughly once per 200 new conversations; no scheduler needed

_ROW = "id, wallet_id, title, context, message_count, created_at, last_activity"


def _owner(row: Dict[str, Any]) -> Dict[str, Any]:
    row["wallet_id"] = str(row["wallet_id"]) if row.get("wallet_id") else None
    return row


class ConversationStore:
    def __init__(self, pool: Any) -> None:
        self.pool = pool

    def ensure(self, conversation_id: str, wallet_id: Optional[str] = None) -> Dict[str, Any]:
        """Create the conversation if missing and return its row. Never reassigns an owned conversation."""
        if random.random() < _PURGE_PROBABILITY:
            try:
                self.purge_stale_guests()
            except Exception:  # noqa: BLE001 - housekeeping must never break a request
                pass
        with self.pool.connection() as conn:
            row = conn.execute(
                f"""
                insert into conversations (id, wallet_id) values (%s, %s)
                on conflict (id) do update set last_activity = now()
                returning {_ROW}
                """,
                (conversation_id, wallet_id),
            ).fetchone()
        return _owner(row)

    def load(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Conversation row plus ordered ``messages`` (list of :data:`StoredMessage`), or ``None``."""
        with self.pool.connection() as conn:
            row = conn.execute(f"select {_ROW} from conversations where id = %s", (conversation_id,)).fetchone()
            if row is None:
                return None
            msgs = conn.execute(
                "select role, content, extra from messages where conversation_id = %s order by id", (conversation_id,)
            ).fetchall()
        row = _owner(row)
        row["messages"] = [(m["role"], m["content"], m["extra"] or {}) for m in msgs]
        return row

    def append(self, conversation_id: str, messages: Sequence[StoredMessage]) -> None:
        first_human = next((content for role, content, _ in messages if role == "human"), "")
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    "insert into messages (conversation_id, role, content, extra) values (%s, %s, %s, %s)",
                    [(conversation_id, role, content, jsonb(extra)) for role, content, extra in messages],
                )
                cur.execute(
                    "update conversations set message_count = message_count + %s, last_activity = now(), "
                    "title = coalesce(title, nullif(left(%s, 80), '')) where id = %s",
                    (len(messages), first_human.strip(), conversation_id),
                )

    def save_context(self, conversation_id: str, context: Dict[str, Any]) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                "update conversations set context = %s, last_activity = now() where id = %s",
                (jsonb(context), conversation_id),
            )

    def purge_stale_guests(self, days: int = GUEST_RETENTION_DAYS) -> int:
        """Delete guest conversations (no wallet) untouched for ``days`` days. Wallet-owned ones are never auto-deleted."""
        with self.pool.connection() as conn:
            return conn.execute(
                "delete from conversations where wallet_id is null and last_activity < now() - make_interval(days => %s)", (days,)
            ).rowcount

    def claim(self, conversation_id: str, wallet_id: str) -> bool:
        """Attach a guest conversation to a wallet. False if it is missing or already owned (by anyone)."""
        with self.pool.connection() as conn:
            row = conn.execute(
                "update conversations set wallet_id = %s where id = %s and wallet_id is null returning id",
                (wallet_id, conversation_id),
            ).fetchone()
        return row is not None

    def list_for_wallet(self, wallet_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "select id, title, message_count, created_at, last_activity from conversations "
                "where wallet_id = %s and message_count > 0 order by last_activity desc limit %s",
                (wallet_id, limit),
            ).fetchall()
        return [stringify_ids(r) for r in rows]

    def delete(self, conversation_id: str) -> bool:
        with self.pool.connection() as conn:
            cur = conn.execute("delete from conversations where id = %s", (conversation_id,))
            return cur.rowcount > 0

    def export_wallet(self, wallet_id: str) -> List[Dict[str, Any]]:
        """Every conversation of a wallet with its messages (for the data export)."""
        with self.pool.connection() as conn:
            convs = conn.execute(
                "select id, title, created_at, last_activity from conversations where wallet_id = %s order by created_at",
                (wallet_id,),
            ).fetchall()
            out = []
            for conv in convs:
                msgs = conn.execute(
                    "select role, content, extra, created_at from messages where conversation_id = %s order by id", (conv["id"],)
                ).fetchall()
                out.append({**stringify_ids(conv), "messages": [stringify_ids(m) for m in msgs]})
        return out


_default: Optional[ConversationStore] = None
_default_lock = threading.Lock()


def get_conversation_store() -> Optional[ConversationStore]:
    """Process-wide store, or ``None`` when no database is configured."""
    global _default
    with _default_lock:
        if _default is None:
            pool = get_pool()
            if pool is not None:
                _default = ConversationStore(pool)
        return _default
