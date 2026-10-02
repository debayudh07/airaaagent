"""Merge tool outputs into one structure: ``primary_data`` (assets, DEX pairs), ``supplementary_data``
(everything else) and ``metadata``.

``completeness_score`` is the percentage of attempted sources that returned data. It says how much of
the plan succeeded, not how good the answer is.
"""
from __future__ import annotations

from typing import Any, Dict, List

_DEFILLAMA_SECTIONS = {
    "tvl": "defillama_tvl",
    "stablecoins": "defillama_stablecoins",
    "dex": "defillama_dex",
    "fees": "defillama_fees",
    "yields": "defillama_yields",
    "bridges": "defillama_bridges",
}
_WEI = 10 ** 18


def new_merged() -> Dict[str, Any]:
    return {
        "primary_data": {},
        "supplementary_data": {},
        "metadata": {
            "sources_used": [],
            "failed_sources": [],
            "tools_attempted": 0,
            "tools_succeeded": 0,
            "completeness_score": 0.0,
            "data_quality": "none",
            "conflicts": [],
        },
    }


def merge_results(results: List[Dict[str, Any]], merged: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Fold ``results`` into ``merged`` (a fresh structure by default) and recompute the score.

    Passing an existing ``merged`` lets a follow-up round add to the first round's data.
    """
    merged = merged or new_merged()
    meta = merged["metadata"]

    for result in results:
        if not isinstance(result, dict):
            continue
        meta["tools_attempted"] += 1
        source = result.get("source", "unknown")
        if not result.get("success"):
            meta["failed_sources"].append({
                "source": source,
                "tool": result.get("tool"),
                "error": str(result.get("error", "unknown error")),
            })
            continue

        meta["tools_succeeded"] += 1
        if source not in meta["sources_used"]:
            meta["sources_used"].append(source)
        data, info = result.get("data"), result.get("metadata") or {}

        if source == "coinmarketcap":
            _merge_coinmarketcap(merged, data)
        elif source == "dune_analytics":
            _merge_dune(merged, data, source, info)
        elif source == "etherscan":
            _merge_etherscan(merged, data, info)
        elif source == "defillama":
            _merge_defillama(merged, data, info)
        elif source == "coingecko":
            _merge_coingecko(merged, data)
        elif source == "dexscreener":
            merged["supplementary_data"]["dex_screener"] = {"type": "dex_screener", **(data or {})}
        elif source == "news":
            merged["supplementary_data"]["news"] = {"type": "news", **(data or {})}
        elif source == "web_search":
            merged["supplementary_data"]["web_results"] = {"type": "web_results", **(data or {})}
        elif source == "web_pages":
            merged["supplementary_data"]["web_pages"] = {"type": "web_pages", **(data or {})}

    attempted, ok = meta["tools_attempted"], meta["tools_succeeded"]
    meta["completeness_score"] = round(100.0 * ok / attempted, 1) if attempted else 0.0
    meta["data_quality"] = "high" if attempted and ok == attempted else "partial" if ok else "none"
    return merged


# ------------------------------------------------------------------ CoinMarketCap
def _market_row(crypto: Dict[str, Any], fallback_symbol: str) -> Dict[str, Any]:
    usd = (crypto.get("quote") or {}).get("USD") or {}
    return {
        "type": "market_data",
        "name": crypto.get("name"),
        "symbol": crypto.get("symbol") or fallback_symbol,
        "cmc_id": crypto.get("id"),
        "rank": crypto.get("cmc_rank"),
        "price": usd.get("price"),
        "market_cap": usd.get("market_cap"),
        "volume_24h": usd.get("volume_24h"),
        "percent_change_1h": usd.get("percent_change_1h"),
        "percent_change_24h": usd.get("percent_change_24h"),
        "percent_change_7d": usd.get("percent_change_7d"),
        "percent_change_30d": usd.get("percent_change_30d"),
        "circulating_supply": crypto.get("circulating_supply"),
        "total_supply": crypto.get("total_supply"),
        "max_supply": crypto.get("max_supply"),
        "last_updated": usd.get("last_updated") or crypto.get("last_updated"),
        "source": "coinmarketcap",
    }


def _merge_coinmarketcap(merged: Dict[str, Any], data: Any) -> None:
    payload = data.get("data") if isinstance(data, dict) else None
    if payload is None:
        return
    primary, supplementary = merged["primary_data"], merged["supplementary_data"]

    if isinstance(payload, list):  # listings/latest
        for crypto in payload:
            if isinstance(crypto, dict):
                row = _market_row(crypto, "UNKNOWN")
                primary[f"market_{row['symbol']}"] = row
    elif isinstance(payload, dict) and "active_cryptocurrencies" in payload:  # global metrics
        usd = (payload.get("quote") or {}).get("USD") or {}
        supplementary["global_metrics"] = {
            "type": "global_metrics",
            "total_market_cap": usd.get("total_market_cap"),
            "total_volume_24h": usd.get("total_volume_24h"),
            "bitcoin_dominance": payload.get("btc_dominance"),
            "ethereum_dominance": payload.get("eth_dominance"),
            "active_cryptocurrencies": payload.get("active_cryptocurrencies"),
            "source": "coinmarketcap",
        }
    elif isinstance(payload, dict):  # quotes/latest keyed by symbol (v1: dict, v2: list)
        for key, value in payload.items():
            crypto = value[0] if isinstance(value, list) and value else value
            if isinstance(crypto, dict) and "quote" in crypto:
                row = _market_row(crypto, str(key))
                primary[f"market_{row['symbol']}"] = row


# ------------------------------------------------------------------ Dune
def _merge_dune(merged: Dict[str, Any], data: Any, source: str, info: Dict[str, Any]) -> None:
    if not isinstance(data, list) or not data:
        return
    if isinstance(data[0], dict) and any(k in data[0] for k in ("token_pair", "pair_address", "one_day_volume", "seven_day_volume")):
        total = lambda key: sum(float(p.get(key) or 0) for p in data if isinstance(p, dict))  # noqa: E731
        merged["primary_data"]["dex_trading"] = {
            "type": "dex_data",
            "total_pairs": len(data),
            "total_24h_volume": total("one_day_volume"),
            "total_7d_volume": total("seven_day_volume"),
            "total_liquidity": total("usd_liquidity"),
            "top_pairs": data[:5],
            "chain": info.get("chain"),
            "as_of": info.get("as_of"),
            "source": source,
        }
    else:
        merged["supplementary_data"]["blockchain_analytics"] = {"type": "analytics_data", "data": data[:20], "source": source}


# ------------------------------------------------------------------ Etherscan
def _merge_etherscan(merged: Dict[str, Any], data: Any, info: Dict[str, Any]) -> None:
    if not isinstance(data, dict):
        return
    result = data.get("result")
    supplementary = merged["supplementary_data"]
    if isinstance(result, str) and result.isdigit():
        supplementary["wallet_balance"] = {
            "type": "wallet_balance",
            "address": info.get("address"),
            "chain": info.get("chain"),
            "balance_wei": result,
            "balance_native": int(result) / _WEI,
            "source": "etherscan",
        }
    elif isinstance(result, list):
        if info.get("query_type") == "tokentx":
            supplementary["token_transfers"] = {
                "type": "token_transfers",
                "chain": info.get("chain"),
                "total_count": len(result),
                "transfers": [
                    {k: t.get(k) for k in ("tokenSymbol", "tokenName", "from", "to", "value", "tokenDecimal", "timeStamp")}
                    for t in result[:10] if isinstance(t, dict)
                ],
                "source": "etherscan",
            }
        else:
            supplementary["transactions"] = {
                "type": "transaction_data",
                "chain": info.get("chain"),
                "total_count": len(result),
                "transactions": [
                    {
                        "hash": t.get("hash"), "from": t.get("from"), "to": t.get("to"),
                        "value_native": int(t["value"]) / _WEI if str(t.get("value", "")).isdigit() else None,
                        "timeStamp": t.get("timeStamp"), "failed": t.get("isError") == "1",
                    }
                    for t in result[:10] if isinstance(t, dict)
                ],
                "source": "etherscan",
            }


# ------------------------------------------------------------------ DefiLlama
def _merge_defillama(merged: Dict[str, Any], data: Any, info: Dict[str, Any]) -> None:
    supplementary = merged["supplementary_data"]
    if not isinstance(data, dict):
        return
    if data.get("aggregate"):
        for section, key in _DEFILLAMA_SECTIONS.items():
            if isinstance(data.get(section), dict) and data[section]:
                supplementary[key] = data[section]
        return

    kind = data.get("type")
    if kind == "protocol_tvl":
        supplementary[f"protocol_{data.get('slug')}"] = data
    elif kind == "protocol_tvl_list":
        for item in data.get("protocols", []):
            supplementary[f"protocol_{item.get('slug')}"] = item
    elif kind == "chain_tvl_history":
        supplementary[f"chain_tvl_history_{data.get('chain')}"] = data
    elif str(info.get("endpoint", "")).startswith("/prices"):
        supplementary["defillama_prices"] = {"type": "prices", "coins": data.get("coins", data), "source": "defillama"}
    else:
        supplementary["defillama_data"] = {"type": "defillama_data", "endpoint": info.get("endpoint"), "data": data}


# ------------------------------------------------------------------ CoinGecko
def _merge_coingecko(merged: Dict[str, Any], data: Any) -> None:
    """CoinMarketCap stays canonical for prices; CoinGecko fills coins it did not return.

    Merge order is not guaranteed, so a CoinMarketCap row that arrives later overwrites (see
    ``_merge_coinmarketcap``) and a CoinGecko row never replaces an existing one.
    """
    if not isinstance(data, dict):
        return
    primary, sup = merged["primary_data"], merged["supplementary_data"]
    for row in data.get("markets") or []:
        key = f"market_{row.get('symbol')}"
        if key not in primary:
            primary[key] = {"type": "market_data", **row, "source": "coingecko"}
        else:  # keep CoinGecko-only fields (ATH, FDV) alongside the CMC row
            for extra in ("ath", "ath_change_percentage", "ath_date", "fully_diluted_valuation"):
                if row.get(extra) is not None:
                    primary[key].setdefault(extra, row[extra])
    if data.get("history"):
        sup["price_history"] = {"type": "price_history", "source": "coingecko", **data["history"]}
    if data.get("trending"):
        sup["trending"] = {"type": "trending", "source": "coingecko", "coins": data["trending"]}
    if data.get("global") and "global_metrics" not in sup:
        g = data["global"]
        sup["global_metrics"] = {
            "type": "global_metrics", "total_market_cap": g.get("total_market_cap_usd"),
            "total_volume_24h": g.get("total_volume_usd"), "bitcoin_dominance": g.get("btc_dominance"),
            "ethereum_dominance": g.get("eth_dominance"), "active_cryptocurrencies": g.get("active_cryptocurrencies"),
            "market_cap_change_24h_pct": g.get("market_cap_change_24h_pct"), "source": "coingecko",
        }
    if data.get("fear_greed"):
        sup["fear_greed"] = {"type": "fear_greed", "source": "alternative.me", **data["fear_greed"]}
