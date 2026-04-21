#!/usr/bin/env python3
"""e24 pool-level Orca USDC/SOL CL LP simulation (reproducible single-file).

Does NOT require API keys. Uses GeckoTerminal + Orca v2 public APIs.

LIMITATION — pool-level only. Per-LP-position data (individual open/close events,
per-position realized fees/IL/APR) is not obtainable without a paid indexer:
  - public Solana RPC blocks getProgramAccounts on the Whirlpool program
  - Dune/Shyft/Helius/Bitquery free tiers all require an API key
  - Orca's own profitability-analysis tool requires a known wallet/position address
    (no mechanism to enumerate closed positions)
See FINDINGS.md for the blocked-data summary and the specific next-step plan.

Run:
    python3 fetch_and_simulate.py
Outputs land under ../data/.
"""
from __future__ import annotations

import json, math, os, statistics as st, sys, urllib.request
from typing import Any

POOL = "Czfq3xZZDmsdGdUyrNLtRhGc47cXcZtLG4crryfu44zE"
# Orca USDC/SOL Whirlpool, tick_spacing=4, fee_rate=400 (0.04% fee tier)
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)


def _get(url: str, headers: dict[str, str] | None = None) -> Any:
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "curl/8"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def fetch_pool_meta() -> dict:
    d = _get(f"https://api.orca.so/v2/solana/pools/{POOL}")["data"]
    meta = {
        "pool": POOL,
        "tick_spacing": d["tickSpacing"],
        "fee_rate_raw": d["feeRate"],
        "fee_tier_bps": d["feeRate"] / 100,
        "tvl_usd": float(d["tvlUsdc"]),
        "stats_24h": d["stats"]["24h"],
        "stats_7d": d["stats"]["7d"],
        "stats_30d": d["stats"]["30d"],
        "price_history_7d": d.get("priceHistory7d", []),
        "updated_at": d["updatedAt"],
    }
    return meta


def fetch_hourly_ohlcv(hours: int = 2160) -> list[list[float]]:
    """Pull ``hours`` hourly candles via GeckoTerminal free endpoint."""
    merged: dict[int, list] = {}
    before = None
    while len(merged) < hours:
        q = "limit=1000&aggregate=1&currency=usd"
        if before:
            q += f"&before_timestamp={before}"
        url = f"https://api.geckoterminal.com/api/v2/networks/solana/pools/{POOL}/ohlcv/hour?{q}"
        j = _get(url)
        rows = j["data"]["attributes"]["ohlcv_list"]
        if not rows:
            break
        for row in rows:
            merged[int(row[0])] = row
        before = min(int(row[0]) for row in rows)
        if len(rows) < 1000:
            break
    out = sorted(merged.values(), key=lambda x: x[0])
    return out


def realized_vol_annualized(prices: list[float]) -> float:
    rets = []
    for i in range(1, len(prices)):
        if prices[i - 1] > 0 and prices[i] > 0:
            rets.append(math.log(prices[i] / prices[i - 1]))
    if len(rets) < 2:
        return 0.0
    return st.stdev(rets) * math.sqrt(24 * 365)


def sim_range(
    prices: list[float], width_pct: float, conc_mult: float, pool_gross_apr: float
) -> dict:
    """CL position value + fee-earned model, given a price path and deployed width.

    Entry/exit at the first/last price. ``width_pct`` = symmetric half-width (e.g.
    0.05 = ±5%). ``conc_mult`` is a multiplier on pool-average fee APR that
    represents how much fee yield a concentrated LP captures vs the average
    pool-weighted LP. 1.0 = pool-share only (conservative lower bound). 2.0 =
    moderate concentration advantage (realistic mid estimate given the pool
    already has many concentrated LPs). Higher multipliers (5-20) assume little
    competition from other tight LPs — usually too optimistic.
    """
    p0, pN = prices[0], prices[-1]
    p_lo, p_hi = p0 * (1 - width_pct), p0 * (1 + width_pct)
    in_range = sum(1 for p in prices if p_lo <= p <= p_hi)
    tir = in_range / len(prices)
    fee_apr = pool_gross_apr * conc_mult * tir
    sq = math.sqrt
    # Normalize: liquidity L such that position value at p0 = 1 USD
    L = 1.0 / (2 * sq(p0) - sq(p_lo) - p0 / sq(p_hi))
    if pN <= p_lo:
        principal = L * (1 / sq(p_lo) - 1 / sq(p_hi)) * pN
    elif pN >= p_hi:
        principal = L * (sq(p_hi) - sq(p_lo))
    else:
        principal = L * (1 / sq(pN) - 1 / sq(p_hi)) * pN + L * (sq(pN) - sq(p_lo))
    wdays = len(prices) / 24
    fee_earned = fee_apr * (wdays / 365)
    net = principal + fee_earned
    hodl = 0.5 * (pN / p0) + 0.5
    return {
        "tir_pct": round(tir * 100, 2),
        "principal_final_usd": round(principal, 4),
        "hodl_final_usd": round(hodl, 4),
        "fee_earned_usd": round(fee_earned, 4),
        "net_final_usd": round(net, 4),
        "il_vs_hodl_pct": round((principal - hodl) / hodl * 100, 2),
        "net_pnl_pct": round((net - 1) * 100, 2),
        "net_apr_pct": round((net - 1) * 100 * 365 / wdays, 1),
        "net_apr_vs_hodl_pct": round(((net - hodl) / hodl * 100) * 365 / wdays, 1),
        "exited_range": not (p_lo <= pN <= p_hi),
    }


