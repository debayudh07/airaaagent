"""Turn merged tool data into chart specs the frontend renders (recharts).

Charts are built deterministically from the data actually fetched, never by the language model,
so every plotted point is a real value. Spec shape::

    {
      "id": "price-ETH", "kind": "line" | "area" | "bar", "title": "...", "subtitle": "CoinGecko · 30 days",
      "x_key": "x", "series": [{"key": "ETH", "label": "ETH"}],
      "data": [{"x": "2026-09-03", "ETH": 2512.3}, ...],
      "y_format": "usd" | "percent" | "number"
    }
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from ..schemas import Plan

Chart = Dict[str, Any]
MAX_BARS = 10


def _day(ts: float, ms: bool, hourly: bool = False) -> str:
    dt = datetime.fromtimestamp(ts / 1000 if ms else ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:00" if hourly else "%Y-%m-%d")


def _num(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bar(chart_id: str, title: str, subtitle: str, rows: List[tuple], y_format: str, label: str) -> Optional[Chart]:
    rows = [(str(name), v) for name, v in rows if name and v is not None][:MAX_BARS]
    if len(rows) < 2:
        return None
    return {
        "id": chart_id, "kind": "bar", "title": title, "subtitle": subtitle, "x_key": "x",
        "series": [{"key": "value", "label": label}],
        "data": [{"x": name, "value": round(v, 4)} for name, v in rows], "y_format": y_format,
    }


# ----------------------------------------------------------------- builders
def _price_history(merged: Dict[str, Any], plan: Plan) -> Optional[Chart]:
    hist = merged["supplementary_data"].get("price_history")
    if not hist or not hist.get("series"):
        return None
    series: Dict[str, List[List[float]]] = hist["series"]
    days = hist.get("days") or 30
    hourly = days <= 2
    window = f"last {days} day{'s' if days != 1 else ''}"

    if len(series) == 1:
        symbol, points = next(iter(series.items()))
        data = [{"x": _day(t, ms=True, hourly=hourly), symbol: round(p, 8)} for t, p in points]
        return {"id": f"price-{symbol}", "kind": "area", "title": f"{symbol} price (USD)", "subtitle": f"CoinGecko · {window}",
                "x_key": "x", "series": [{"key": symbol, "label": symbol}], "data": data, "y_format": "usd"}

    # Several coins: plot % change from the start of the window so different price scales compare.
    by_x: Dict[str, Dict[str, Any]] = {}
    for symbol, points in series.items():
        if not points or not points[0][1]:
            continue
        base = points[0][1]
        for t, p in points:
            row = by_x.setdefault(_day(t, ms=True, hourly=hourly), {})
            row[symbol] = round((p / base - 1) * 100, 2)
    data = [{"x": x, **vals} for x, vals in sorted(by_x.items())]
    return {"id": "performance", "kind": "line", "title": "Price performance (% change)", "subtitle": f"CoinGecko · {window}",
            "x_key": "x", "series": [{"key": s, "label": s} for s in series], "data": data, "y_format": "percent"}


def _protocol_tvl(merged: Dict[str, Any], plan: Plan) -> Optional[Chart]:
    protocols = [v for k, v in merged["supplementary_data"].items() if k.startswith("protocol_") and v.get("tvl_history")]
    if not protocols:
        return None
    by_x: Dict[str, Dict[str, Any]] = {}
    for p in protocols[:4]:
        name = p.get("name") or p.get("slug")
        for t, v in p["tvl_history"]:
            by_x.setdefault(_day(t, ms=False), {})[name] = v
    data = [{"x": x, **vals} for x, vals in sorted(by_x.items())]
    names = [p.get("name") or p.get("slug") for p in protocols[:4]]
    return {"id": "protocol-tvl", "kind": "area" if len(names) == 1 else "line",
            "title": f"{names[0]} TVL" if len(names) == 1 else "Protocol TVL", "subtitle": "DefiLlama · last 12 months",
            "x_key": "x", "series": [{"key": n, "label": n} for n in names], "data": data, "y_format": "usd"}


def _chain_tvl(merged: Dict[str, Any], plan: Plan) -> Optional[Chart]:
    hist = next((v for k, v in merged["supplementary_data"].items() if k.startswith("chain_tvl_history")), None)
    if not hist or not hist.get("points"):
        return None
    data = [{"x": _day(p["date"], ms=False), "tvl": p.get("tvl")} for p in hist["points"] if "date" in p]
    return {"id": f"chain-tvl-{hist.get('chain')}", "kind": "area", "title": f"{hist.get('chain')} TVL",
            "subtitle": f"DefiLlama · last {len(data)} days", "x_key": "x",
            "series": [{"key": "tvl", "label": "TVL"}], "data": data, "y_format": "usd"}


def _market_caps(merged: Dict[str, Any], plan: Plan) -> Optional[Chart]:
    rows = [v for v in merged["primary_data"].values() if v.get("type") == "market_data" and _num(v.get("market_cap"))]
    wanted = set(plan.entities.symbols)
    if wanted:
        rows = [r for r in rows if r.get("symbol") in wanted]
    elif plan.intent != "comparison":
        return None
    rows.sort(key=lambda r: _num(r["market_cap"]) or 0, reverse=True)
    return _bar("market-caps", "Market capitalisation", "USD", [(r["symbol"], _num(r["market_cap"])) for r in rows], "usd", "Market cap")


def _yields(merged: Dict[str, Any], plan: Plan) -> Optional[Chart]:
    y = merged["supplementary_data"].get("defillama_yields")
    if not y:
        return None
    rows = [(f"{p.get('project')} {p.get('symbol')}"[:28], _num(p.get("apy"))) for p in y.get("top_pools", [])]
    return _bar("yields", "Top yields (APY %)", "DefiLlama · pools ≥ $5M TVL", rows, "percent", "APY")


def _dex_volume(merged: Dict[str, Any], plan: Plan) -> Optional[Chart]:
    d = merged["supplementary_data"].get("defillama_dex")
    if not d:
        return None
    rows = [(p.get("name"), _num(p.get("total24h"))) for p in d.get("top_protocols", [])]
    scope = f" on {d['chain']}" if d.get("chain") else ""
    return _bar("dex-volume", f"DEX volume by protocol, 24h{scope}", "DefiLlama", rows, "usd", "24h volume")


def _fees(merged: Dict[str, Any], plan: Plan) -> Optional[Chart]:
    d = merged["supplementary_data"].get("defillama_fees")
    if not d:
        return None
    rows = [(p.get("name"), _num(p.get("total24h"))) for p in d.get("top_protocols", [])]
    return _bar("fees", "Fees by protocol, 24h", "DefiLlama", rows, "usd", "24h fees")


def _chain_tvl_bars(merged: Dict[str, Any], plan: Plan) -> Optional[Chart]:
    t = merged["supplementary_data"].get("defillama_tvl")
    if not t:
        return None
    return _bar("tvl-by-chain", "TVL by chain", "DefiLlama", [(c.get("name"), _num(c.get("tvl_usd"))) for c in t.get("top_chains", [])], "usd", "TVL")


def _stablecoins(merged: Dict[str, Any], plan: Plan) -> Optional[Chart]:
    s = merged["supplementary_data"].get("defillama_stablecoins")
    if not s:
        return None
    rows = [(a.get("symbol") or a.get("name"), _num(a.get("circulating_usd"))) for a in s.get("top_assets", [])]
    return _bar("stablecoins", "Stablecoin supply", "DefiLlama · circulating USD", rows, "usd", "Circulating")


def _fear_greed(merged: Dict[str, Any], plan: Plan) -> Optional[Chart]:
    fg = merged["supplementary_data"].get("fear_greed")
    if not fg or len(fg.get("last_7_days", [])) < 2:
        return None
    data = [{"x": _day(int(r["timestamp"]), ms=False), "value": r["value"]} for r in reversed(fg["last_7_days"])]
    return {"id": "fear-greed", "kind": "line", "title": "Crypto Fear & Greed index", "subtitle": "alternative.me · 0 = extreme fear, 100 = extreme greed",
            "x_key": "x", "series": [{"key": "value", "label": "Index"}], "data": data, "y_format": "number"}


# Order = priority when more charts are possible than ``max_charts``.
_BUILDERS: List[Callable[[Dict[str, Any], Plan], Optional[Chart]]] = [
    _price_history, _protocol_tvl, _chain_tvl, _market_caps, _yields, _dex_volume,
    _fees, _chain_tvl_bars, _stablecoins, _fear_greed,
]


def build_charts(merged: Dict[str, Any], plan: Plan, max_charts: int = 3) -> List[Chart]:
    charts: List[Chart] = []
    for builder in _BUILDERS:
        if len(charts) >= max_charts:
            break
        try:
            chart = builder(merged, plan)
        except Exception:  # a malformed upstream row must not cost the user the answer
            chart = None
        if chart and chart["data"]:
            charts.append(chart)
    return charts
