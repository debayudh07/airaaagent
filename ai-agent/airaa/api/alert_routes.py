"""Alert rules (scheduled research), the inbox, and the cron trigger.

``POST /api/internal/alerts/run`` is meant for a scheduler (Cloudflare cron, GitHub Actions, Render cron). It is
authenticated by the ``X-Cron-Secret`` header and disabled unless AIRAA_CRON_SECRET is set.
"""
from __future__ import annotations

import hmac
import logging
import threading
from typing import Any

from flask import Flask, jsonify, request

from ..config import Settings
from .deps import ApiError, json_object, need, wallet_required

logger = logging.getLogger(__name__)
MIN_INTERVAL_MINUTES = 15
MAX_INTERVAL_MINUTES = 60 * 24 * 30
_run_lock = threading.Lock()


def _text(body: dict, key: str, limit: int, required: bool = True):
    value = body.get(key)
    if value is None or value == "":
        if required:
            raise ApiError(f"'{key}' is required")
        return None
    if not isinstance(value, str) or len(value.strip()) > limit:
        raise ApiError(f"'{key}' must be a string of at most {limit} characters")
    return value.strip()


def _interval(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not MIN_INTERVAL_MINUTES <= value <= MAX_INTERVAL_MINUTES:
        raise ApiError(f"'interval_minutes' must be an integer between {MIN_INTERVAL_MINUTES} and {MAX_INTERVAL_MINUTES}")
    return value


def register_alert_routes(app: Flask, settings: Settings, services: Any, limiter: Any) -> None:
    def repo():
        return need(services.alerts_repo, "Alerts")

    # ------------------------------------------------------------------ rules
    @app.get("/api/alerts")
    def list_alerts():
        wallet = wallet_required(services)
        return jsonify({"success": True, "alerts": repo().list_rules(wallet.id),
                        "limits": {"max_rules": settings.max_alert_rules, "min_interval_minutes": MIN_INTERVAL_MINUTES,
                                   "max_runs_per_day": settings.max_alert_runs_per_day}})

    @app.post("/api/alerts")
    def create_alert():
        wallet = wallet_required(services)
        body = json_object()
        if repo().count_rules(wallet.id) >= settings.max_alert_rules:
            raise ApiError(f"You can have at most {settings.max_alert_rules} alerts", 409)
        rule = repo().create_rule(
            wallet.id, _text(body, "name", 80), _text(body, "query_text", 1000),
            _text(body, "condition_text", 300, required=False), _interval(body.get("interval_minutes", 1440)))
        return jsonify({"success": True, "alert": rule}), 201

    @app.patch("/api/alerts/<rule_id>")
    def update_alert(rule_id: str):
        wallet = wallet_required(services)
        body = json_object()
        fields: dict = {}
        if "name" in body:
            fields["name"] = _text(body, "name", 80)
        if "query_text" in body:
            fields["query_text"] = _text(body, "query_text", 1000)
        if "condition_text" in body:
            fields["condition_text"] = _text(body, "condition_text", 300, required=False) or None
        if "interval_minutes" in body:
            fields["interval_minutes"] = _interval(body["interval_minutes"])
        if "enabled" in body:
            if not isinstance(body["enabled"], bool):
                raise ApiError("'enabled' must be true or false")
            fields["enabled"] = body["enabled"]
        if not fields:
            raise ApiError("Nothing to update")
        rule = repo().update_rule(wallet.id, rule_id, **fields)
        if rule is None:
            raise ApiError("Alert not found", 404)
        return jsonify({"success": True, "alert": rule})

    @app.delete("/api/alerts/<rule_id>")
    def delete_alert(rule_id: str):
        wallet = wallet_required(services)
        if not repo().delete_rule(wallet.id, rule_id):
            raise ApiError("Alert not found", 404)
        return jsonify({"success": True})

    # ------------------------------------------------------------------ inbox
    @app.get("/api/inbox")
    def list_inbox():
        wallet = wallet_required(services)
        unread_only = request.args.get("unread") in ("1", "true")
        limit = min(max(request.args.get("limit", 50, type=int), 1), 100)
        return jsonify({"success": True, "items": repo().list_inbox(wallet.id, unread_only, limit),
                        "unread": repo().unread_count(wallet.id)})

    @app.get("/api/inbox/unread-count")
    def unread_count():
        wallet = wallet_required(services)
        return jsonify({"success": True, "unread": repo().unread_count(wallet.id)})

    @app.post("/api/inbox/read")
    def mark_read():
        wallet = wallet_required(services)
        body = request.get_json(silent=True) or {}
        inbox_id = body.get("id") if isinstance(body, dict) else None
        return jsonify({"success": True, "updated": repo().mark_read(wallet.id, inbox_id)})

    @app.delete("/api/inbox/<inbox_id>")
    def delete_inbox_item(inbox_id: str):
        wallet = wallet_required(services)
        if not repo().delete_inbox(wallet.id, inbox_id):
            raise ApiError("Not found", 404)
        return jsonify({"success": True})

    # ------------------------------------------------------------------ scheduler hook
    @app.post("/api/internal/alerts/run")
    def run_alerts():
        if not settings.cron_secret:
            raise ApiError("Not found", 404)   # disabled: look like any unknown route
        supplied = request.headers.get("X-Cron-Secret", "")
        if not hmac.compare_digest(supplied.encode(), settings.cron_secret.encode()):
            raise ApiError("Forbidden", 403)
        repo()
        if not _run_lock.acquire(blocking=False):
            return jsonify({"success": True, "status": "already_running"}), 202

        def work() -> None:
            try:
                from ..alerts.runner import run_due

                logger.info("Alert run finished: %s", run_due(services))
            except Exception:  # noqa: BLE001
                logger.exception("Alert run crashed")
            finally:
                _run_lock.release()

        threading.Thread(target=work, daemon=True, name="airaa-alerts").start()
        return jsonify({"success": True, "status": "started"}), 202
