"""DefiLlama: TVL, protocols, stablecoins, yields, DEX volume, fees and bridges (no API key needed)."""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx
from langchain_core.tools import tool

from .. import http
from ..utils.assets import KNOWN_PROTOCOLS, extract_chain, extract_symbols, to_coingecko_ids

logger = logging.getLogger(__name__)

API = "https://api.llama.fi"
COINS = "https://coins.llama.fi"
YIELDS = "https://yields.llama.fi"
STABLES = "https://stablecoins.llama.fi"
BRIDGES = "https://bridges.llama.fi"

SOURCE = "defillama"
_SLUG = re.compile(r"^[a-z0-9][a-z0-9.\-]{0,60}$")
_OVERVIEW_PARAMS = {"excludeTotalDataChart": "true", "excludeTotalDataChartBreakdown": "true"}

# Which sections of the overview to fetch, keyed by words in the question.
_SECTION_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "tvl": ("tvl", "total value locked", "chains"),
    "stablecoins": ("stablecoin",),
    "dex": ("dex", "volume", "swap"),
    "fees": ("fees", "revenue"),
    "yields": ("yield", "apy", "lending", "borrow", "farm"),
    "bridges": ("bridge",),
}
_DEFAULT_SECTIONS = ("tvl", "dex", "fees")
MIN_YIELD_TVL_USD = 5_000_000


def _ok(data: Any, endpoint: str, **meta: Any) -> Dict[str, Any]:
    return {"success": True, "data": data, "metadata": {"endpoint": endpoint, **meta}, "source": SOURCE}


def _err(message: str) -> Dict[str, Any]:
    return {"success": False, "error": message, "source": SOURCE}


async def _fetch(url: str, params: Optional[Dict[str, str]] = None) -> Tuple[Any, Optional[str]]:
    """GET + decode. Returns ``(json, None)`` or ``(None, error message)``."""
    try:
        response = await http.get(url, params=params)
    except httpx.HTTPError as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if response.status_code != 200:
        return None, f"HTTP {response.status_code}"
    try:
        return response.json(), None
    except ValueError:
        return None, "Invalid JSON from DefiLlama"


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _wanted_sections(q: str) -> List[str]:
    wanted = [name for name, words in _SECTION_KEYWORDS.items() if any(w in q for w in words)]
    return wanted or list(_DEFAULT_SECTIONS)


# ---------------------------------------------------------------- sections
async def _section_tvl(chain: Optional[str]) -> Dict[str, Any]:
    data, err = await _fetch(f"{API}/v2/chains")
    if err or not isinstance(data, list):
        return {}
    rows = [
        {"name": c.get("name"), "tvl_usd": _number(c.get("tvl"))}
        for c in data if isinstance(c, dict)
    ]
    rows.sort(key=lambda r: r["tvl_usd"], reverse=True)
    out: Dict[str, Any] = {"type": "tvl_overview", "chains_count": len(rows), "top_chains": rows[:10]}
    if chain:
        match = next((r for r in rows if (r["name"] or "").lower() == chain.lower()), None)
        if match:
            out["requested_chain"] = match
    return out


async def _section_stablecoins() -> Dict[str, Any]:
    data, err = await _fetch(f"{STABLES}/stablecoins", {"includePrices": "false"})
    if err or not isinstance(data, dict):
        return {}
    assets = data.get("peggedAssets") or []
    rows = [
        {
            "name": a.get("name"),
            "symbol": a.get("symbol"),
            "circulating_usd": _number((a.get("circulating") or {}).get("peggedUSD")),
        }
        for a in assets if isinstance(a, dict)
    ]
    rows.sort(key=lambda r: r["circulating_usd"], reverse=True)
    return {"type": "stablecoins_overview", "assets_count": len(rows), "top_assets": rows[:10]}


async def _section_volume(kind: str, chain: Optional[str]) -> Dict[str, Any]:
    """DEX volume (``kind='dexs'``) or fees/revenue (``kind='fees'``) overview."""
    path = f"{API}/overview/{kind}" + (f"/{chain}" if chain else "")
    data, err = await _fetch(path, _OVERVIEW_PARAMS)
    if err or not isinstance(data, dict):
        return {}
    protocols = [p for p in (data.get("protocols") or []) if isinstance(p, dict)]
    protocols.sort(key=lambda p: _number(p.get("total24h")), reverse=True)
    top = [
        {
            "name": p.get("name"),
            "total24h": p.get("total24h"),
            "total7d": p.get("total7d"),
            "change_1d": p.get("change_1d"),
            "change_7d": p.get("change_7d"),
        }
        for p in protocols[:10]
    ]
    return {
        "type": "dex_overview" if kind == "dexs" else "fees_overview",
        "chain": chain,
        "protocols_count": len(protocols),
        "total24h": data.get("total24h"),
        "total7d": data.get("total7d"),
        "change_1d": data.get("change_1d"),
        "change_7d": data.get("change_7d"),
        "top_protocols": top,
    }


