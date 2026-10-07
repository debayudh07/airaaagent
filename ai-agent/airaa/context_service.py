"""Personalisation context: a wallet's watchlist and on-chain portfolio snapshots."""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .config import Settings, get_settings

ENTITY_TYPES = ("token", "protocol", "chain")
_ENTITY_ID = re.compile(r"^[a-z0-9][a-z0-9 ._:-]{0,79}$")
_NATIVE = {"ethereum": "ETH", "base": "ETH", "arbitrum": "ETH", "optimism": "ETH", "linea": "ETH",
           "polygon": "POL", "bsc": "BNB", "avalanche": "AVAX"}


class ContextError(ValueError):
    """Invalid input; the message is safe to show to the user."""


def build_portfolio_summary(chain: str, address: str, balance: Dict[str, Any], transfers: Dict[str, Any]) -> Dict[str, Any]:
    """Turn raw Etherscan results into ``{"summary": str, "holdings": dict}``.

    Etherscan only exposes the native balance directly. Token activity is the net flow of the most recent transfers,
    which is not a balance, and the summary says so, so the model does not present it as one.
    """
    symbol = _NATIVE.get(chain, "ETH")
    holdings: Dict[str, Any] = {"address": address, "chain": chain, "tokens": []}
    parts: List[str] = []

    raw = (balance.get("data") or {}).get("result") if balance.get("success") else None
    if isinstance(raw, str) and raw.isdigit():
        native = int(raw) / 10**18
        holdings["native"] = {"symbol": symbol, "balance": native}
        parts.append(f"native balance {native:,.4f} {symbol}")

    rows = (transfers.get("data") or {}).get("result") if transfers.get("success") else None
    if isinstance(rows, list) and rows:
        flows: Dict[str, Dict[str, Any]] = {}
        for tx in rows:
            if not isinstance(tx, dict):
                continue
            try:
                decimals = int(tx.get("tokenDecimal") or 0)
                amount = int(tx.get("value") or 0) / 10**decimals
            except (TypeError, ValueError):
                continue
            sym = str(tx.get("tokenSymbol") or "?")[:12]
            incoming = str(tx.get("to", "")).lower() == address.lower()
            entry = flows.setdefault(sym, {"symbol": sym, "net": 0.0, "transfers": 0, "contract": tx.get("contractAddress")})
            entry["net"] += amount if incoming else -amount
            entry["transfers"] += 1
        tokens = sorted(flows.values(), key=lambda t: t["transfers"], reverse=True)[:8]
        holdings["tokens"] = tokens
        if tokens:
            parts.append("recent token activity (net flow over its last %d transfers, not a balance): " % len(rows)
                         + ", ".join(f"{t['symbol']} {t['net']:+,.2f} ({t['transfers']} transfers)" for t in tokens))

    if not parts:
        raise ContextError(f"No on-chain data found for this wallet on {chain}")
    return {"summary": f"Wallet {address} on {chain}: " + "; ".join(parts) + ".", "holdings": holdings}


