"""Sealed storage rules. The server validates shapes and ownership; it cannot read what it stores."""
from __future__ import annotations

import base64
import binascii
import hashlib
import logging
import secrets
import uuid
from typing import Any, Dict, List, Optional

from ..config import Settings, get_settings
from ..db.util import as_uuid

logger = logging.getLogger(__name__)

WRAPPER_TYPES = ("signature", "passphrase", "recovery")
MAX_META_BYTES = 8 * 1024
MAX_WRAPPED_KEY_BYTES = 512
MAX_SUMMARY_CHARS = 600


class VaultError(ValueError):
    """Bad input or a rule violation. ``status`` is the suggested HTTP status; the message is safe to show."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def b64decode(value: Any, field: str, max_bytes: int) -> bytes:
    if not isinstance(value, str) or not value:
        raise VaultError(f"'{field}' must be a base64 string")
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise VaultError(f"'{field}' is not valid base64") from None
    if not raw or len(raw) > max_bytes:
        raise VaultError(f"'{field}' must be between 1 and {max_bytes} bytes")
    return raw


def b64encode(value: Optional[bytes]) -> Optional[str]:
    return base64.b64encode(value).decode() if value is not None else None


def public_key_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {"id": row["id"], "wrapper_type": row["wrapper_type"], "wrapped_dek": b64encode(row["wrapped_dek"]),
            "kdf": row["kdf"], "created_at": row["created_at"]}


def public_artifact_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {"id": row["id"], "size_bytes": row["size_bytes"], "enc_alg": row["enc_alg"],
            "wrapped_cek": b64encode(row["wrapped_cek"]), "meta_enc": b64encode(row.get("meta_enc")),
            "index_summary": row.get("index_summary"), "created_at": row["created_at"]}


class VaultService:
    def __init__(self, repo: Any, blobs: Any, embedder: Any = None, settings: Optional[Settings] = None) -> None:
        self.repo, self.blobs, self.embedder = repo, blobs, embedder
        self.settings = settings or get_settings()

    # ---- keys ----------------------------------------------------------
    def put_key(self, wallet_id: str, wrapper_type: str, body: Dict[str, Any]) -> Dict[str, Any]:
        if wrapper_type not in WRAPPER_TYPES:
            raise VaultError("wrapper_type must be one of: " + ", ".join(WRAPPER_TYPES), 404)
        wrapped = b64decode(body.get("wrapped_dek"), "wrapped_dek", MAX_WRAPPED_KEY_BYTES)
        kdf = body.get("kdf") or {}
        if not isinstance(kdf, dict) or len(str(kdf)) > 2000:
            raise VaultError("'kdf' must be a small object")
        row = self.repo.put_key(wallet_id, wrapper_type, wrapped, kdf)
        return {"id": row["id"], "wrapper_type": row["wrapper_type"], "created_at": row["created_at"]}

    def list_keys(self, wallet_id: str) -> List[Dict[str, Any]]:
        return [public_key_row(r) for r in self.repo.list_keys(wallet_id)]

    def delete_key(self, wallet_id: str, wrapper_type: str) -> None:
        keys = self.repo.list_keys(wallet_id)
        if wrapper_type not in {k["wrapper_type"] for k in keys}:
            raise VaultError("No such key", 404)
        if len(keys) == 1:
            raise VaultError("Cannot remove the only way to unlock the vault; add another first", 409)
        self.repo.delete_key(wallet_id, wrapper_type)

    # ---- artifacts -----------------------------------------------------
    def create_artifact(self, wallet_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
        if not self.repo.list_keys(wallet_id):
            raise VaultError("Set up your vault before storing sealed files", 409)
        artifact_id = as_uuid(body.get("id")) if body.get("id") else str(uuid.uuid4())
        if artifact_id is None:
            raise VaultError("'id' must be a UUID")
        ciphertext = b64decode(body.get("ciphertext"), "ciphertext", self.settings.max_artifact_bytes)
        if len(ciphertext) < 29:    # 12-byte nonce + 16-byte GCM tag + at least 1 byte
            raise VaultError("'ciphertext' is too short to be valid")
        wrapped_cek = b64decode(body.get("wrapped_cek"), "wrapped_cek", MAX_WRAPPED_KEY_BYTES)
        meta_enc = b64decode(body["meta_enc"], "meta_enc", MAX_META_BYTES) if body.get("meta_enc") else None

        summary = (body.get("index_summary") or "").strip() or None   # opt-in: the user chose to expose this text
        if summary and len(summary) > MAX_SUMMARY_CHARS:
            raise VaultError(f"'index_summary' must be at most {MAX_SUMMARY_CHARS} characters")
        vector = None
        if summary and self.embedder is not None:
            try:
                vector = self.embedder.embed_one_sync(summary, "document")
            except Exception:  # noqa: BLE001 - the file still saves; it just is not searchable
                logger.warning("Could not embed the artifact summary; saving without search")

        path = f"sealed/{wallet_id}/{artifact_id}"
        self.blobs.put(path, ciphertext)
        try:
            row = self.repo.create_artifact(wallet_id, artifact_id, path, len(ciphertext), wrapped_cek, meta_enc, summary, vector)
        except Exception:
            self.blobs.delete([path])    # do not leave an orphaned object behind
            raise
        return {"id": row["id"], "size_bytes": row["size_bytes"], "created_at": row["created_at"]}

    def list_artifacts(self, wallet_id: str) -> List[Dict[str, Any]]:
        return [public_artifact_row(r) for r in self.repo.list_artifacts(wallet_id)]

    def get_artifact(self, wallet_id: str, artifact_id: str) -> Dict[str, Any]:
        row = self.repo.get_artifact(artifact_id, wallet_id)
        if row is None:
            raise VaultError("Not found", 404)
        return row

    def read_blob(self, row: Dict[str, Any]) -> bytes:
        data = self.blobs.get(row["storage_path"])
        if data is None:
            raise VaultError("The stored file is missing", 404)
        return data

    def delete_artifact(self, wallet_id: str, artifact_id: str) -> None:
        path = self.repo.delete_artifact(wallet_id, artifact_id)
        if path is None:
            raise VaultError("Not found", 404)
        try:
            self.blobs.delete([path])
        except Exception:  # noqa: BLE001 - the row is gone; the object is unreachable either way
            logger.exception("Could not delete blob %s", path)

    def search(self, wallet_id: str, query: str, k: int = 10) -> List[Dict[str, Any]]:
        if self.embedder is None:
            raise VaultError("Search is unavailable", 503)
        vector = self.embedder.embed_one_sync(query, "query")
        return self.repo.search_artifacts(wallet_id, vector, k, 0.4)

    def purge_blobs(self, wallet_id: str) -> None:
        paths = self.repo.storage_paths(wallet_id)
        for start in range(0, len(paths), 100):
            self.blobs.delete(paths[start:start + 100])

    # ---- shares --------------------------------------------------------
    def create_link_share(self, owner_wallet_id: str, resource_type: str, resource_id: str,
                          wrapped_key: Optional[bytes], redact: bool, ttl_hours: Optional[int]) -> Dict[str, Any]:
        token = secrets.token_urlsafe(24)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        row = self.repo.create_share(owner_wallet_id, resource_type, resource_id, "link", None, token_hash,
                                     wrapped_key, redact, ttl_hours)
        return {**row, "token": token}   # the token is shown once; only its hash is stored
