"""Runs planned tools concurrently, each with a timeout, retry on transient failure, and a trace."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Iterable, List, Optional

from ..config import Settings, get_settings
from ..schemas import Entities, EventCallback, ResearchRequest
from ..tools import TOOLS
from ..tools.web import extract_urls

logger = logging.getLogger(__name__)

# The UI's time-range selector, used as the default chart window.
_RANGE_DAYS = {"1d": 1, "7d": 7, "30d": 30, "90d": 90, "1y": 365}

_TRANSIENT_MARKERS = ("timed out", "timeout", "http 429", "http 500", "http 502", "http 503", "http 504",
                      "rate limited", "http 429)", "connecterror", "readerror", "remoteprotocolerror")


async def emit(on_event: EventCallback, event: Dict[str, Any]) -> None:
    """Fire a progress event; a broken listener must never break research."""
    if on_event is None:
        return
    try:
        await on_event(event)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Event listener failed: %s", exc)


def build_tool_args(name: str, request: ResearchRequest, entities: Entities) -> Optional[Dict[str, Any]]:
    """Arguments for ``name``, or ``None`` if it cannot run (e.g. Etherscan without an address)."""
    q = request.query
    if name == "coinmarketcap_tool":
        return {"query": q, "symbols": entities.symbols or None}
    if name == "defillama_tool":
        return {
            "query": q,
            "protocols": entities.protocols or None,
            "chain": entities.chain,
            "symbols": entities.symbols or None,
        }
    if name == "dune_analytics_tool":
        # The user's wallet is not a token address, so it is intentionally not passed here.
        return {"query": q, "time_range": request.time_range, "chain": (entities.chain or "").lower() or None}
    if name == "etherscan_tool":
        if not request.address:
            return None
        return {"query": q, "address": request.address, "chain": (entities.chain or "").lower() or None}
    if name == "coingecko_tool":
        return {"query": q, "symbols": entities.symbols or None, "days": entities.days or _RANGE_DAYS.get(request.time_range)}
    if name == "dexscreener_tool":
        return {"query": q, "search": entities.search_query or (" ".join(entities.symbols[:1]) or None)}
    if name == "news_tool":
        return {"query": q, "symbols": entities.symbols or None, "search": entities.search_query}
    if name == "web_search_tool":
        return {"query": q, "search": entities.search_query}
    if name == "read_url_tool":
        urls = entities.urls or extract_urls(q)
        return {"query": q, "urls": urls} if urls else None
    return None


def _is_transient(result: Dict[str, Any]) -> bool:
    error = str(result.get("error", "")).lower()
    return any(marker in error for marker in _TRANSIENT_MARKERS)


async def _run_one(name: str, args: Dict[str, Any], settings: Settings, on_event: EventCallback,
                   cache: Optional[Any] = None) -> Dict[str, Any]:
    tool = TOOLS[name]
    await emit(on_event, {"type": "tool_start", "tool": name})
    started = time.perf_counter()
    attempts = 0
    result: Dict[str, Any] = {"success": False, "error": "not run"}

    ticket = None
    if cache is not None:
        hit, ticket = await cache.lookup(name, args)
        if hit is not None:
            cached = dict(hit["result"])
            cached["cached"] = {"age_seconds": hit["age_seconds"], "match": hit["match"], "similarity": hit["similarity"]}
            return await _finish(name, cached, started, 0, on_event)

    for attempt in range(settings.tool_retries + 1):
        attempts = attempt + 1
        try:
            result = await asyncio.wait_for(tool.ainvoke(args), timeout=settings.tool_timeout_seconds)
            if not isinstance(result, dict):
                result = {"success": False, "error": "Tool returned an unexpected payload"}
        except asyncio.TimeoutError:
            result = {"success": False, "error": f"Timed out after {settings.tool_timeout_seconds:.0f}s"}
        except Exception as exc:  # tools should not raise, but never let one take down the run
            logger.exception("Tool %s raised", name)
            result = {"success": False, "error": f"{type(exc).__name__}: {exc}"}

        if result.get("success") or not _is_transient(result) or attempt >= settings.tool_retries:
            break
        await emit(on_event, {"type": "tool_retry", "tool": name, "error": result.get("error")})
        await asyncio.sleep(0.8 * (attempt + 1))

    if cache is not None and result.get("success"):
        await cache.store(ticket, result)
    return await _finish(name, result, started, attempts, on_event)


async def _finish(name: str, result: Dict[str, Any], started: float, attempts: int, on_event: EventCallback) -> Dict[str, Any]:
    duration_ms = int((time.perf_counter() - started) * 1000)
    result.setdefault("source", name.replace("_tool", ""))
    result.update({"tool": name, "duration_ms": duration_ms, "attempts": attempts})
    await emit(on_event, {
        "type": "tool_end",
        "tool": name,
        "success": bool(result.get("success")),
        "duration_ms": duration_ms,
        "cached": bool(result.get("cached")),
        "error": None if result.get("success") else result.get("error"),
    })
    return result


async def run_tools(
    names: Iterable[str],
    request: ResearchRequest,
    entities: Entities,
    on_event: EventCallback = None,
    settings: Optional[Settings] = None,
    cache: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """Run each named tool concurrently and return their result dicts in plan order.

    ``cache`` (a :class:`airaa.cache.ToolCache`) serves fresh results for public tools without calling them."""
    settings = settings or get_settings()
    jobs = []
    for name in dict.fromkeys(names):
        args = build_tool_args(name, request, entities) if name in TOOLS else None
        if args is None:
            logger.warning("Skipping %s: unknown tool or missing arguments", name)
            continue
        jobs.append(_run_one(name, args, settings, on_event, cache))
    return list(await asyncio.gather(*jobs)) if jobs else []
