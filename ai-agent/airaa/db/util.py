"""Small helpers shared by the repositories."""
from __future__ import annotations

import json
import uuid
from typing import Any, Optional, Sequence


def jsonb(value: Any) -> Any:
    """Wrap a Python value for a jsonb parameter (datetimes etc. fall back to ``str``)."""
    from psycopg.types.json import Jsonb

    return Jsonb(value, dumps=lambda o: json.dumps(o, default=str))


def vec(values: Sequence[float]) -> str:
    """pgvector text literal; use as ``%s::vector``."""
    return "[" + ",".join(f"{v:.7g}" for v in values) + "]"


def as_uuid(value: Any) -> Optional[str]:
    """Canonical UUID string, or ``None`` if ``value`` is not a UUID (so bad ids 404 instead of raising)."""
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        return None


def stringify_ids(row: dict) -> dict:
    """UUID/datetime values to JSON-friendly strings (shallow)."""
    out = {}
    for k, v in row.items():
        if isinstance(v, uuid.UUID):
            out[k] = str(v)
        elif hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif isinstance(v, (bytes, bytearray, memoryview)):
            out[k] = bytes(v)
        else:
            out[k] = v
    return out
