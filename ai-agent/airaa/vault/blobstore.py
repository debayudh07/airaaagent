"""Where sealed ciphertext bytes live. Both backends only ever see encrypted data.

* :class:`SupabaseBlobStore` - Supabase Storage (private bucket), used when SUPABASE_URL and
  SUPABASE_SERVICE_ROLE_KEY are set.
* :class:`DbBlobStore` - a Postgres table; the zero-setup fallback (fine for small artifacts).
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Optional
from urllib.parse import quote

import httpx

from ..config import Settings

logger = logging.getLogger(__name__)


class BlobError(RuntimeError):
    pass


class DbBlobStore:
    name = "postgres"

    def __init__(self, pool: Any) -> None:
        self.pool = pool

    def put(self, path: str, data: bytes) -> None:
        with self.pool.connection() as conn:
            conn.execute("insert into artifact_blobs (path, data) values (%s, %s)", (path, data))

    def get(self, path: str) -> Optional[bytes]:
        with self.pool.connection() as conn:
            row = conn.execute("select data from artifact_blobs where path = %s", (path,)).fetchone()
        return bytes(row["data"]) if row else None

    def delete(self, paths: Iterable[str]) -> None:
        paths = list(paths)
        if paths:
            with self.pool.connection() as conn:
                conn.execute("delete from artifact_blobs where path = any(%s)", (paths,))


class SupabaseBlobStore:
    name = "supabase-storage"

    def __init__(self, settings: Settings, timeout: float = 60.0) -> None:
        self.base = f"{settings.supabase_url}/storage/v1"
        self.bucket = settings.storage_bucket
        key = settings.supabase_service_key
        # Legacy service_role keys are JWTs and are sent both ways. The newer "sb_secret_..." keys are NOT JWTs: they go in
        # the apikey header only, and a Bearer copy would be rejected as an invalid JWT.
        self.headers = {"apikey": key} if key.startswith("sb_secret_") else {"Authorization": f"Bearer {key}", "apikey": key}
        self.timeout = timeout

    def _object(self, path: str, prefix: str = "") -> str:
        return f"{self.base}/object/{prefix}{self.bucket}/{quote(path, safe='/')}"

    def put(self, path: str, data: bytes) -> None:
        response = httpx.post(self._object(path), content=data, timeout=self.timeout,
                              headers={**self.headers, "Content-Type": "application/octet-stream", "x-upsert": "false"})
        if response.status_code >= 300:
            logger.error("Storage upload failed: HTTP %s %s", response.status_code, response.text[:200])
            raise BlobError("Could not store the file")

    def get(self, path: str) -> Optional[bytes]:
        response = httpx.get(self._object(path, "authenticated/"), headers=self.headers, timeout=self.timeout)
        if response.status_code in (400, 404):
            return None
        if response.status_code >= 300:
            raise BlobError("Could not read the file")
        return response.content

    def delete(self, paths: Iterable[str]) -> None:
        paths = list(paths)
        if not paths:
            return
        response = httpx.request("DELETE", f"{self.base}/object/{self.bucket}", json={"prefixes": paths},
                                 headers=self.headers, timeout=self.timeout)
        if response.status_code >= 300:
            logger.error("Storage delete failed: HTTP %s %s", response.status_code, response.text[:200])
            raise BlobError("Could not delete the file")


def make_blob_store(settings: Settings, pool: Any):
    if settings.supabase_url and settings.supabase_service_key:
        return SupabaseBlobStore(settings)
    return DbBlobStore(pool)
