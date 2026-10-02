"""HTTP routes."""
from __future__ import annotations

import asyncio
import hmac
import json
import queue
import threading
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional

from flask import Flask, Response, jsonify, request, stream_with_context

from ..config import Settings
from ..memory import get_session_manager
from ..tools import TOOL_CATALOG
from .ratelimit import RateLimiter
from .validation import SESSION_ID, parse_research_payload


def _client_key() -> str:
    """Caller identity for rate limiting. Behind Render's proxy the first X-Forwarded-For hop is the client."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    return forwarded.split(",")[0].strip() or request.remote_addr or "unknown"


def _error(message: str, status: int, **extra: Any):
    return jsonify({"success": False, "error": message, **extra}), status


def register_routes(app: Flask, settings: Settings, agent_factory: Callable[[Optional[str]], Any], limiter: RateLimiter) -> None:
    sessions = get_session_manager

    def _guard():
        """Parse + rate-limit a research request. Returns ``(ResearchRequest, None)`` or ``(None, response)``."""
        allowed, retry_after = limiter.check(_client_key())
        if not allowed:
            response, status = _error("Too many requests; slow down", 429, retry_after=retry_after)
            response.headers["Retry-After"] = str(retry_after)
            return None, (response, status)
        req, err = parse_research_payload(request.get_json(silent=True), settings)
        if err:
            return None, _error(err, 400)
        return req, None

    # ------------------------------------------------------------------ meta
    @app.get("/api/health")
    def health():
        return jsonify({
            "status": "ok",
            "models": {"planner": settings.planner_model, "synthesis": settings.synthesis_model},
            "sources": settings.configured_sources(),
        })

    @app.get("/api/tools")
    def tools():
        return jsonify({"success": True, "tools": [{"name": n, "description": d} for n, d in TOOL_CATALOG.items()]})

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
        session = sessions().get(session_id)
        if session is None:
            return _error("Session not found", 404)

        base = session["created_at"]
        messages = []
        for i, msg in enumerate(session["chat_history"].messages):
            extra = getattr(msg, "additional_kwargs", {}) or {}
            is_ai = msg.type == "ai"
            item = {
                "type": "ai" if is_ai else "human",
                "content": msg.content,
                "timestamp": extra.get("timestamp") or (base + timedelta(minutes=i)).isoformat(),
            }
            if is_ai and extra.get("research_data"):
                item["research_data"] = extra["research_data"]
            messages.append(item)

        return jsonify({
            "success": True,
            "session_id": session_id,
            "messages": messages,
            "message_count": len(messages),
            "created_at": session["created_at"].isoformat(),
            "last_activity": session["last_activity"].isoformat(),
        })

    @app.delete("/api/conversation/<session_id>")
    def delete_conversation(session_id: str):
        if not SESSION_ID.match(session_id):
            return _error("Invalid session id", 400)
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