async def _section_yields(q: str, chain: Optional[str]) -> Dict[str, Any]:
    data, err = await _fetch(f"{YIELDS}/pools")
    if err or not isinstance(data, dict):
        return {}
    pools = [p for p in (data.get("data") or []) if isinstance(p, dict)]
    stable_only = "stable" in q
    rows = []
    for p in pools:
        apy, tvl = _number(p.get("apy")), _number(p.get("tvlUsd"))
        # Skip small pools, absurd APYs and pools DefiLlama itself flags as outliers: these are
        # almost always short-lived incentive artefacts, not yields a user could rely on.
        if tvl < MIN_YIELD_TVL_USD or apy <= 0 or apy > 1000 or p.get("outlier"):
            continue
        if chain and (p.get("chain") or "").lower() != chain.lower():
            continue
        if stable_only and not p.get("stablecoin"):
            continue
        rows.append({
            "project": p.get("project"), "chain": p.get("chain"), "symbol": p.get("symbol"),
            "apy": round(apy, 2), "tvl_usd": round(tvl), "il_risk": p.get("ilRisk"),
        })
    rows.sort(key=lambda r: r["apy"], reverse=True)
    return {
        "type": "yields_overview",
        "pools_count": len(pools),
        "filters": {"chain": chain, "stablecoins_only": stable_only, "min_tvl_usd": MIN_YIELD_TVL_USD},
        "top_pools": rows[:10],
    }


async def _section_bridges() -> Dict[str, Any]:
    data, err = await _fetch(f"{BRIDGES}/bridges", {"includeChains": "false"})
    if err or not isinstance(data, dict):
        return {}
    bridges = [b for b in (data.get("bridges") or []) if isinstance(b, dict)]
    bridges.sort(key=lambda b: _number(b.get("lastDailyVolume")), reverse=True)
    top = [
        {"name": b.get("displayName") or b.get("name"), "last_daily_volume": b.get("lastDailyVolume"),
         "weekly_volume": b.get("weeklyVolume"), "monthly_volume": b.get("monthlyVolume")}
        for b in bridges[:10]
    ]
    return {"type": "bridges_overview", "bridges_count": len(bridges), "top_bridges": top}


async def _overview(q: str, chain: Optional[str]) -> Dict[str, Any]:
    sections = _wanted_sections(q)
    jobs = {
        "tvl": lambda: _section_tvl(chain),
        "stablecoins": _section_stablecoins,
        "dex": lambda: _section_volume("dexs", chain),
        "fees": lambda: _section_volume("fees", chain),
        "yields": lambda: _section_yields(q, chain),
        "bridges": _section_bridges,
    }
    results = await asyncio.gather(*(jobs[s]() for s in sections), return_exceptions=True)
    bundle: Dict[str, Any] = {"aggregate": True}
    for name, res in zip(sections, results):
        bundle[name] = res if isinstance(res, dict) else {}
    if not any(bundle[s] for s in sections):
        return _err("DefiLlama returned no data for the requested sections")
    return _ok(bundle, "aggregate", chain=chain, sections=sections)