class ContextService:
    def __init__(self, repo: Any, embedder: Any = None, settings: Optional[Settings] = None) -> None:
        self.repo, self.embedder = repo, embedder
        self.settings = settings or get_settings()

    def _embed(self, text: str, task: str = "document") -> Optional[List[float]]:
        """Embedding is a nicety here: without it the item is still stored and listed, just not searchable."""
        if self.embedder is None:
            return None
        try:
            return self.embedder.embed_one_sync(text, task)
        except Exception:  # noqa: BLE001
            return None

    # ---- watchlist (sync: Flask handlers) -----------------------------
    def add_watch(self, wallet_id: str, entity_type: str, entity_id: str, note: Optional[str] = None) -> Dict[str, Any]:
        entity_type = (entity_type or "").strip().lower()
        entity_id = (entity_id or "").strip().lower()
        note = (note or "").strip()[:500] or None
        if entity_type not in ENTITY_TYPES:
            raise ContextError("entity_type must be one of: " + ", ".join(ENTITY_TYPES))
        if not _ENTITY_ID.match(entity_id):
            raise ContextError("entity_id must be 1-80 letters, digits or . _ : - characters")
        if self.repo.count_watch(wallet_id) >= self.settings.max_watchlist_items:
            existing = {(w["entity_type"], w["entity_id"]) for w in self.repo.list_watch(wallet_id)}
            if (entity_type, entity_id) not in existing:
                raise ContextError(f"Watchlist is full ({self.settings.max_watchlist_items} items)")
        vector = self._embed(f"{entity_type} {entity_id}" + (f": {note}" if note else ""))
        return self.repo.add_watch(wallet_id, entity_type, entity_id, note, vector)

    def list_watch(self, wallet_id: str) -> List[Dict[str, Any]]:
        return self.repo.list_watch(wallet_id)

    def remove_watch(self, wallet_id: str, watch_id: str) -> bool:
        return self.repo.remove_watch(wallet_id, watch_id)

    # ---- portfolio -----------------------------------------------------
    async def refresh_portfolio(self, wallet_id: str, address: str, chain: str = "ethereum") -> Dict[str, Any]:
        from .http import client_scope
        from .tools import TOOLS
        from .utils.assets import ETHERSCAN_CHAIN_IDS

        chain = (chain or "ethereum").lower()
        if chain not in ETHERSCAN_CHAIN_IDS:
            raise ContextError(f"Chain '{chain}' is not supported")
        tool = TOOLS["etherscan_tool"]
        async with client_scope():
            balance, transfers = await asyncio.gather(
                tool.ainvoke({"query": "balance", "address": address, "chain": chain}),
                tool.ainvoke({"query": "token transfers", "address": address, "chain": chain}),
            )
        if not balance.get("success") and not transfers.get("success"):
            raise ContextError(str(balance.get("error") or transfers.get("error") or "Could not read the wallet"))
        built = build_portfolio_summary(chain, address, balance, transfers)
        vector = None
        if self.embedder is not None:
            try:
                vector = await self.embedder.aembed_one(built["summary"], "document")
            except Exception:  # noqa: BLE001
                vector = None
        return await asyncio.to_thread(self.repo.add_snapshot, wallet_id, chain, built["holdings"], built["summary"], vector)

    def snapshots(self, wallet_id: str) -> List[Dict[str, Any]]:
        return self.repo.latest_snapshots(wallet_id)

    # ---- retrieval (async: agent pipeline) ----------------------------
    async def relevant(self, wallet_id: str, vector: Optional[List[float]]) -> Dict[str, Any]:
        """Everything on the watchlist, notes highlighted for the items closest to the question, plus latest snapshots."""
        watch, snaps = await asyncio.gather(
            asyncio.to_thread(self.repo.list_watch, wallet_id),
            asyncio.to_thread(self.repo.latest_snapshots, wallet_id, 2),
        )
        close: List[Dict[str, Any]] = []
        if watch and vector is not None:
            close = await asyncio.to_thread(self.repo.search_watch, wallet_id, vector, 5, 0.45)
        return {"watchlist": watch, "close": close, "snapshots": snaps}


def format_block(data: Dict[str, Any], now: Optional[datetime] = None) -> str:
    """Prompt block for the watchlist and portfolio. Empty when the wallet has neither."""
    now = now or datetime.now(timezone.utc)
    lines: List[str] = []
    watch = data.get("watchlist") or []
    if watch:
        grouped: Dict[str, List[str]] = {}
        for w in watch[:30]:
            grouped.setdefault(w["entity_type"], []).append(w["entity_id"].upper() if w["entity_type"] == "token" else w["entity_id"])
        lines.append("USER WATCHLIST: " + "; ".join(f"{kind}s: {', '.join(items)}" for kind, items in grouped.items()))
        notes = [f"{c['entity_id']}: {c['note']}" for c in data.get("close") or [] if c.get("note")]
        if notes:
            lines.append("Notes on watched items relevant to this question: " + " | ".join(notes))
    for snap in data.get("snapshots") or []:
        fetched = snap["fetched_at"]
        stamp = datetime.fromisoformat(fetched) if isinstance(fetched, str) else fetched
        days = max((now - stamp).total_seconds() / 86400, 0)
        age = f"{days:.0f} day(s) old" if days >= 1 else "under a day old"
        lines.append(f"PORTFOLIO SNAPSHOT ({age}): {snap['summary']}")
    if not lines:
        return ""
    return ("USER CONTEXT (the user's own watchlist and wallet; personalise the answer to it, treat the portfolio as a "
            "possibly stale snapshot, never as live data):\n" + "\n".join(lines))
