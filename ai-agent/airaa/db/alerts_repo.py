"""Alert rules (scheduled research) and the inbox."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .util import as_uuid, jsonb, stringify_ids

_RULE_COLUMNS = ("id, name, query_text, condition_text, interval_minutes, enabled, next_run_at, last_run_at, last_error, "
                 "runs_today, run_day, created_at")


class AlertsRepo:
    def __init__(self, pool: Any) -> None:
        self.pool = pool

    # ---- rules ---------------------------------------------------------
    def create_rule(self, wallet_id: str, name: str, query_text: str, condition_text: Optional[str], interval_minutes: int) -> Dict[str, Any]:
        with self.pool.connection() as conn:
            row = conn.execute(
                f"insert into alert_rules (wallet_id, name, query_text, condition_text, interval_minutes) "
                f"values (%s, %s, %s, %s, %s) returning {_RULE_COLUMNS}",
                (wallet_id, name, query_text, condition_text, interval_minutes),
            ).fetchone()
        return stringify_ids(row)

    def list_rules(self, wallet_id: str) -> List[Dict[str, Any]]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                f"select {_RULE_COLUMNS} from alert_rules where wallet_id = %s order by created_at desc", (wallet_id,)
            ).fetchall()
        return [stringify_ids(r) for r in rows]

    def count_rules(self, wallet_id: str) -> int:
        with self.pool.connection() as conn:
            return conn.execute("select count(*) as n from alert_rules where wallet_id = %s", (wallet_id,)).fetchone()["n"]

    def update_rule(self, wallet_id: str, rule_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
        rid = as_uuid(rule_id)
        allowed = {"name", "query_text", "condition_text", "interval_minutes", "enabled"}
        sets = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if rid is None or not sets:
            return None
        assignments = ", ".join(f"{k} = %s" for k in sets)
        with self.pool.connection() as conn:
            row = conn.execute(
                f"update alert_rules set {assignments} where id = %s and wallet_id = %s returning {_RULE_COLUMNS}",
                (*sets.values(), rid, wallet_id),
            ).fetchone()
        return stringify_ids(row) if row else None

    def delete_rule(self, wallet_id: str, rule_id: str) -> bool:
        rid = as_uuid(rule_id)
        if rid is None:
            return False
        with self.pool.connection() as conn:
            return conn.execute("delete from alert_rules where id = %s and wallet_id = %s", (rid, wallet_id)).rowcount > 0

    def claim_due(self, limit: int, max_runs_per_day: int) -> List[Dict[str, Any]]:
        """Atomically pick due rules and push their next run forward, so concurrent runners never double-run one.

        At-most-once by design: a crash after the claim skips that occurrence rather than repeating it.
        """
        with self.pool.connection() as conn:
            rows = conn.execute(
                """
                update alert_rules r set
                    next_run_at = now() + make_interval(mins => r.interval_minutes),
                    last_run_at = now(),
                    runs_today = case when r.run_day = current_date then r.runs_today + 1 else 1 end,
                    run_day = current_date
                where r.id in (
                    select id from alert_rules
                     where enabled and next_run_at <= now()
                       and (run_day is distinct from current_date or runs_today < %s)
                     order by next_run_at limit %s
                     for update skip locked)
                returning r.id, r.wallet_id, r.name, r.query_text, r.condition_text
                """,
                (max_runs_per_day, limit),
            ).fetchall()
        return [stringify_ids(r) for r in rows]

    def record_result(self, rule_id: str, error: Optional[str]) -> None:
        with self.pool.connection() as conn:
            conn.execute("update alert_rules set last_error = %s where id = %s", (error[:300] if error else None, rule_id))

    # ---- inbox ---------------------------------------------------------
    def add_inbox(self, wallet_id: str, rule_id: Optional[str], title: str, summary: str,
                  research_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        with self.pool.connection() as conn:
            row = conn.execute(
                "insert into inbox (wallet_id, rule_id, title, summary, research_data) values (%s, %s, %s, %s, %s) "
                "returning id, title, created_at",
                (wallet_id, rule_id, title, summary, jsonb(research_data) if research_data is not None else None),
            ).fetchone()
            conn.execute(  # bounded: keep the newest 200 items per wallet
                "delete from inbox where id in (select id from inbox where wallet_id = %s order by created_at desc offset 200)",
                (wallet_id,),
            )
        return stringify_ids(row)

    def list_inbox(self, wallet_id: str, unread_only: bool = False, limit: int = 50) -> List[Dict[str, Any]]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "select id, rule_id, title, summary, research_data, created_at, read_at from inbox "
                "where wallet_id = %s and (not %s or read_at is null) order by created_at desc limit %s",
                (wallet_id, unread_only, limit),
            ).fetchall()
        return [stringify_ids(r) for r in rows]

    def unread_count(self, wallet_id: str) -> int:
        with self.pool.connection() as conn:
            return conn.execute("select count(*) as n from inbox where wallet_id = %s and read_at is null", (wallet_id,)).fetchone()["n"]

    def mark_read(self, wallet_id: str, inbox_id: Optional[str] = None) -> int:
        """Mark one item (or, with ``inbox_id=None``, everything) read."""
        iid = as_uuid(inbox_id) if inbox_id else None
        if inbox_id and iid is None:
            return 0
        with self.pool.connection() as conn:
            return conn.execute(
                "update inbox set read_at = now() where wallet_id = %s and read_at is null and (%s::uuid is null or id = %s::uuid)",
                (wallet_id, iid, iid),
            ).rowcount

    def delete_inbox(self, wallet_id: str, inbox_id: str) -> bool:
        iid = as_uuid(inbox_id)
        if iid is None:
            return False
        with self.pool.connection() as conn:
            return conn.execute("delete from inbox where id = %s and wallet_id = %s", (iid, wallet_id)).rowcount > 0
