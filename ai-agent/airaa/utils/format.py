"""Number formatting helpers. All return ``"N/A"`` for missing or non-numeric input."""
from __future__ import annotations

from typing import Any, Optional


def _to_float(value: Any) -> Optional[float]:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def fmt_money(value: Any, decimals: int = 2) -> str:
    n = _to_float(value)
    return "N/A" if n is None else f"${n:,.{decimals}f}"


def fmt_num(value: Any, decimals: Optional[int] = None) -> str:
    n = _to_float(value)
    if n is None:
        return "N/A"
    return f"{round(n):,}" if decimals is None else f"{n:,.{decimals}f}"


def fmt_pct(value: Any) -> str:
    n = _to_float(value)
    return "N/A" if n is None else f"{n:+.2f}%"
