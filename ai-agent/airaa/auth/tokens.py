"""Access tokens (short-lived HS256 JWTs) and refresh tokens (opaque, rotated, stored hashed)."""
from __future__ import annotations

import hashlib
import secrets
import time
from typing import Any, Dict, Optional, Tuple

import jwt

from ..config import Settings

ISSUER = "airaa"
AUDIENCE = "authenticated"   # what Supabase expects, so the same token works for RLS


class TokenError(Exception):
    """The token is missing, malformed, expired or not ours."""


def issue_access_token(settings: Settings, wallet_id: str, address: str, chain_id: int, session_id: str,
                       now: Optional[float] = None) -> Tuple[str, int]:
    """Returns ``(token, expires_in_seconds)``."""
    issued = int(now if now is not None else time.time())
    ttl = settings.access_token_ttl_seconds
    claims = {
        "iss": ISSUER, "aud": AUDIENCE, "sub": wallet_id, "role": "authenticated",
        "wallet": address.lower(), "chain": chain_id, "sid": session_id,
        "iat": issued, "exp": issued + ttl,
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm="HS256"), ttl


def decode_access_token(settings: Settings, token: str) -> Dict[str, Any]:
    try:
        return jwt.decode(
            token, settings.jwt_secret, algorithms=["HS256"], audience=AUDIENCE, issuer=ISSUER,
            options={"require": ["exp", "iat", "sub", "wallet"]},
        )
    except jwt.ExpiredSignatureError:
        raise TokenError("Access token expired") from None
    except jwt.PyJWTError:
        raise TokenError("Invalid access token") from None


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def new_refresh_token(session_id: str) -> Tuple[str, str]:
    """Returns ``(token, sha256_of_secret)``. The token embeds the session id so lookup needs no index on the hash."""
    secret = secrets.token_urlsafe(32)
    return f"{session_id}.{secret}", hash_secret(secret)


def split_refresh_token(token: str) -> Optional[Tuple[str, str]]:
    session_id, sep, secret = (token or "").partition(".")
    return (session_id, secret) if sep and session_id and secret else None
