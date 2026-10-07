"""Helpers shared by the route modules: errors, JSON body, and the signed-in wallet."""
from __future__ import annotations

from typing import Any, Dict, Optional

from flask import request

from ..auth import AuthError, Wallet


class ApiError(Exception):
    """Raised anywhere in a handler; turned into a JSON error response by the app's error handler."""

    def __init__(self, message: str, status: int = 400, **extra: Any) -> None:
        super().__init__(message)
        self.message, self.status, self.extra = message, status, extra


def json_object() -> Dict[str, Any]:
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ApiError("Request body must be a JSON object", 400)
    return body


def bearer_token() -> Optional[str]:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


def wallet_or_none(services: Any) -> Optional[Wallet]:
    """The signed-in wallet, ``None`` for a guest. A token that is present but bad is a 401, never a silent guest,
    so the client knows to refresh instead of quietly losing its identity."""
    token = bearer_token()
    if token is None:
        return None
    if services.auth is None:
        raise ApiError("Wallet sign-in is not enabled on this server", 503)
    try:
        return services.auth.authenticate(token)
    except AuthError as exc:
        raise ApiError(exc.message, 401, code="token_invalid") from None


def wallet_required(services: Any) -> Wallet:
    wallet = wallet_or_none(services)
    if wallet is None:
        raise ApiError("Sign in with your wallet to use this", 401, code="auth_required")
    return wallet


def need(component: Any, name: str) -> Any:
    """Return ``component`` or 503 if that feature is not configured on this server."""
    if component is None:
        raise ApiError(f"{name} is not enabled on this server", 503)
    return component


def client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    return forwarded.split(",")[0].strip() or request.remote_addr or "unknown"


def limit_or_429(limiter: Any, key: str) -> None:
    allowed, retry_after = limiter.check(key)
    if not allowed:
        raise ApiError("Too many requests; slow down", 429, retry_after=retry_after)
