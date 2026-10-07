"""Semantic cache for tool results.

Only public, wallet-independent tools are cached (never Etherscan, which is per-address). An entry is reused when
the tool and its *structured* arguments (symbols, protocols, chain, ...) match exactly and the free-text question is
either identical or semantically near-identical (cosine >= ``cache_similarity``) and the entry has not expired.
Structured arguments are never matched fuzzily, so "ETH price" cannot be answered with BTC data.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from ..config import Settings, get_settings

logger = logging.getLogger(__name__)

# tool -> seconds a result stays fresh. Anything not listed is not cached.
TTL_SECONDS: Dict[str, int] = {
    "coinmarketcap_tool": 60,
    "coingecko_tool": 120,
    "defillama_tool": 600,
    "dexscreener_tool": 60,
    "news_tool": 600,
    "web_search_tool": 900,
    "dune_analytics_tool": 3600,
}
# Free-text arguments: embedded for the semantic lookup and excluded from the exact structured match.
FREE_TEXT_FIELDS: Dict[str, Tuple[str, ...]] = {
    "news_tool": ("query", "search"),
    "web_search_tool": ("query", "search"),
}
DEFAULT_FREE_TEXT = ("query",)
MAX_RESULT_BYTES = 400_000


def _canonical(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _canonical(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        items = [_canonical(v) for v in value]
        return sorted(items, key=lambda x: json.dumps(x, sort_keys=True, default=str)) if all(not isinstance(i, (dict, list)) for i in items) else items
    return value


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@dataclass
class Ticket:
    """Carries a miss from lookup to store so the embedding is computed once."""
    tool: str
    key_hash: str
    params_hash: str
    query_text: str
    vector: Optional[List[float]] = None


class ToolCache:
    def __init__(self, repo: Any, embedder: Any = None, settings: Optional[Settings] = None) -> None:
        self.repo, self.embedder = repo, embedder
        self.settings = settings or get_settings()

    def ttl(self, tool: str) -> Optional[int]:
        return TTL_SECONDS.get(tool) if self.settings.cache_enabled else None

    @staticmethod
    def keys(tool: str, args: Dict[str, Any]) -> Tuple[str, str, str]:
        free = FREE_TEXT_FIELDS.get(tool, DEFAULT_FREE_TEXT)
        structured = {k: v for k, v in args.items() if k not in free}
        params_hash = _sha(tool + "|" + json.dumps(_canonical(structured), sort_keys=True, default=str))
        query_text = " | ".join(str(args[f]).strip().lower() for f in free if args.get(f))
        return _sha(params_hash + "|" + query_text), params_hash, query_text

    async def lookup(self, tool: str, args: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[Ticket]]:
        """Returns ``(hit, ticket)``. ``hit`` is ``{"result", "age_seconds", "match", "similarity"}`` or ``None``;
        ``ticket`` is what to pass to :meth:`store` on a miss (``None`` if the tool is not cacheable)."""
        if self.ttl(tool) is None:
            return None, None
        key_hash, params_hash, query_text = self.keys(tool, args)
        ticket = Ticket(tool, key_hash, params_hash, query_text)
        try:
            exact = await asyncio.to_thread(self.repo.get_exact, key_hash)
            if exact:
                return {"result": exact["result"], "age_seconds": exact["age_seconds"], "match": "exact", "similarity": 1.0}, ticket
            if self.embedder is not None and query_text:
                ticket.vector = await self.embedder.aembed_one(query_text, "similarity")
                near = await asyncio.to_thread(
                    self.repo.get_semantic, tool, params_hash, ticket.vector, self.settings.cache_similarity)
                if near:
                    return {"result": near["result"], "age_seconds": near["age_seconds"], "match": "semantic",
                            "similarity": round(float(near["similarity"]), 4)}, ticket
        except Exception as exc:  # noqa: BLE001 - a broken cache must never break research
            logger.warning("Tool cache lookup failed (%s); running the tool", exc)
        return None, ticket

    async def store(self, ticket: Optional[Ticket], result: Dict[str, Any]) -> None:
        ttl = self.ttl(ticket.tool) if ticket else None
        if ticket is None or ttl is None or not result.get("success"):
            return
        try:
            payload = json.loads(json.dumps(result, default=str))
            if len(json.dumps(payload)) > MAX_RESULT_BYTES:
                return
            await asyncio.to_thread(self.repo.put, ticket.key_hash, ticket.tool, ticket.params_hash,
                                    ticket.query_text, ticket.vector, payload, ttl)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Tool cache store failed: %s", exc)
