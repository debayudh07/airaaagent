"""Flask application factory."""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from flask import Flask, Request, jsonify
from flask_cors import CORS

from ..auth import AuthError
from ..config import Settings, get_settings
from ..vault.service import VaultError
from .alert_routes import register_alert_routes
from .account_routes import register_account_routes
from .auth_routes import register_auth_routes
from .deps import ApiError
from .ratelimit import RateLimiter
from .routes import register_routes
from .vault_routes import register_vault_routes

logger = logging.getLogger(__name__)

DEFAULT_BODY_LIMIT = 64 * 1024  # research requests are tiny
# Local dev frontends may use the cookie-based sign-in endpoints even when ALLOWED_ORIGINS is the open default.
_LOCAL_ORIGINS = [r"^http://localhost:\d+$", r"^http://127\.0\.0\.1:\d+$"]


def _request_class(settings: Settings) -> type:
    """Same 64 KB body cap everywhere except sealed-file upload, which carries base64 ciphertext."""
    upload_limit = int(settings.max_artifact_bytes * 4 / 3) + DEFAULT_BODY_LIMIT

    class SizedRequest(Request):
        @property
        def max_content_length(self):  # type: ignore[override]
            if self.method == "POST" and self.path == "/api/artifacts":
                return upload_limit
            return DEFAULT_BODY_LIMIT

        @max_content_length.setter
        def max_content_length(self, value):  # Flask/Werkzeug may try to set it; the rule above decides
            pass

    return SizedRequest


def create_app(settings: Optional[Settings] = None, agent_factory: Optional[Callable[[Optional[str]], Any]] = None,
               services: Any = None) -> Flask:
    """Build the app.

    ``agent_factory(session_id)`` returns an object with ``async research(request, on_event=None)``
    and a ``session_id`` attribute. It defaults to the real agent and exists so tests can inject a stub.
    ``services`` (see :mod:`airaa.services`) holds the database-backed features; it defaults to the process-wide one,
    which is empty when no database is configured.
    """
    settings = settings or get_settings()
    if services is None:
        from ..services import get_services

        services = get_services(settings)

    app = Flask(__name__)
    app.request_class = _request_class(settings)
    app.config["MAX_CONTENT_LENGTH"] = DEFAULT_BODY_LIMIT

    open_origins = settings.allowed_origins.strip() == "*"
    origins = "*" if open_origins else [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
    if open_origins:
        # Bearer-token calls work from anywhere; only the cookie endpoints need credentials, so they are restricted.
        resources = {
            r"/api/auth/*": {"origins": _LOCAL_ORIGINS, "supports_credentials": True},
            r"/api/*": {"origins": "*", "supports_credentials": False},
        }
    else:
        resources = {r"/api/*": {"origins": origins, "supports_credentials": True}}
    CORS(
        app,
        resources=resources,
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Admin-Token"],
        max_age=3600,
    )

    if agent_factory is None:
        from ..agent import Web3ResearchAgent

        agent_factory = lambda session_id: Web3ResearchAgent(  # noqa: E731
            session_id=session_id, retrieval=services.retrieval, cache=services.cache)

    limiter = RateLimiter(settings.rate_limit_per_minute)
    register_routes(app, settings, agent_factory, limiter, services)
    register_auth_routes(app, settings, services, limiter)
    register_account_routes(app, settings, services, limiter)
    register_vault_routes(app, settings, services, limiter)
    register_alert_routes(app, settings, services, limiter)

    @app.errorhandler(ApiError)
    def _api_error(exc: ApiError):
        response = jsonify({"success": False, "error": exc.message, **exc.extra})
        response.status_code = exc.status
        if exc.status == 429 and "retry_after" in exc.extra:
            response.headers["Retry-After"] = str(exc.extra["retry_after"])
        return response

    @app.errorhandler(AuthError)
    def _auth_error(exc: AuthError):
        return jsonify({"success": False, "error": exc.message}), exc.status

    @app.errorhandler(VaultError)
    def _vault_error(exc: VaultError):
        return jsonify({"success": False, "error": str(exc)}), exc.status

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
