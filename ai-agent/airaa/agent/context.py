"""Render merged tool data as the text the synthesis model sees.

Everything here is generated from the data actually fetched for this request. Values are printed
with full precision so the model can quote them exactly.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..schemas import Plan, ResearchRequest
from ..utils.format import fmt_money, fmt_num, fmt_pct

_MAX_JSON_CHARS = 1500


def _market_lines(rows: List[Dict[str, Any]]) -> List[str]:
    lines = ["MARKET DATA (CoinMarketCap):"]
    for r in rows:
        rank = f"#{int(r['rank'])}" if isinstance(r.get("rank"), (int, float)) else "N/A"
        lines.append(
            f"- {r.get('name') or r.get('symbol')} ({r.get('symbol')}): price {fmt_money(r.get('price'), 8)}; "
            f"24h {fmt_pct(r.get('percent_change_24h'))}; 7d {fmt_pct(r.get('percent_change_7d'))}; "
            f"30d {fmt_pct(r.get('percent_change_30d'))}; market cap {fmt_money(r.get('market_cap'), 0)}; "
            f"24h volume {fmt_money(r.get('volume_24h'), 0)}; rank {rank}; "
            f"circulating supply {fmt_num(r.get('circulating_supply'), 2)}; max supply {fmt_num(r.get('max_supply'), 2)}; "
            f"updated {r.get('last_updated') or 'N/A'}"
        )
    return lines


def _age_days(timestamp: Optional[str]) -> Optional[float]:
    try:
        then = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - then).total_seconds() / 86400


def _dex_lines(d: Dict[str, Any]) -> List[str]:
    age = _age_days(d.get("as_of"))
    freshness = ""
    if d.get("as_of"):
        freshness = f" [data computed {d['as_of']}"
        freshness += f", {age:.0f} days ago: STALE, say so and do not call these 'current' or '24h']" if age is not None and age > 3 else "]"
    lines = [
        f"DEX TRADING PAIRS (Dune{', ' + d['chain'] if d.get('chain') else ''}){freshness}: {d.get('total_pairs', 0)} pairs; total 24h volume {fmt_money(d.get('total_24h_volume'), 0)}; "
        f"7d volume {fmt_money(d.get('total_7d_volume'), 0)}; liquidity {fmt_money(d.get('total_liquidity'), 0)}"
    ]
    for i, p in enumerate(d.get("top_pairs", [])[:5], 1):
        lines.append(
            f"  {i}. {p.get('token_pair', 'Unknown')}: 24h {fmt_money(p.get('one_day_volume'), 0)}, "
            f"7d {fmt_money(p.get('seven_day_volume'), 0)}, liquidity {fmt_money(p.get('usd_liquidity'), 0)}"
        )
    return lines


def _defillama_lines(key: str, item: Dict[str, Any]) -> List[str]:
    kind = item.get("type")
    if kind == "tvl_overview":
        lines = [f"CHAIN TVL (DefiLlama): {item.get('chains_count')} chains tracked"]
        if item.get("requested_chain"):
            c = item["requested_chain"]
            lines.append(f"- Requested chain {c['name']}: {fmt_money(c['tvl_usd'], 0)}")
        lines += [f"- {c['name']}: {fmt_money(c['tvl_usd'], 0)}" for c in item.get("top_chains", [])[:8]]
        return lines
    if kind == "stablecoins_overview":
        return ["STABLECOINS (DefiLlama), by circulating supply:"] + [
            f"- {a.get('symbol') or a.get('name')}: {fmt_money(a.get('circulating_usd'), 0)}" for a in item.get("top_assets", [])[:8]
        ]
    if kind in ("dex_overview", "fees_overview"):
        label = "DEX VOLUME" if kind == "dex_overview" else "FEES"
        scope = f" on {item['chain']}" if item.get("chain") else ""
        lines = [
            f"{label}{scope} (DefiLlama): 24h {fmt_money(item.get('total24h'), 0)} ({fmt_pct(item.get('change_1d'))} d/d); "
            f"7d {fmt_money(item.get('total7d'), 0)} ({fmt_pct(item.get('change_7d'))} w/w)"
        ]
        lines += [
            f"- {p.get('name')}: 24h {fmt_money(p.get('total24h'), 0)} ({fmt_pct(p.get('change_1d'))})"
            for p in item.get("top_protocols", [])[:8]
        ]
        return lines
    if kind == "yields_overview":
        f = item.get("filters", {})
        scope = ", ".join(x for x in (f.get("chain"), "stablecoin pools" if f.get("stablecoins_only") else None) if x)
        lines = [f"TOP YIELDS (DefiLlama; pools with TVL >= {fmt_money(f.get('min_tvl_usd'), 0)}{'; ' + scope if scope else ''}):"]
        lines += [
            f"- {y.get('project')} {y.get('symbol')} on {y.get('chain')}: {y.get('apy'):.2f}% APY, TVL {fmt_money(y.get('tvl_usd'), 0)}"
            for y in item.get("top_pools", [])[:10]
        ]
        return lines
    if kind == "bridges_overview":
        return ["BRIDGES (DefiLlama), by last daily volume:"] + [
            f"- {b.get('name')}: {fmt_money(b.get('last_daily_volume'), 0)} (weekly {fmt_money(b.get('weekly_volume'), 0)})"
            for b in item.get("top_bridges", [])[:8]
        ]
    if kind == "protocol_tvl":
        chains = ", ".join(f"{k} {fmt_money(v, 0)}" for k, v in (item.get("current_chain_tvls") or {}).items())
        line = (
            f"PROTOCOL {item.get('name')} ({item.get('category')}; DefiLlama): TVL {fmt_money(item.get('tvl_usd'), 0)}; "
            f"7d change {fmt_pct(item.get('tvl_change_7d_pct'))}; market cap {fmt_money(item.get('mcap'), 0)}; "
            f"chains: {', '.join(item.get('chains') or []) or 'N/A'}"
        )
        extras = [line]
        if chains:
            extras.append(f"  TVL by chain/segment: {chains}")
        if item.get("fees_24h") is not None:
            extras.append(f"  Fees: 24h {fmt_money(item.get('fees_24h'), 0)}; 7d {fmt_money(item.get('fees_7d'), 0)}; 30d {fmt_money(item.get('fees_30d'), 0)}")
        return extras
    if kind == "chain_tvl_history":
        return [
            f"{item.get('chain')} TVL HISTORY (DefiLlama, last {len(item.get('points', []))} days): latest "
            f"{fmt_money(item.get('latest_tvl_usd'), 0)}; change over window {fmt_pct(item.get('change_pct_over_window'))}"
        ]
    if kind == "prices":
        return ["PRICES (DefiLlama): " + json.dumps(item.get("coins"), default=str)[:_MAX_JSON_CHARS]]
    return [f"{key.upper()} (DefiLlama): " + json.dumps(item, default=str)[:_MAX_JSON_CHARS]]


def _wallet_lines(sup: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    if "wallet_balance" in sup:
        w = sup["wallet_balance"]
        lines.append(f"WALLET (Etherscan, {w.get('chain')}): {w.get('address')} balance {w.get('balance_native'):.6f} (native token)")
    if "transactions" in sup:
        t = sup["transactions"]
        lines.append(f"RECENT TRANSACTIONS (Etherscan, {t.get('chain')}): showing {len(t['transactions'])} of the latest {t.get('total_count')}")
        lines += [
            f"- {x.get('timeStamp')}: {x.get('from')} -> {x.get('to')}, {x.get('value_native')} native{' (failed)' if x.get('failed') else ''}"
            for x in t["transactions"][:5]
        ]
    if "token_transfers" in sup:
        t = sup["token_transfers"]
        lines.append(f"TOKEN TRANSFERS (Etherscan, {t.get('chain')}): latest {t.get('total_count')}")
        lines += [f"- {x.get('timeStamp')}: {x.get('value')} raw units of {x.get('tokenSymbol')} {x.get('from')} -> {x.get('to')}" for x in t["transfers"][:5]]
    return lines


def build_context(request: ResearchRequest, plan: Plan, merged: Dict[str, Any]) -> str:
    """The user-turn text sent to the synthesis model (question + verified data + gaps)."""
    primary, sup, meta = merged["primary_data"], merged["supplementary_data"], merged["metadata"]
    parts = [f"QUESTION: {request.query}", f"INTENT: {plan.intent}", f"TIME RANGE REQUESTED: {request.time_range}"]
    if request.address:
        parts.append(f"WALLET ADDRESS PROVIDED BY USER: {request.address}")

    parts.append("\n=== VERIFIED DATA (the only facts you may use) ===")
    blocks: List[str] = []

    market_rows = [v for v in primary.values() if isinstance(v, dict) and v.get("type") == "market_data"]
    if market_rows:
        blocks.append("\n".join(_market_lines(market_rows)))
    if isinstance(primary.get("dex_trading"), dict):
        blocks.append("\n".join(_dex_lines(primary["dex_trading"])))
    if isinstance(sup.get("global_metrics"), dict):
        g = sup["global_metrics"]
        blocks.append(
            f"GLOBAL MARKET (CoinMarketCap): total cap {fmt_money(g.get('total_market_cap'), 0)}; 24h volume "
            f"{fmt_money(g.get('total_volume_24h'), 0)}; BTC dominance {fmt_num(g.get('bitcoin_dominance'), 2)}%; "
            f"ETH dominance {fmt_num(g.get('ethereum_dominance'), 2)}%"
        )
    for key, item in sup.items():
        if isinstance(item, dict) and (key.startswith(("defillama", "protocol_", "chain_tvl_history"))):
            blocks.append("\n".join(_defillama_lines(key, item)))
    wallet = _wallet_lines(sup)
    if wallet:
        blocks.append("\n".join(wallet))
    if isinstance(sup.get("blockchain_analytics"), dict):
        blocks.append("ON-CHAIN ANALYTICS (Dune): " + json.dumps(sup["blockchain_analytics"].get("data"), default=str)[:_MAX_JSON_CHARS])

    parts.append("\n\n".join(blocks) if blocks else "(no data was retrieved)")

    failed = meta.get("failed_sources", [])
    parts.append("\n=== UNAVAILABLE SOURCES ===")
    parts.append("\n".join(f"- {f['source']}: {f['error']}" for f in failed) if failed else "(none)")
    parts.append(f"\nSources that responded: {', '.join(meta.get('sources_used', [])) or 'none'}")
    return "\n".join(parts)


def plain_summary(request: ResearchRequest, plan: Plan, merged: Dict[str, Any]) -> str:
    """Readable data-only answer used when the language model is unavailable."""
    context = build_context(request, plan, merged)
    body = context.split("=== VERIFIED DATA (the only facts you may use) ===", 1)[-1].split("=== UNAVAILABLE SOURCES ===")[0]
    return (
        "The AI summary is temporarily unavailable, so here is the data I retrieved for your question:\n\n"
        + body.strip()
    )
