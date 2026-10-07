"""HTTP routes: health, research (plain and streaming) and conversations.

Identity: a request with a valid ``Authorization: Bearer`` token is a signed-in wallet; without one it is a guest and
works exactly as before. Conversations created by a wallet are private to it (other callers get 404); guest
conversations stay open to anyone holding the id, and a wallet can claim one it already holds.
"""
from __future__ import annotations

import asyncio
import hmac
import json
import queue
import threading
from typing import Any, Callable, Dict, Optional

from flask import Flask, Response, jsonify, request, stream_with_context

from ..auth import Wallet
from ..config import Settings
from ..memory import get_session_manager
from ..schemas import ResearchRequest
from ..tools import TOOL_CATALOG
from .deps import ApiError, client_ip, wallet_or_none
from .ratelimit import RateLimiter
from .serialize import conversation_json
from .validation import SESSION_ID, parse_research_payload


def current_sessions():
    """The session manager, looked up at call time (tests patch ``get_session_manager`` on this module)."""
    return get_session_manager()


def _client_key() -> str:
    """Caller identity for rate limiting. Behind Render's proxy the first X-Forwarded-For hop is the client."""
    return client_ip()


def _error(message: str, status: int, **extra: Any):
    return jsonify({"success": False, "error": message, **extra}), status


def _can_access(session: Dict[str, Any], wallet: Optional[Wallet]) -> bool:
    owner = session.get("wallet_id")
    return owner is None or (wallet is not None and owner == wallet.id)


def register_routes(app: Flask, settings: Settings, agent_factory: Callable[[Optional[str]], Any], limiter: RateLimiter,
                    services: Any) -> None:
    sessions = current_sessions

    def _memory_enabled(wallet: Wallet) -> bool:
        try:
            row = services.auth_repo.get_wallet(wallet.id) if services.auth_repo else None
            return bool(row["settings"].get("memory_enabled", True)) if row else True
        except Exception:  # noqa: BLE001 - a settings lookup must never block research
            return True

    def _bind_conversation(req: ResearchRequest, wallet: Optional[Wallet]) -> None:
        """Enforce ownership and attach the wallet to the request and its conversation."""
        existing = sessions().get(req.session_id)
        if existing is not None and not _can_access(existing, wallet):
            raise ApiError("Conversation not found", 404)
        if wallet is None:
            return
        if existing is None:
            sessions().get_or_create(req.session_id, wallet.id)       # new conversation, owned from the start
        elif existing.get("wallet_id") is None:
            sessions().claim(req.session_id, wallet.id)                # a guest conversation the wallet already holds
        req.wallet_id, req.wallet_address = wallet.id, wallet.address
        req.memory_enabled = _memory_enabled(wallet)

    def _guard():
        """Parse, authenticate and rate-limit a research request. Returns ``(ResearchRequest, None)`` or ``(None, response)``."""
        wallet = wallet_or_none(services)
        allowed, retry_after = limiter.check(wallet.id if wallet else _client_key())
        if not allowed:
            response, status = _error("Too many requests; slow down", 429, retry_after=retry_after)
            response.headers["Retry-After"] = str(retry_after)
            return None, (response, status)
        req, err = parse_research_payload(request.get_json(silent=True), settings)
        if err:
            return None, _error(err, 400)
        _bind_conversation(req, wallet)
        return req, None

    # ------------------------------------------------------------------ meta
    @app.get("/api/health")
    def health():
        return jsonify({
            "status": "ok",
            "models": {"planner": settings.planner_model, "synthesis": settings.synthesis_model},
            "sources": settings.configured_sources(),
            "features": services.features(),
        })

    @app.get("/api/tools")
    def tools():
        return jsonify({"success": True, "tools": [{"name": n, "description": d} for n, d in TOOL_CATALOG.items()]})

    @app.get("/api/feed")
    def feed():
        """Live snapshot for the home board (cached server-side; see airaa.feed)."""
        from ..feed import get_feed

        snapshot = get_feed()
        response = jsonify({"success": bool(snapshot["sections"]), **snapshot})
        response.headers["Cache-Control"] = "public, max-age=60"
        return response

    # ------------------------------------------------------------------ research
    @app.post("/api/research")
    def research():
        req, failure = _guard()
        if failure:
            return failure
        agent = agent_factory(req.session_id)
        result = asyncio.run(agent.research(req))
        result.setdefault("session_id", agent.session_id)
        return jsonify(result), (200 if result.get("success") else 502)

    @app.post("/api/research/stream")
    def research_stream():
        """Server-Sent Events: plan, tool progress, answer tokens, then the final result."""
        req, failure = _guard()
        if failure:
            return failure

        events: "queue.Queue[Optional[Dict[str, Any]]]" = queue.Queue()
        cancelled = threading.Event()

        async def on_event(event: Dict[str, Any]) -> None:
            if cancelled.is_set():  # client went away: stop spending tokens on an answer nobody reads
                raise asyncio.CancelledError()
            events.put(event)

        def worker() -> None:
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                agent = agent_factory(req.session_id)
                result = loop.run_until_complete(agent.research(req, on_event=on_event))
                result.setdefault("session_id", agent.session_id)
                events.put({"type": "result", "result": result})
            except asyncio.CancelledError:
                pass
            except Exception as exc:  # noqa: BLE001
                app.logger.exception("Streaming research failed")
                events.put({"type": "error", "error": str(exc)})
            finally:
                loop.close()
                asyncio.set_event_loop(None)
                events.put(None)

        threading.Thread(target=worker, daemon=True).start()

        def sse():
            try:
                while True:
                    try:
                        event = events.get(timeout=15)
                    except queue.Empty:
                        yield ": keep-alive\n\n"  # stops proxies from closing an idle stream
                        continue
                    if event is None:
                        break
                    yield f"data: {json.dumps(event, default=str)}\n\n"
            finally:
                cancelled.set()

        return Response(
            stream_with_context(sse()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ------------------------------------------------------------------ conversations
    @app.get("/api/conversation/<session_id>")
    def get_conversation(session_id: str):
        if not SESSION_ID.match(session_id):
            return _error("Invalid session id", 400)
        wallet = wallet_or_none(services)
        session = sessions().get(session_id)
        if session is None or not _can_access(session, wallet):
            return _error("Session not found", 404)   # same answer for "missing" and "not yours"
        return jsonify(conversation_json(session, session_id))

    @app.delete("/api/conversation/<session_id>")
    def delete_conversation(session_id: str):
        if not SESSION_ID.match(session_id):
            return _error("Invalid session id", 400)
        wallet = wallet_or_none(services)
        session = sessions().get(session_id)
        if session is not None and not _can_access(session, wallet):
            return _error("Session not found", 404)
        return jsonify({"success": True, "deleted": sessions().delete(session_id)})

    @app.get("/api/sessions")
    def list_sessions():
        """Operator-only listing. Disabled (404) unless ADMIN_TOKEN is set, so one visitor cannot enumerate others' sessions."""
        if not settings.admin_token:
            return _error("Not found", 404)
        supplied = request.headers.get("X-Admin-Token", "")
        if not hmac.compare_digest(supplied.encode(), settings.admin_token.encode()):
            return _error("Forbidden", 403)
        rows = [
            {
                "session_id": sid,
                "message_count": s["message_count"],
                "created_at": s["created_at"].isoformat(),
                "last_activity": s["last_activity"].isoformat(),
            }
            for sid, s in sessions().sessions.items()
        ]
        return jsonify({"success": True, "sessions": rows, "total_sessions": len(rows)})