def pct(xs: list[float], q: float) -> float:
    if not xs:
        return float("nan")
    xs = sorted(xs)
    return xs[int(q * (len(xs) - 1))]


def bootstrap_cells(prices: list[float], pool_gross_apr: float) -> list[dict]:
    cells = []
    for dur_hours, dur_label in ((24, "<24h"), (168, "24h-7d"), (720, ">7d")):
        wins = []
        for start in range(0, len(prices) - dur_hours, 24):
            sl = prices[start : start + dur_hours + 1]
            if len(sl) < 2:
                continue
            wins.append({"slice": sl, "vol": realized_vol_annualized(sl)})
        if len(wins) < 9:
            continue
        vols = sorted(w["vol"] for w in wins)
        n = len(vols)
        t_lo, t_hi = vols[n // 3], vols[2 * n // 3]
        regimes = {"low": [], "med": [], "high": []}
        for w in wins:
            if w["vol"] <= t_lo:
                regimes["low"].append(w)
            elif w["vol"] >= t_hi:
                regimes["high"].append(w)
            else:
                regimes["med"].append(w)
        for reg, ws in regimes.items():
            for width in (0.025, 0.05, 0.10, 0.20, 0.40):
                for conc in (1.0, 2.0):
                    aprs = [
                        sim_range(w["slice"], width, conc, pool_gross_apr)["net_apr_pct"]
                        for w in ws
                    ]
                    if not aprs:
                        continue
                    aprs.sort()
                    cells.append(
                        {
                            "duration": dur_label,
                            "vol_regime": reg,
                            "vol_tercile_lo_ann_pct": round(t_lo * 100, 1),
                            "vol_tercile_hi_ann_pct": round(t_hi * 100, 1),
                            "width_pct": width * 100,
                            "width_bucket": (
                                "narrow" if width < 0.05 else "medium" if width <= 0.20 else "wide"
                            ),
                            "conc_mult": conc,
                            "n": len(aprs),
                            "median_net_apr": round(pct(aprs, 0.5), 1),
                            "p25": round(pct(aprs, 0.25), 1),
                            "p75": round(pct(aprs, 0.75), 1),
                            "pct_losing": round(sum(1 for a in aprs if a < 0) / len(aprs) * 100, 1),
                            "pct_over_5pct_apr": round(
                                sum(1 for a in aprs if a > 5) / len(aprs) * 100, 1
                            ),
                        }
                    )
    return cells


def main() -> None:
    meta = fetch_pool_meta()
    json.dump(meta, open(f"{DATA_DIR}/pool_meta.json", "w"), indent=2, default=str)

    hourly = fetch_hourly_ohlcv(2160)
    json.dump(hourly, open(f"{DATA_DIR}/sol_usdc_hourly_90d.json", "w"))
    # Trim to most recent 90d if we over-fetched
    cutoff = hourly[-1][0] - 90 * 86400
    hourly = [h for h in hourly if h[0] >= cutoff]
    prices = [row[4] for row in hourly]

    pool_gross_apr = float(meta["stats_30d"]["yieldOverTvl"]) * 12  # 30d -> annual (xN months)
    if pool_gross_apr < 0.05:
        # fallback: 24h snapshot
        pool_gross_apr = float(meta["stats_24h"]["yieldOverTvl"]) * 365
    print(f"pool_gross_apr (model input) = {pool_gross_apr*100:.1f}%")

    vol_ann = realized_vol_annualized(prices)
    p0, pN = prices[0], prices[-1]
    stats = {
        "pool": POOL,
        "window_n_hours": len(hourly),
        "window_start_ts": hourly[0][0],
        "window_end_ts": hourly[-1][0],
        "sol_90d_pct_change": round((pN / p0 - 1) * 100, 2),
        "sol_90d_max": max(row[2] for row in hourly),
        "sol_90d_min": min(row[3] for row in hourly),
        "sol_realized_vol_ann_pct": round(vol_ann * 100, 1),
        "pool_tvl_usd": meta["tvl_usd"],
        "pool_gross_apr_model_pct": round(pool_gross_apr * 100, 1),
    }
    json.dump(stats, open(f"{DATA_DIR}/pool_level_stats.json", "w"), indent=2)

    # Single 90d window per width
    single = []
    for w in (0.025, 0.05, 0.10, 0.20, 0.40):
        for conc in (1.0, 2.0):
            r = sim_range(prices, w, conc, pool_gross_apr)
            r.update({"width_pct": w * 100, "conc_mult": conc})
            single.append(r)
    json.dump(single, open(f"{DATA_DIR}/single_window_90d.json", "w"), indent=2)

    # Full bootstrap stratification
    cells = bootstrap_cells(prices, pool_gross_apr)
    json.dump(
        {
            "model": "pool-level simulation (NOT per-LP-position measurement)",
            "pool": POOL,
            "pool_gross_apr_pct": round(pool_gross_apr * 100, 1),
            "sol_realized_vol_ann_pct": round(vol_ann * 100, 1),
            "cells": cells,
        },
        open(f"{DATA_DIR}/stratification_poolmodel.json", "w"),
        indent=2,
    )
    print(f"wrote {len(cells)} cells")


if __name__ == "__main__":
    main()