# ---------------------------------------------------------------- specific routes
async def _protocol(slug: str, q: str) -> Dict[str, Any]:
    if not _SLUG.match(slug):
        return _err(f"Invalid protocol slug: {slug!r}")
    want_fees = any(w in q for w in ("fee", "revenue"))
    detail_task = _fetch(f"{API}/protocol/{slug}")
    fees_task = _fetch(f"{API}/summary/fees/{slug}", {"dataType": "dailyFees"}) if want_fees else asyncio.sleep(0, (None, None))
    (detail, err), (fees, _) = await asyncio.gather(detail_task, fees_task)
    if err or not isinstance(detail, dict):
        return _err(f"Protocol '{slug}': {err or 'unexpected response'}")

    series = [p for p in (detail.get("tvl") or []) if isinstance(p, dict)]
    latest = _number(series[-1].get("totalLiquidityUSD")) if series else None
    week_ago = _number(series[-8].get("totalLiquidityUSD")) if len(series) > 7 else None
    chain_tvls = detail.get("currentChainTvls") or {}
    top_chain_tvls = dict(sorted(chain_tvls.items(), key=lambda kv: _number(kv[1]), reverse=True)[:8])

    summary: Dict[str, Any] = {
        "type": "protocol_tvl",
        "slug": slug,
        "name": detail.get("name"),
        "symbol": detail.get("symbol"),
        "category": detail.get("category"),
        "chains": (detail.get("chains") or [])[:12],
        "url": detail.get("url"),
        "description": (detail.get("description") or "")[:300],
        "tvl_usd": latest,
        "tvl_7d_ago_usd": week_ago,
        "tvl_change_7d_pct": round((latest - week_ago) / week_ago * 100, 2) if latest and week_ago else None,
        "current_chain_tvls": top_chain_tvls,
        "mcap": detail.get("mcap"),
        # last ~year, at most 120 points: enough for a chart without bloating the response
        "tvl_history": [[int(p["date"]), round(_number(p.get("totalLiquidityUSD")))] for p in series[-365:][::max(1, len(series[-365:]) // 120)] if "date" in p],
    }
    if isinstance(fees, dict):
        summary.update({
            "fees_24h": fees.get("total24h"), "fees_7d": fees.get("total7d"), "fees_30d": fees.get("total30d"),
        })
    return _ok(summary, "/protocol/{protocol}", protocol=slug)


async def _chain_history(chain: str) -> Dict[str, Any]:
    data, err = await _fetch(f"{API}/v2/historicalChainTvl/{chain}")
    if err or not isinstance(data, list) or not data:
        return _err(f"Chain history for {chain}: {err or 'empty'}")
    recent = data[-30:]
    first, last = _number(recent[0].get("tvl")), _number(recent[-1].get("tvl"))
    return _ok(
        {
            "type": "chain_tvl_history",
            "chain": chain,
            "points": recent,
            "latest_tvl_usd": last,
            "change_pct_over_window": round((last - first) / first * 100, 2) if first else None,
        },
        "/v2/historicalChainTvl/{chain}",
        chain=chain,
    )


async def _prices(symbols: List[str]) -> Dict[str, Any]:
    ids = to_coingecko_ids(symbols)
    if not ids:
        return _err("No supported tokens to price on DefiLlama")
    data, err = await _fetch(f"{COINS}/prices/current/{','.join(ids)}")
    if err or not isinstance(data, dict):
        return _err(f"Prices: {err or 'unexpected response'}")
    return _ok(data, "/prices/current/{coins}", coins=ids)


# ---------------------------------------------------------------- tool
@tool
async def defillama_tool(
    query: str,
    protocols: Optional[List[str]] = None,
    chain: Optional[str] = None,
    symbols: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Get DeFi ecosystem data from DefiLlama (no API key required).

    Covers protocol TVL, chain TVL, stablecoin supply, yield/APY pools, DEX volume,
    fees/revenue and bridge volume.

    Args:
        query: The user's question; used to decide which sections to fetch.
        protocols: DefiLlama protocol slugs (e.g. "aave", "uniswap", "lido") for protocol-level detail.
        chain: Blockchain to focus on (e.g. "Ethereum", "Arbitrum").
        symbols: Token tickers, only used for price lookups.
    """
    try:
        q = (query or "").lower()
        chain = chain or extract_chain(q)

        slugs = [p.strip().lower() for p in (protocols or []) if p and p.strip()]
        if not slugs:
            slugs = [p for p in KNOWN_PROTOCOLS if re.search(rf"\b{re.escape(p)}\b", q)]
        if slugs:
            slugs = list(dict.fromkeys(slugs))[:4]
            results = await asyncio.gather(*(_protocol(s, q) for s in slugs))
            good = [r["data"] for r in results if r.get("success")]
            if not good:
                return results[0]
            if len(good) == 1:
                return next(r for r in results if r.get("success"))
            return _ok({"type": "protocol_tvl_list", "protocols": good}, "/protocol/{protocol}", protocols=slugs)

        if chain and "tvl" in q and any(w in q for w in ("history", "historical", "trend", "over time", "chart")):
            return await _chain_history(chain)

        if "price" in q and not any(any(w in q for w in words) for words in _SECTION_KEYWORDS.values()):
            return await _prices(symbols or extract_symbols(q))

        return await _overview(q, chain)
    except Exception as exc:  # a tool must never raise into the agent loop
        logger.exception("defillama_tool failed")
        return _err(str(exc))
