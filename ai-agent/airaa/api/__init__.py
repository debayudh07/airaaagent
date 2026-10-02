"""Flask application factory."""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from flask import Flask, jsonify
from flask_cors import CORS

from ..config import Settings, get_settings
from .ratelimit import RateLimiter
from .routes import register_routes

logger = logging.getLogger(__name__)


def create_app(settings: Optional[Settings] = None, agent_factory: Optional[Callable[[Optional[str]], Any]] = None) -> Flask:
    """Build the app.

    ``agent_factory(session_id)`` returns an object with ``async research(request, on_event=None)``
    and a ``session_id`` attribute. It defaults to the real agent and exists so tests can inject a stub.
    """
    settings = settings or get_settings()
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024  # research requests are tiny

    origins = "*" if settings.allowed_origins.strip() == "*" else [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
    CORS(
        app,
        resources={r"/api/*": {"origins": origins}},
        methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Admin-Token"],
        supports_credentials=False,
        max_age=3600,
    )

    if agent_factory is None:
        from ..agent import Web3ResearchAgent

        agent_factory = lambda session_id: Web3ResearchAgent(session_id=session_id)  # noqa: E731

    register_routes(app, settings, agent_factory, RateLimiter(settings.rate_limit_per_minute))

    @app.errorhandler(404)
    def _not_found(_):
        return jsonify({"success": False, "error": "Not found"}), 404

    @app.errorhandler(405)
    def _method_not_allowed(_):
        return jsonify({"success": False, "error": "Method not allowed"}), 405

    @app.errorhandler(413)
    def _too_large(_):
        return jsonify({"success": False, "error": "Request body too large"}), 413

    @app.errorhandler(Exception)
    def _unhandled(exc):
        logger.exception("Unhandled error")
        return jsonify({"success": False, "error": "Internal server error"}), 500

    return app


__all__ = ["create_app"]
