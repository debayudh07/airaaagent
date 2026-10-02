"""Request validation. Returns ``(ResearchRequest, None)`` or ``(None, error message)``."""
from __future__ import annotations

import re
from typing import Any, Optional, Tuple

from ..config import Settings
from ..schemas import ResearchRequest

TIME_RANGES = {"1d", "7d", "30d", "90d", "1y"}
_ADDRESS = re.compile(r"^0x[a-fA-F0-9]{40}$")
SESSION_ID = re.compile(r"^[A-Za-z0-9_\-]{8,100}$")


def parse_research_payload(payload: Any, settings: Settings) -> Tuple[Optional[ResearchRequest], Optional[str]]:
    if not isinstance(payload, dict):
        return None, "Request body must be a JSON object"

    query = payload.get("query")
    if not isinstance(query, str) or not query.strip():
        return None, "Field 'query' (non-empty string) is required"
    query = query.strip()
    if len(query) > settings.max_query_chars:
        return None, f"Field 'query' must be at most {settings.max_query_chars} characters"

    address = payload.get("address")
    if address in (None, ""):
        address = None
    elif not isinstance(address, str) or not _ADDRESS.match(address.strip()):
        return None, "Field 'address' must be a 0x-prefixed 40-hex-character address"
    else:
        address = address.strip()

    time_range = payload.get("time_range") or "7d"
    if time_range not in TIME_RANGES:
        return None, f"Field 'time_range' must be one of: {', '.join(sorted(TIME_RANGES))}"

    session_id = payload.get("session_id")
    if session_id in (None, ""):
        session_id = None
    elif not isinstance(session_id, str) or not SESSION_ID.match(session_id):
        return None, "Field 'session_id' must be 8-100 characters of letters, digits, '-' or '_'"

    return ResearchRequest(query=query, address=address, time_range=time_range, session_id=session_id), None
