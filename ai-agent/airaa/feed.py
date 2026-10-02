"""Home-board feed: a small, cached snapshot of live market, DeFi and news data.

Every section is fetched independently; a section whose source fails is simply left out, so the
board shows whatever is available. The snapshot is cached per process for ``CACHE_TTL`` seconds,
which keeps keyless CoinGecko well inside its rate limit no matter how many visitors load the page.
"""
from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import http
from .tools import coingecko, defillama
from .tools.web import RSS_FEEDS, _rss

logger = logging.getLogger(__name__)

CACHE_TTL = 300
FEED_COINS = ("bitcoin", "ethereum", "solana")
FEED_PROTOCOLS = (("lido", "Lido"), ("aave-v3", "Aave V3"))
SPARK_POINTS = 48
SECTION_TIMEOUT = 20.0

_cache: Dict[str, Any] = {"at": 0.0, "data": None}
_lock = threading.Lock()


def _spark(prices: List[float], limit: int = SPARK_POINTS) -> List[float]:
    if len(prices) <= limit:
        return [round(p, 6) for p in prices]
    step = len(prices) / limit
    out = [prices[int(i * step)] for i in range(limit)]
    out[-1] = prices[-1]
    return [round(p, 6) for p in out]


async def _markets() -> Optional[List[Dict[str, Any]]]:
    data, err = await coingecko._get(f"{coingecko.BASE_URL}/coins/markets", {
        "vs_currency": "usd", "ids": ",".join(FEED_COINS), "sparkline": "true",
        "price_change_percentage": "24h,7d,30d",
    })
    if err or not isinstance(data, list):
        logger.info("Feed markets unavailable: %s", err)
        return None
    rows = []
    for c in data:
        if not isinstance(c, dict):
            continue
        rows.append({
            "id": c.get("id"), "symbol": str(c.get("symbol", "")).upper(), "name": c.get("name"),
            "price": c.get("current_price"),
            "change_24h": c.get("price_change_percentage_24h_in_currency", c.get("price_change_percentage_24h")),
            "change_7d": c.get("price_change_percentage_7d_in_currency"),
            "change_30d": c.get("price_change_percentage_30d_in_currency"),
            "sparkline_7d": _spark(((c.get("sparkline_in_7d") or {}).get("price") or [])),
        })
    order = {cid: i for i, cid in enumerate(FEED_COINS)}
    rows.sort(key=lambda r: order.get(r["id"], 99))
    return rows or None


async def _yields() -> Optional[List[Dict[str, Any]]]:
    section = await defillama._section_yields("stable", None)
    pools = section.get("top_pools") or []
    return [{k: p.get(k) for k in ("project", "chain", "symbol", "apy", "tvl_usd")} for p in pools[:5]] or None


async def _stablecoins() -> Optional[List[Dict[str, Any]]]:
    section = await defillama._section_stablecoins()
    assets = section.get("top_assets") or []
    return [{k: a.get(k) for k in ("symbol", "name", "circulating_usd")} for a in assets[:4]] or None


async def _volume(kind: str, chain: str) -> Optional[Dict[str, Any]]:
    section = await defillama._section_volume(kind, chain)
    if not section.get("top_protocols"):
        return None
    return {
        "chain": chain, "total24h": section.get("total24h"),
        "top": [{"name": p.get("name"), "total24h": p.get("total24h")} for p in section["top_protocols"][:5]],
    }


async def _protocol_tvl() -> Optional[List[Dict[str, Any]]]:
    async def one(slug: str, label: str) -> Optional[Dict[str, Any]]:
        value, err = await defillama._fetch(f"{defillama.API}/tvl/{slug}")
        if err or not isinstance(value, (int, float)):
            return None
        return {"slug": slug, "name": label, "tvl_usd": float(value)}

    rows = [r for r in await asyncio.gather(*(one(s, n) for s, n in FEED_PROTOCOLS)) if r]
    return rows or None


async def _news() -> Optional[List[Dict[str, Any]]]:
    feeds = await asyncio.gather(*(_rss(name, url) for name, url in RSS_FEEDS.items()))
    seen, items = set(), []
    for item in (i for feed in feeds for i in feed):
        key = re.sub(r"\W+", " ", item["title"].lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        items.append(item)
    items.sort(key=lambda i: i["published"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return [
        {**i, "published": i["published"].isoformat() if i["published"] else None, "summary": (i["summary"] or "")[:200]}
        for i in items[:6]
    ] or None


async def build_feed() -> Dict[str, Any]:
    jobs = {
        "markets": _markets(),
        "yields": _yields(),
        "stablecoins": _stablecoins(),
        "dex": _volume("dexs", "Arbitrum"),
        "fees": _volume("fees", "Arbitrum"),
        "protocols": _protocol_tvl(),
        "news": _news(),
    }
    async with http.client_scope():
        results = await asyncio.gather(
            *(asyncio.wait_for(job, SECTION_TIMEOUT) for job in jobs.values()), return_exceptions=True,
        )
    feed: Dict[str, Any] = {}
    for name, result in zip(jobs, results):
        if isinstance(result, BaseException):
            logger.info("Feed section %s failed: %s", name, type(result).__name__)
        elif result:
            feed[name] = result
    return feed


def get_feed(now: Optional[float] = None) -> Dict[str, Any]:
    """Cached snapshot. Only one thread rebuilds it at a time; the others wait and reuse it."""
    now = time.time() if now is None else now
    with _lock:
        if _cache["data"] is not None and now - _cache["at"] < CACHE_TTL:
            return _cache["data"]
        data = asyncio.run(build_feed())
        snapshot = {"generated_at": datetime.now(timezone.utc).isoformat(), "sections": data}
        # An empty build (all sources down) is not cached, so the next request retries.
        if data:
            _cache.update(at=now, data=snapshot)
        return snapshot
