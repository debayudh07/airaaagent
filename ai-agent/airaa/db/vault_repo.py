"""Sealed storage metadata (vault keys, artifacts) and shares. Holds ciphertext-adjacent data only."""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional, Sequence

from .util import as_uuid, jsonb, stringify_ids, vec


def _b(value: Any) -> Optional[bytes]:
    return bytes(value) if value is not None else None


class VaultRepo:
    def __init__(self, pool: Any) -> None:
        self.pool = pool

    # ---- vault keys ----------------------------------------------------
    def put_key(self, wallet_id: str, wrapper_type: str, wrapped_dek: bytes, kdf: Dict[str, Any]) -> Dict[str, Any]:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                insert into vault_keys (wallet_id, wrapper_type, wrapped_dek, kdf) values (%s, %s, %s, %s)
                on conflict (wallet_id, wrapper_type)
                do update set wrapped_dek = excluded.wrapped_dek, kdf = excluded.kdf, created_at = now()
                returning id, wrapper_type, created_at
                """,
                (wallet_id, wrapper_type, wrapped_dek, jsonb(kdf)),
            ).fetchone()
        return stringify_ids(row)

    def list_keys(self, wallet_id: str) -> List[Dict[str, Any]]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "select id, wrapper_type, wrapped_dek, kdf, created_at from vault_keys where wallet_id = %s order by created_at",
                (wallet_id,),
            ).fetchall()
        return [{**stringify_ids(r), "wrapped_dek": _b(r["wrapped_dek"])} for r in rows]

    def delete_key(self, wallet_id: str, wrapper_type: str) -> bool:
        with self.pool.connection() as conn:
            return conn.execute(
                "delete from vault_keys where wallet_id = %s and wrapper_type = %s", (wallet_id, wrapper_type)
            ).rowcount > 0

    # ---- artifacts -----------------------------------------------------
    def create_artifact(self, wallet_id: str, artifact_id: str, storage_path: str, size_bytes: int, wrapped_cek: bytes,
                        meta_enc: Optional[bytes], index_summary: Optional[str], index_embedding: Optional[Sequence[float]],
                        enc_alg: str = "A256GCM") -> Dict[str, Any]:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                insert into artifacts (id, wallet_id, storage_path, size_bytes, enc_alg, wrapped_cek, meta_enc,
                                       index_summary, index_embedding)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
                returning id, size_bytes, enc_alg, created_at
                """,
                (artifact_id, wallet_id, storage_path, size_bytes, enc_alg, wrapped_cek, meta_enc, index_summary,
                 vec(index_embedding) if index_embedding is not None else None),
            ).fetchone()
        return stringify_ids(row)

    def list_artifacts(self, wallet_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "select id, size_bytes, enc_alg, wrapped_cek, meta_enc, index_summary, created_at from artifacts "
                "where wallet_id = %s order by created_at desc limit %s",
                (wallet_id, limit),
            ).fetchall()
        return [{**stringify_ids(r), "wrapped_cek": _b(r["wrapped_cek"]), "meta_enc": _b(r["meta_enc"])} for r in rows]

    def get_artifact(self, artifact_id: str, wallet_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        aid = as_uuid(artifact_id)
        if aid is None:
            return None
        with self.pool.connection() as conn:
            row = conn.execute(
                "select id, wallet_id, storage_path, size_bytes, enc_alg, wrapped_cek, meta_enc, index_summary, created_at "
                "from artifacts where id = %s and (%s::uuid is null or wallet_id = %s::uuid)",
                (aid, wallet_id, wallet_id),
            ).fetchone()
        if not row:
            return None
        return {**stringify_ids(row), "wrapped_cek": _b(row["wrapped_cek"]), "meta_enc": _b(row["meta_enc"])}

    def delete_artifact(self, wallet_id: str, artifact_id: str) -> Optional[str]:
        """Delete the row; returns its storage path so the caller can remove the object."""
        aid = as_uuid(artifact_id)
        if aid is None:
            return None
        with self.pool.connection() as conn:
            row = conn.execute(
                "delete from artifacts where id = %s and wallet_id = %s returning storage_path", (aid, wallet_id)
            ).fetchone()
        return row["storage_path"] if row else None

    def storage_paths(self, wallet_id: str) -> List[str]:
        with self.pool.connection() as conn:
            return [r["storage_path"] for r in conn.execute("select storage_path from artifacts where wallet_id = %s", (wallet_id,)).fetchall()]

    def search_artifacts(self, wallet_id: str, embedding: Sequence[float], k: int, min_similarity: float) -> List[Dict[str, Any]]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "select * from match_artifacts(%s::uuid, %s::vector, %s::int, %s::real)", (wallet_id, vec(embedding), k, min_similarity)
            ).fetchall()
        return [stringify_ids(r) for r in rows]

    # ---- shares --------------------------------------------------------
    def create_share(self, owner_wallet_id: str, resource_type: str, resource_id: str, mode: str,
                     recipient_address: Optional[str], token_hash: Optional[str], wrapped_key: Optional[bytes],
                     redact_research_data: bool, ttl_hours: Optional[int]) -> Dict[str, Any]:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                insert into shares (owner_wallet_id, resource_type, resource_id, mode, recipient_address, token_hash,
                                    wrapped_key, redact_research_data, expires_at)
                values (%s, %s, %s, %s, %s, %s, %s, %s,
                        case when %s::int is null then null else now() + make_interval(hours => %s::int) end)
                returning id, resource_type, resource_id, mode, recipient_address, redact_research_data, created_at, expires_at
                """,
                (owner_wallet_id, resource_type, resource_id, mode, recipient_address, token_hash, wrapped_key,
                 redact_research_data, ttl_hours, ttl_hours),
            ).fetchone()
        return stringify_ids(row)

    def list_shares(self, owner_wallet_id: str) -> List[Dict[str, Any]]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "select id, resource_type, resource_id, mode, recipient_address, redact_research_data, created_at, expires_at, revoked_at "
                "from shares where owner_wallet_id = %s order by created_at desc",
                (owner_wallet_id,),
            ).fetchall()
        return [stringify_ids(r) for r in rows]

    def revoke_share(self, owner_wallet_id: str, share_id: str) -> bool:
        sid = as_uuid(share_id)
        if sid is None:
            return False
        with self.pool.connection() as conn:
            return conn.execute(
                "update shares set revoked_at = now() where id = %s and owner_wallet_id = %s and revoked_at is null",
                (sid, owner_wallet_id),
            ).rowcount > 0

    def get_link_share(self, token: str) -> Optional[Dict[str, Any]]:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with self.pool.connection() as conn:
            row = conn.execute(
                "select id, owner_wallet_id, resource_type, resource_id, wrapped_key, redact_research_data, created_at "
                "from shares where token_hash = %s and mode = 'link' and revoked_at is null "
                "and (expires_at is null or expires_at > now())",
                (token_hash,),
            ).fetchone()
        return {**stringify_ids(row), "wrapped_key": _b(row["wrapped_key"])} if row else None

    def get_wallet_share(self, resource_type: str, resource_id: str, recipient_address: str) -> Optional[Dict[str, Any]]:
        with self.pool.connection() as conn:
            row = conn.execute(
                "select id, owner_wallet_id, redact_research_data from shares "
                "where resource_type = %s and resource_id = %s and recipient_address = %s "
                "and mode = 'wallet' and revoked_at is null and (expires_at is null or expires_at > now()) limit 1",
                (resource_type, resource_id, recipient_address.lower()),
            ).fetchone()
        return stringify_ids(row) if row else None

    def list_received(self, recipient_address: str) -> List[Dict[str, Any]]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "select s.id, s.resource_type, s.resource_id, s.redact_research_data, s.created_at, w.address as owner_address "
                "from shares s join wallets w on w.id = s.owner_wallet_id "
                "where s.recipient_address = %s and s.mode = 'wallet' and s.revoked_at is null "
                "and (s.expires_at is null or s.expires_at > now()) order by s.created_at desc",
                (recipient_address.lower(),),
            ).fetchall()
        return [stringify_ids(r) for r in rows]
