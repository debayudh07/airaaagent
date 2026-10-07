"""Wallet sign-in orchestration: nonce -> SIWE verify -> session -> access/refresh tokens."""
from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlparse

from ..config import Settings
from . import siwe
from .tokens import (TokenError, decode_access_token, hash_secret, issue_access_token, new_refresh_token,
                     split_refresh_token)

logger = logging.getLogger(__name__)


class AuthError(Exception):
    """Authentication failed. ``message`` is safe to return to the client."""

    def __init__(self, message: str, status: int = 401) -> None:
        super().__init__(message)
        self.message, self.status = message, status


@dataclass
class Wallet:
    id: str
    address: str
    chain_id: int = 0
    session_id: str = ""


@dataclass
class LoginResult:
    wallet: Dict[str, Any]
    access_token: str
    expires_in: int
    refresh_token: str
    refresh_max_age: int


def allowed_domains(settings: Settings) -> tuple:
    """Hosts a SIWE message may name: explicit setting, else the hosts of ALLOWED_ORIGINS, else local dev."""
    if settings.siwe_domains:
        return settings.siwe_domains
    origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip() and o.strip() != "*"]
    hosts = tuple(urlparse(o).netloc for o in origins if urlparse(o).netloc)
    return hosts or ("localhost:3000", "localhost", "127.0.0.1:3000")


class AuthService:
    def __init__(self, repo: Any, settings: Settings, verifier: Callable[..., str] = siwe.verify_signature) -> None:
        self.repo = repo
        self.settings = settings
        self._verify = verifier

    # ---- sign in -------------------------------------------------------
    def issue_nonce(self) -> str:
        nonce = secrets.token_hex(16)
        self.repo.create_nonce(nonce, ttl_seconds=300)
        return nonce

    def login(self, message_text: str, signature: str, user_agent: str = "", ip: str = "") -> LoginResult:
        try:
            message = siwe.parse_message(message_text)
            siwe.validate_message(message, allowed_domains(self.settings))
            if not self.repo.consume_nonce(message.nonce):
                raise siwe.SiweError("Sign-in link expired or was already used; try again")
            self._verify(message_text, signature, message.address, message.chain_id, self.settings.rpc_urls_json)
        except siwe.SiweError as exc:
            raise AuthError(str(exc), 401) from None
        wallet = self.repo.upsert_wallet(message.address)
        return self._start_session(wallet, message.chain_id, user_agent, ip)

    def _start_session(self, wallet: Dict[str, Any], chain_id: int, user_agent: str, ip: str) -> LoginResult:
        session_id = str(uuid.uuid4())
        refresh, refresh_hash = new_refresh_token(session_id)
        self.repo.create_session(
            wallet["id"], refresh_hash, self.settings.refresh_token_ttl_days, user_agent,
            hashlib.sha256(ip.encode()).hexdigest()[:32] if ip else "", session_id=session_id,
        )
        return self._result(wallet, chain_id, session_id, refresh)

    def _result(self, wallet: Dict[str, Any], chain_id: int, session_id: str, refresh: str) -> LoginResult:
        access, ttl = issue_access_token(self.settings, wallet["id"], wallet["address"], chain_id, session_id)
        return LoginResult(wallet=wallet, access_token=access, expires_in=ttl, refresh_token=refresh,
                           refresh_max_age=self.settings.refresh_token_ttl_days * 86400)

    # ---- refresh / logout ---------------------------------------------
    def refresh(self, refresh_token: str, chain_id: int = 0) -> LoginResult:
        """Rotate the refresh token. A replayed (already rotated) token revokes the whole session family."""
        parts = split_refresh_token(refresh_token)
        session = self.repo.get_session(parts[0]) if parts else None
        if not parts or session is None:
            raise AuthError("Invalid refresh token")
        if session["revoked_at"] or session["expired"]:
            raise AuthError("Session expired; sign in again")
        presented = hash_secret(parts[1])
        if not secrets.compare_digest(presented, session["refresh_hash"]):
            logger.warning("Refresh token reuse detected for session %s; revoking its family", session["id"])
            self.repo.revoke_family(session["family_id"])
            raise AuthError("Session was reused and has been revoked; sign in again")

        new_token, new_hash = new_refresh_token(session["id"])
        if not self.repo.rotate(session["id"], presented, new_hash, self.settings.refresh_token_ttl_days):
            raise AuthError("Session expired; sign in again")  # lost a rotation race or expired in between
        wallet = self.repo.get_wallet(session["wallet_id"])
        if wallet is None:
            raise AuthError("Account no longer exists")
        return self._result(wallet, chain_id, session["id"], new_token)

    def logout(self, refresh_token: Optional[str]) -> None:
        parts = split_refresh_token(refresh_token or "")
        session = self.repo.get_session(parts[0]) if parts else None
        if session and secrets.compare_digest(hash_secret(parts[1]), session["refresh_hash"]):
            self.repo.revoke_session(session["id"])

    # ---- per request ---------------------------------------------------
    def authenticate(self, access_token: str) -> Wallet:
        try:
            claims = decode_access_token(self.settings, access_token)
        except TokenError as exc:
            raise AuthError(str(exc)) from None
        return Wallet(id=claims["sub"], address=claims["wallet"], chain_id=int(claims.get("chain") or 0),
                      session_id=str(claims.get("sid") or ""))
