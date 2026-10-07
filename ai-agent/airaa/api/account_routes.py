"""Per-wallet account endpoints: conversations, memory dashboard, watchlist, portfolio, settings, export, purge.

All require a signed-in wallet. Memory edits re-embed the text, so they need the embedding service; listing and
deleting do not.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Callable

from flask import Flask, Response, jsonify, request

from ..config import Settings
from ..context_service import ContextError
from .routes import current_sessions
from .deps import ApiError, json_object, limit_or_429, need, wallet_required

MEMORY_KINDS = ("fact", "preference", "finding", "summary")


def _importance(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ApiError("'importance' must be a number between 0 and 1") from None
    if not 0 <= number <= 1:
        raise ApiError("'importance' must be a number between 0 and 1")
    return number


def _content(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ApiError("'content' must be a non-empty string")
    if len(value.strip()) > 2000:
        raise ApiError("'content' must be at most 2000 characters")
    return value.strip()


def register_account_routes(app: Flask, settings: Settings, services: Any, limiter: Any) -> None:
    sessions: Callable[[], Any] = current_sessions

    # ------------------------------------------------------------------ conversations
    @app.get("/api/conversations")
    def list_conversations():
        wallet = wallet_required(services)
        return jsonify({"success": True, "conversations": sessions().list_for_wallet(wallet.id)})

    @app.post("/api/conversations/claim")
    def claim_conversation():
        """After signing in, attach the guest conversation the browser was using to the wallet."""
        wallet = wallet_required(services)
        session_id = json_object().get("session_id")
        if not isinstance(session_id, str) or not session_id:
            raise ApiError("'session_id' is required")
        claimed = sessions().claim(session_id, wallet.id)
        if not claimed:
            raise ApiError("Conversation not found", 404)
        return jsonify({"success": True, "session_id": session_id})

    # ------------------------------------------------------------------ me
    @app.get("/api/me")
    def me():
        wallet = wallet_required(services)
        row = need(services.auth_repo, "Accounts").get_wallet(wallet.id)
        if row is None:
            raise ApiError("Account not found", 404)
        counts = {
            "memories": services.memory_repo.count(wallet.id) if services.memory_repo else 0,
            "watchlist": services.context_repo.count_watch(wallet.id) if services.context_repo else 0,
            "alerts": services.alerts_repo.count_rules(wallet.id) if services.alerts_repo else 0,
            "unread": services.alerts_repo.unread_count(wallet.id) if services.alerts_repo else 0,
        }
        return jsonify({"success": True, "wallet": {"id": row["id"], "address": row["address"], "plan": row["plan"],
                                                    "settings": row["settings"]}, "counts": counts})

    @app.patch("/api/me/settings")
    def update_settings():
        wallet = wallet_required(services)
        body = json_object()
        patch = {}
        if "memory_enabled" in body:
            if not isinstance(body["memory_enabled"], bool):
                raise ApiError("'memory_enabled' must be true or false")
            patch["memory_enabled"] = body["memory_enabled"]
        if not patch:
            raise ApiError("Nothing to update")
        return jsonify({"success": True, "settings": need(services.auth_repo, "Accounts").update_settings(wallet.id, patch)})

    @app.get("/api/me/export")
    def export_data():
        """Everything the server holds about the wallet, as one JSON download. Sealed files stay encrypted (metadata only)."""
        wallet = wallet_required(services)
        from ..vault.service import public_artifact_row

        data = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "wallet": wallet.address,
            "conversations": sessions().store.export_wallet(wallet.id) if sessions().store else [],
            "memories": services.memory_repo.list(wallet.id, limit=1000) if services.memory_repo else [],
            "watchlist": services.context_repo.list_watch(wallet.id) if services.context_repo else [],
            "portfolio_snapshots": services.context_repo.latest_snapshots(wallet.id, 10) if services.context_repo else [],
            "alert_rules": services.alerts_repo.list_rules(wallet.id) if services.alerts_repo else [],
            "inbox": services.alerts_repo.list_inbox(wallet.id, limit=200) if services.alerts_repo else [],
            "sealed_files": [public_artifact_row(r) for r in services.vault_repo.list_artifacts(wallet.id, 1000)] if services.vault_repo else [],
            "shares": services.vault_repo.list_shares(wallet.id) if services.vault_repo else [],
        }
        response = Response(json.dumps(data, default=str, indent=1), mimetype="application/json")
        response.headers["Content-Disposition"] = 'attachment; filename="airaa-export.json"'
        return response

    @app.delete("/api/me")
    def delete_account():
        """Erase the wallet and everything it owns. Requires {"confirm": "DELETE"} so a stray call cannot do it."""
        wallet = wallet_required(services)
        if json_object().get("confirm") != "DELETE":
            raise ApiError('Send {"confirm": "DELETE"} to erase your data')
        if services.vault is not None:
            services.vault.purge_blobs(wallet.id)
        need(services.auth_repo, "Accounts").delete_wallet(wallet.id)   # cascades to every wallet-owned table
        manager = sessions()
        with manager._lock:   # drop this wallet's conversations from the in-process cache too
            for sid in [sid for sid, s in manager.sessions.items() if s.get("wallet_id") == wallet.id]:
                del manager.sessions[sid]
        response = jsonify({"success": True})
        response.delete_cookie("airaa_refresh", path="/api/auth")
        return response

    # ------------------------------------------------------------------ memory dashboard
    @app.get("/api/memories")
    def list_memories():
        wallet = wallet_required(services)
        repo = need(services.memory_repo, "Memory")
        kind = request.args.get("kind")
        if kind and kind not in MEMORY_KINDS:
            raise ApiError("Unknown 'kind'")
        limit = min(max(request.args.get("limit", 100, type=int), 1), 200)
        offset = max(request.args.get("offset", 0, type=int), 0)
        return jsonify({"success": True, "memories": repo.list(wallet.id, kind, limit, offset), "total": repo.count(wallet.id)})

    @app.post("/api/memories")
    def add_memory():
        wallet = wallet_required(services)
        memories = need(services.memories, "Memory")
        body = json_object()
        kind = body.get("kind", "fact")
        if kind not in MEMORY_KINDS:
            raise ApiError("'kind' must be one of: " + ", ".join(MEMORY_KINDS))
        memory_id = asyncio.run(memories.add_manual(
            wallet.id, kind, _content(body.get("content")), _importance(body.get("importance", 0.7)), bool(body.get("pinned", False))))
        return jsonify({"success": True, "id": memory_id}), 201

    @app.patch("/api/memories/<memory_id>")
    def edit_memory(memory_id: str):
        wallet = wallet_required(services)
        memories = need(services.memories, "Memory")
        body = json_object()
        content = _content(body["content"]) if "content" in body else None
        importance = _importance(body["importance"]) if "importance" in body else None
        pinned = body.get("pinned")
        if pinned is not None and not isinstance(pinned, bool):
            raise ApiError("'pinned' must be true or false")
        if content is None and importance is None and pinned is None:
            raise ApiError("Nothing to update")
        row = asyncio.run(memories.edit(wallet.id, memory_id, content, importance, pinned))
        if row is None:
            raise ApiError("Memory not found", 404)
        return jsonify({"success": True, "memory": row})

    @app.delete("/api/memories/<memory_id>")
    def delete_memory(memory_id: str):
        wallet = wallet_required(services)
        if not need(services.memory_repo, "Memory").delete(wallet.id, memory_id):
            raise ApiError("Memory not found", 404)
        return jsonify({"success": True})

    @app.delete("/api/memories")
    def forget_everything():
        wallet = wallet_required(services)
        if json_object().get("confirm") is not True:
            raise ApiError('Send {"confirm": true} to forget everything')
        return jsonify({"success": True, "deleted": need(services.memory_repo, "Memory").delete_all(wallet.id)})

    # ------------------------------------------------------------------ watchlist
    @app.get("/api/watchlist")
    def get_watchlist():
        wallet = wallet_required(services)
        return jsonify({"success": True, "items": need(services.context, "Watchlist").list_watch(wallet.id)})

    @app.post("/api/watchlist")
    def add_watchlist():
        wallet = wallet_required(services)
        body = json_object()
        try:
            item = need(services.context, "Watchlist").add_watch(
                wallet.id, str(body.get("entity_type", "")), str(body.get("entity_id", "")), body.get("note"))
        except ContextError as exc:
            raise ApiError(str(exc)) from None
        return jsonify({"success": True, "item": item}), 201

    @app.delete("/api/watchlist/<watch_id>")
    def remove_watchlist(watch_id: str):
        wallet = wallet_required(services)
        if not need(services.context, "Watchlist").remove_watch(wallet.id, watch_id):
            raise ApiError("Not found", 404)
        return jsonify({"success": True})

    # ------------------------------------------------------------------ portfolio
    @app.get("/api/portfolio")
    def get_portfolio():
        wallet = wallet_required(services)
        return jsonify({"success": True, "address": wallet.address,
                        "snapshots": need(services.context, "Portfolio").snapshots(wallet.id)})

    @app.post("/api/portfolio/refresh")
    def refresh_portfolio():
        wallet = wallet_required(services)
        context = need(services.context, "Portfolio")
        limit_or_429(limiter, f"portfolio:{wallet.id}")
        chain = str(json_object().get("chain") or "ethereum") if request.data else "ethereum"
        try:
            snapshot = asyncio.run(context.refresh_portfolio(wallet.id, wallet.address, chain))
        except ContextError as exc:
            raise ApiError(str(exc), 422) from None
        return jsonify({"success": True, "snapshot": snapshot})
