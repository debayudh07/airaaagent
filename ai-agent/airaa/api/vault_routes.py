"""Sealed storage and sharing endpoints.

The server never sees plaintext or unwrapped keys here: it stores wrapped keys and ciphertext, enforces ownership
and size limits, and serves them back. See ``client/lib/vault.ts`` for the matching browser-side crypto.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from flask import Flask, Response, jsonify, request

from ..config import Settings
from ..vault.service import VaultError, b64decode, b64encode, public_artifact_row
from .routes import current_sessions
from .deps import ApiError, client_ip, json_object, limit_or_429, need, wallet_or_none, wallet_required
from .serialize import conversation_json

_ADDRESS = re.compile(r"^0x[a-fA-F0-9]{40}$")
MAX_SHARE_HOURS = 24 * 365


def register_vault_routes(app: Flask, settings: Settings, services: Any, limiter: Any) -> None:
    sessions: Callable[[], Any] = current_sessions

    def vault():
        return need(services.vault, "Sealed storage")

    # ------------------------------------------------------------------ vault keys
    @app.get("/api/vault")
    def get_vault():
        wallet = wallet_required(services)
        keys = vault().list_keys(wallet.id)
        return jsonify({"success": True, "initialized": bool(keys), "keys": keys,
                        "limits": {"max_artifact_bytes": settings.max_artifact_bytes}})

    @app.put("/api/vault/keys/<wrapper_type>")
    def put_vault_key(wrapper_type: str):
        wallet = wallet_required(services)
        return jsonify({"success": True, "key": vault().put_key(wallet.id, wrapper_type, json_object())})

    @app.delete("/api/vault/keys/<wrapper_type>")
    def delete_vault_key(wrapper_type: str):
        wallet = wallet_required(services)
        vault().delete_key(wallet.id, wrapper_type)
        return jsonify({"success": True})

    # ------------------------------------------------------------------ artifacts
    @app.post("/api/artifacts")
    def create_artifact():
        wallet = wallet_required(services)
        limit_or_429(limiter, f"artifact:{wallet.id}")
        return jsonify({"success": True, "artifact": vault().create_artifact(wallet.id, json_object())}), 201

    @app.get("/api/artifacts")
    def list_artifacts():
        wallet = wallet_required(services)
        return jsonify({"success": True, "artifacts": vault().list_artifacts(wallet.id)})

    @app.get("/api/artifacts/search")
    def search_artifacts():
        wallet = wallet_required(services)
        query = (request.args.get("q") or "").strip()
        if not query:
            raise ApiError("'q' is required")
        return jsonify({"success": True, "results": vault().search(wallet.id, query[:300])})

    @app.get("/api/artifacts/<artifact_id>")
    def get_artifact(artifact_id: str):
        wallet = wallet_required(services)
        return jsonify({"success": True, "artifact": public_artifact_row(vault().get_artifact(wallet.id, artifact_id))})

    @app.get("/api/artifacts/<artifact_id>/blob")
    def get_artifact_blob(artifact_id: str):
        wallet = wallet_required(services)
        row = vault().get_artifact(wallet.id, artifact_id)
        response = Response(vault().read_blob(row), mimetype="application/octet-stream")
        response.headers["Cache-Control"] = "private, no-store"
        return response

    @app.delete("/api/artifacts/<artifact_id>")
    def delete_artifact(artifact_id: str):
        wallet = wallet_required(services)
        vault().delete_artifact(wallet.id, artifact_id)
        return jsonify({"success": True})

    # ------------------------------------------------------------------ shares
    @app.post("/api/shares")
    def create_share():
        wallet = wallet_required(services)
        v = vault()
        body = json_object()
        resource_type, resource_id = body.get("resource_type"), str(body.get("resource_id") or "")
        mode = body.get("mode", "link")
        if resource_type not in ("conversation", "artifact") or not resource_id:
            raise ApiError("'resource_type' (conversation|artifact) and 'resource_id' are required")
        if mode not in ("link", "wallet"):
            raise ApiError("'mode' must be 'link' or 'wallet'")
        ttl = body.get("ttl_hours")
        if ttl is not None and (not isinstance(ttl, int) or isinstance(ttl, bool) or not 1 <= ttl <= MAX_SHARE_HOURS):
            raise ApiError(f"'ttl_hours' must be an integer between 1 and {MAX_SHARE_HOURS}")
        redact = bool(body.get("redact_research_data", False))

        if resource_type == "conversation":
            session = sessions().get(resource_id)
            if session is None or session.get("wallet_id") != wallet.id:
                raise ApiError("Conversation not found (guest conversations must be claimed by your wallet first)", 404)
        else:
            if mode != "link":
                raise ApiError("Sealed files can only be shared by link for now")
            v.get_artifact(wallet.id, resource_id)   # 404 unless owned

        wrapped_key = None
        if resource_type == "artifact":
            wrapped_key = b64decode(body.get("wrapped_key"), "wrapped_key", 512)

        if mode == "link":
            share = v.create_link_share(wallet.id, resource_type, resource_id, wrapped_key, redact, ttl)
        else:
            recipient = str(body.get("recipient_address") or "")
            if not _ADDRESS.match(recipient):
                raise ApiError("'recipient_address' must be a 0x wallet address")
            share = v.repo.create_share(wallet.id, resource_type, resource_id, "wallet", recipient.lower(), None, None, redact, ttl)
        return jsonify({"success": True, "share": share}), 201

    @app.get("/api/shares")
    def list_shares():
        wallet = wallet_required(services)
        return jsonify({"success": True, "shares": vault().repo.list_shares(wallet.id)})

    @app.get("/api/shares/received")
    def received_shares():
        wallet = wallet_required(services)
        return jsonify({"success": True, "shares": vault().repo.list_received(wallet.address)})

    @app.delete("/api/shares/<share_id>")
    def revoke_share(share_id: str):
        wallet = wallet_required(services)
        if not vault().repo.revoke_share(wallet.id, share_id):
            raise ApiError("Share not found", 404)
        return jsonify({"success": True})

    @app.get("/api/share/<token>")
    def open_link_share(token: str):
        """Public: anyone holding the link. Sealed files come back as ciphertext plus the key wrapped by the link secret,
        which only exists in the URL fragment and never reaches this server."""
        limit_or_429(limiter, f"share:{client_ip()}")
        v = vault()
        share = v.repo.get_link_share(token)
        if share is None:
            raise ApiError("This link is invalid, expired or was revoked", 404)
        if share["resource_type"] == "conversation":
            session = sessions().get(share["resource_id"])
            if session is None:
                raise ApiError("This conversation no longer exists", 404)
            return jsonify({"type": "conversation", **conversation_json(session, share["resource_id"], share["redact_research_data"])})
        row = v.repo.get_artifact(share["resource_id"])
        if row is None:
            raise ApiError("This file no longer exists", 404)
        return jsonify({"success": True, "type": "artifact", "id": row["id"], "wrapped_key": b64encode(share["wrapped_key"]),
                        "meta_enc": b64encode(row.get("meta_enc")), "created_at": row["created_at"],
                        "ciphertext": b64encode(v.read_blob(row))})

    @app.get("/api/shared/conversation/<conversation_id>")
    def open_wallet_share(conversation_id: str):
        wallet = wallet_required(services)
        share = vault().repo.get_wallet_share("conversation", conversation_id, wallet.address)
        session = sessions().get(conversation_id) if share else None
        if share is None or session is None:
            raise ApiError("Not found", 404)
        return jsonify({"type": "conversation", **conversation_json(session, conversation_id, share["redact_research_data"])})
