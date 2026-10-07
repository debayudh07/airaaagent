"""Test helpers: SIWE messages signed by a real key, an in-memory auth repo, and a deterministic fake embedder."""
from __future__ import annotations

import hashlib
import math
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from eth_account import Account
from eth_account.messages import encode_defunct

DOMAIN = "localhost:3000"


def siwe_message(address: str, nonce: str, domain: str = DOMAIN, chain_id: int = 11155111,
                 issued_at: Optional[datetime] = None, statement: Optional[str] = "Sign in to AIRAA.",
                 expiration: Optional[datetime] = None, compact: bool = False) -> str:
    issued = (issued_at or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    lines = [f"{domain} wants you to sign in with your Ethereum account:", address, ""]
    # EIP-4361: with a statement it is "<statement>" + blank; without one there is a second blank line before URI.
    lines += [statement, ""] if statement else [""]
    if compact and not statement:
        lines = lines[:-1]   # the lenient single-blank-line variant
    lines += [f"URI: http://{domain}", "Version: 1", f"Chain ID: {chain_id}", f"Nonce: {nonce}", f"Issued At: {issued}"]
    if expiration:
        lines.append("Expiration Time: " + expiration.strftime("%Y-%m-%dT%H:%M:%S.000Z"))
    return "\n".join(lines)


def sign(account, message: str) -> str:
    return "0x" + account.sign_message(encode_defunct(text=message)).signature.hex().removeprefix("0x")


def new_account():
    return Account.create()


class FakeAuthRepo:
    """The AuthRepo contract, in memory."""

    def __init__(self) -> None:
        self.nonces: Dict[str, bool] = {}
        self.wallets: Dict[str, Dict[str, Any]] = {}
        self.sessions: Dict[str, Dict[str, Any]] = {}

    def create_nonce(self, nonce: str, ttl_seconds: int = 300) -> None:
        self.nonces[nonce] = False

    def consume_nonce(self, nonce: str) -> bool:
        if self.nonces.get(nonce) is False:
            self.nonces[nonce] = True
            return True
        return False

    def upsert_wallet(self, address: str) -> Dict[str, Any]:
        address = address.lower()
        for w in self.wallets.values():
            if w["address"] == address:
                return w
        wallet = {"id": str(uuid.uuid4()), "address": address, "plan": "free", "settings": {"memory_enabled": True}}
        self.wallets[wallet["id"]] = wallet
        return wallet

    def get_wallet(self, wallet_id: str) -> Optional[Dict[str, Any]]:
        return self.wallets.get(wallet_id)

    def update_settings(self, wallet_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        self.wallets[wallet_id]["settings"].update(patch)
        return self.wallets[wallet_id]["settings"]

    def create_session(self, wallet_id, refresh_hash, ttl_days, user_agent="", ip_hash="", session_id=None):
        sid = session_id or str(uuid.uuid4())
        self.sessions[sid] = {"id": sid, "wallet_id": wallet_id, "family_id": str(uuid.uuid4()), "refresh_hash": refresh_hash,
                              "revoked_at": None, "expired": False, "expires_at": None}
        return self.sessions[sid]

    def get_session(self, session_id: str):
        return dict(self.sessions[session_id]) if session_id in self.sessions else None

    def rotate(self, session_id, old_hash, new_hash, ttl_days) -> bool:
        s = self.sessions.get(session_id)
        if not s or s["refresh_hash"] != old_hash or s["revoked_at"] or s["expired"]:
            return False
        s["refresh_hash"] = new_hash
        return True

    def revoke_session(self, session_id: str) -> None:
        self.sessions[session_id]["revoked_at"] = "now"

    def revoke_family(self, family_id: str) -> None:
        for s in self.sessions.values():
            if s["family_id"] == family_id:
                s["revoked_at"] = "now"


class FakeEmbedder:
    """Deterministic bag-of-words embedding: texts sharing words are similar, unrelated texts are near-orthogonal."""

    def __init__(self, dim: int = 768) -> None:
        self.dim = dim
        self.calls: List[tuple] = []

    def _vec(self, text: str) -> List[float]:
        v = [0.0] * self.dim
        for word in text.lower().split():
            h = int(hashlib.md5(word.strip(".,?!:;|()").encode()).hexdigest(), 16)
            v[h % self.dim] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed_sync(self, texts, task: str = "document"):
        self.calls.append((list(texts), task))
        return [self._vec(t) for t in texts]

    def embed_one_sync(self, text: str, task: str = "query"):
        return self.embed_sync([text], task)[0]

    async def aembed(self, texts, task: str = "document"):
        return self.embed_sync(texts, task)

    async def aembed_one(self, text: str, task: str = "query"):
        return self.embed_sync([text], task)[0]


def random_nonce() -> str:
    return secrets.token_hex(8)
