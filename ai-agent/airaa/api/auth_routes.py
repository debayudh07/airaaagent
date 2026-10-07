"""Wallet sign-in endpoints (SIWE).

    GET  /api/auth/nonce     -> {nonce}
    POST /api/auth/verify    {message, signature} -> {access_token, expires_in, wallet}  + httpOnly refresh cookie
    POST /api/auth/refresh   (cookie)             -> new access token, rotated cookie
    POST /api/auth/logout    (cookie)             -> revokes the session
    GET  /api/auth/me        (Bearer)             -> {wallet}

The access token lives in memory in the browser; the refresh token is an httpOnly cookie scoped to /api/auth.
Cookie endpoints also check the Origin header against ALLOWED_ORIGINS, so another site cannot trigger them.
"""
from __future__ import annotations

from urllib.parse import urlparse

from flask import Flask, Response, jsonify, request

from ..auth import AuthError
from ..config import Settings
from .deps import ApiError, client_ip, json_object, limit_or_429, need, wallet_required

COOKIE_NAME = "airaa_refresh"
COOKIE_PATH = "/api/auth"


def _is_https() -> bool:
    return request.is_secure or request.headers.get("X-Forwarded-Proto", "").split(",")[0].strip() == "https"


def _set_refresh_cookie(response: Response, token: str, max_age: int) -> None:
    secure = _is_https()
    # Cross-site (frontend and API on different domains) needs SameSite=None, which browsers only allow with Secure.
    response.set_cookie(COOKIE_NAME, token, max_age=max_age, httponly=True, secure=secure,
                        samesite="None" if secure else "Lax", path=COOKIE_PATH)


def _clear_refresh_cookie(response: Response) -> None:
    secure = _is_https()
    response.set_cookie(COOKIE_NAME, "", max_age=0, httponly=True, secure=secure,
                        samesite="None" if secure else "Lax", path=COOKIE_PATH)


def _check_origin(settings: Settings) -> None:
    """CSRF guard for the cookie endpoints: when origins are configured, the caller's Origin must be one of them."""
    allowed = [o.strip().rstrip("/") for o in settings.allowed_origins.split(",") if o.strip()]
    if not allowed or allowed == ["*"]:
        return
    origin = request.headers.get("Origin", "").rstrip("/")
    if origin not in allowed and urlparse(origin).netloc not in {urlparse(a).netloc for a in allowed}:
        raise ApiError("Origin not allowed", 403)


def _login_payload(result) -> dict:
    return {"success": True, "access_token": result.access_token, "expires_in": result.expires_in,
            "wallet": {"id": result.wallet["id"], "address": result.wallet["address"],
                       "settings": result.wallet.get("settings", {})}}


def register_auth_routes(app: Flask, settings: Settings, services, limiter) -> None:
    @app.get("/api/auth/nonce")
    def auth_nonce():
        auth = need(services.auth, "Wallet sign-in")
        limit_or_429(limiter, f"auth:{client_ip()}")
        return jsonify({"success": True, "nonce": auth.issue_nonce()})

    @app.post("/api/auth/verify")
    def auth_verify():
        auth = need(services.auth, "Wallet sign-in")
        _check_origin(settings)
        limit_or_429(limiter, f"auth:{client_ip()}")
        body = json_object()
        message, signature = body.get("message"), body.get("signature")
        if not isinstance(message, str) or not isinstance(signature, str):
            raise ApiError("'message' and 'signature' are required", 400)
        result = auth.login(message, signature, request.headers.get("User-Agent", ""), client_ip())
        response = jsonify(_login_payload(result))
        _set_refresh_cookie(response, result.refresh_token, result.refresh_max_age)
        return response

    @app.post("/api/auth/refresh")
    def auth_refresh():
        auth = need(services.auth, "Wallet sign-in")
        _check_origin(settings)
        limit_or_429(limiter, f"auth:{client_ip()}")
        token = request.cookies.get(COOKIE_NAME)
        if not token:
            raise ApiError("Not signed in", 401, code="no_session")
        try:
            result = auth.refresh(token)
        except AuthError as exc:
            response = jsonify({"success": False, "error": exc.message, "code": "session_invalid"})
            response.status_code = exc.status
            _clear_refresh_cookie(response)
            return response
        response = jsonify(_login_payload(result))
        _set_refresh_cookie(response, result.refresh_token, result.refresh_max_age)
        return response

    @app.post("/api/auth/logout")
    def auth_logout():
        auth = need(services.auth, "Wallet sign-in")
        _check_origin(settings)
        auth.logout(request.cookies.get(COOKIE_NAME))
        response = jsonify({"success": True})
        _clear_refresh_cookie(response)
        return response

    @app.get("/api/auth/me")
    def auth_me():
        wallet = wallet_required(services)
        return jsonify({"success": True, "wallet": {"id": wallet.id, "address": wallet.address}})
