"""Agent F — execution-adjusted edge + deployment math.

Takes the e16 measured raw edge of +25.8pp at the 0.55-0.60 T-7d bucket
(sports-deep, n=120, yes_rate 0.833 vs bucket mid 0.575, z=7.6) and applies
four layers of execution friction, producing three output matrices and a
deployment recommendation.

Inputs:
  experiments/e16_calibration_study/data/05_tm7d_prices_sports_deep.parquet

Outputs (written to ./data/):
  net_edge_matrix.json
  capital_deployment.json
  fill_probability_matrix.json
  bucket_depth_stats.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
DATA_DIR = HERE / "data"
DATA_DIR.mkdir(exist_ok=True)

PARQUET = Path(__file__).resolve().parents[2] / (
    "e16_calibration_study/data/05_tm7d_prices_sports_deep.parquet"
)

# -- Measured inputs (e16 sports-deep) --
RAW_EDGE_PP = 25.8           # +25.8pp at 0.55-0.60
BUCKET_MID = 0.575           # midpoint of 0.55-0.60
YES_RATE = 0.833             # measured yes_rate in this bucket (n=120)
ORDER_SIZES = [200, 500, 1000, 2000]
FEE_SCENARIOS_BPS = [0.0, 3.0, 7.2, 15.0]
CAPITAL_LEVELS = [5_000, 10_000, 25_000, 50_000]
BETS_PER_MONTH_RANGE = (15, 20)  # qualifying bets per month


# ---------------------------------------------------------------------------
# Friction model assumptions (documented in DECISIONS.md)
# ---------------------------------------------------------------------------

# Layer 1 — Bid/ask spread
# e22 cross-venue: Polymarket vs Smarkets within 0.75pp |mean| on live events.
# e11/e4 do not have a clean measurement at the 0.55-0.60 bucket for sports.
# Conservative central estimate: 2pp spread. Sensitivity: 1pp (tight) to 3pp (wide).
# When buying at the ask we pay the full spread vs bid, but only half the spread vs
# mid. Standard convention: cost = half-spread from mid. We use half_spread = 1pp.
HALF_SPREAD_PP = 1.0          # central estimate
HALF_SPREAD_LOW_PP = 0.5      # tight book
HALF_SPREAD_HIGH_PP = 1.5     # wide book


# Layer 2 — Fees (one-sided; strategy is buy-and-hold to resolution)
# Polymarket fee formula: fee_per_contract = p * (1-p) * fee_bps / 10000
# Applied at entry only — at resolution the contract pays 0 or 1, no exit trade.
# The fee is paid on the notional of the trade when opening the position.
def fee_pp_per_side(price: float, fee_bps: float) -> float:
    """Return fee as a percentage of notional (in pp)."""
    return price * (1 - price) * fee_bps / 10_000 * 100


# Layer 3 — Slippage
# Model: "walking the book" beyond the top-of-book fillable size.
# Proxy: `median_trade_usd` in the T-7d window ~= typical single-print fill capacity.
# For the 0.55-0.60 bucket sub-sample: median_trade_usd p50 = $20, p75 = $30.
# Assumption: 1pp slippage per $500 of order size above the median-single-fill USD.
# That is: an order of $500 above the typical print fills 1pp worse on average.
# This is a deliberately generous haircut — reality may be less if the
# book is thicker than the median PRINT (which undersamples passive resting depth).
SLIPPAGE_PP_PER_500USD = 1.0
MEDIAN_SINGLE_FILL_USD_PROXY = 20.0  # p50 of median_trade_usd in the bucket


def slippage_pp(order_size_usd: float) -> float:
    excess = max(0.0, order_size_usd - MEDIAN_SINGLE_FILL_USD_PROXY)
    return (excess / 500.0) * SLIPPAGE_PP_PER_500USD


# Layer 4 — Fill probability
# Model: probability the full order fills at-or-below our entry cap price.
# Anchored on the observed "n with max_single_fill>=X" fractions from the
# sports-deep parquet for the 0.55-0.60 bucket:
#   $200 -> 86.7% had a max single trade >= $200
#   $500 -> 83.3%
#   $1000 -> 80.0%
#   $2000 -> 74.2%
# We treat "max_single_trade_usd >= X" as a generous ceiling for fill probability.
# Real fill prob at the *quoted* price will be lower because a single fill that
# size may have walked further up the book. We apply a 0.85x haircut to reflect
# that heuristic.
FILL_CAP_HAIRCUT = 0.85


def bucket_stats(df: pd.DataFrame) -> dict:
    mask = (df["price_tm7d"] >= 0.55) & (df["price_tm7d"] < 0.60)
    sub = df[mask].copy()
    out = {
        "n": int(len(sub)),
        "yes_rate": float(sub["resolution"].eq("YES").mean()),
        "median_trade_usd_p50": float(sub["median_trade_usd"].median()),
        "median_trade_usd_p75": float(sub["median_trade_usd"].quantile(0.75)),
        "max_single_trade_usd_p50": float(sub["max_single_trade_usd"].median()),
        "max_single_trade_usd_p25": float(sub["max_single_trade_usd"].quantile(0.25)),
        "total_usd_window_p50": float(sub["total_usd_window"].median()),
        "fill_ceiling_pct": {},
        "by_category": {},
    }
    for thresh in [200, 500, 1000, 2000]:
        out["fill_ceiling_pct"][thresh] = float(
            (sub["max_single_trade_usd"] >= thresh).mean()
        )
    sub["yes"] = (sub["resolution"] == "YES").astype(int)
    by_cat = sub.groupby("category").agg(
        n=("yes", "size"),
        yes_rate=("yes", "mean"),
        med_max_single=("max_single_trade_usd", "median"),
    )
    out["by_category"] = by_cat.reset_index().to_dict(orient="records")
    return out


# ---------------------------------------------------------------------------
# Matrix 1 — Net edge after all friction
# ---------------------------------------------------------------------------
def net_edge_pp(order_size: float, fee_bps: float,
                half_spread_pp: float = HALF_SPREAD_PP,
                fee_model: str = "one_sided") -> dict:
    """Compute net edge in pp after spread + fees + slippage.

    fee_model: "one_sided" (buy + hold to resolution, only entry fee applies)
               "two_sided" (buy + sell before resolution, entry + exit fee)
    """
    # Spread + slippage are always entry-side only (one crossing of the book)
    spread_cost = half_spread_pp
    slip = slippage_pp(order_size)
    # Fees: one-sided (hold to resolution) vs two-sided (exit early)
    f = fee_pp_per_side(BUCKET_MID, fee_bps)
    if fee_model == "one_sided":
        fee_cost = f
    elif fee_model == "two_sided":
        fee_cost = 2 * f
    else:
        raise ValueError(fee_model)
    net = RAW_EDGE_PP - spread_cost - slip - fee_cost
    return {
        "order_size": order_size,
        "fee_bps": fee_bps,
        "fee_model": fee_model,
        "half_spread_pp": spread_cost,
        "slippage_pp": slip,
        "fee_pp_per_side": f,
        "total_fee_pp": fee_cost,
        "total_friction_pp": spread_cost + slip + fee_cost,
        "raw_edge_pp": RAW_EDGE_PP,
        "net_edge_pp": net,
    }


def build_net_edge_matrix(fee_model: str = "one_sided") -> dict:
    out = {"fee_model": fee_model, "assumptions": {
        "raw_edge_pp": RAW_EDGE_PP,
        "bucket_mid": BUCKET_MID,
        "half_spread_pp": HALF_SPREAD_PP,
        "slippage_pp_per_500usd": SLIPPAGE_PP_PER_500USD,
        "median_single_fill_usd_proxy": MEDIAN_SINGLE_FILL_USD_PROXY,
    }, "cells": []}
    for size in ORDER_SIZES:
        for bps in FEE_SCENARIOS_BPS:
            out["cells"].append(net_edge_pp(size, bps, fee_model=fee_model))
    return out


# ---------------------------------------------------------------------------
# Matrix 2 — Capital deployment
# ---------------------------------------------------------------------------
def _pnl_for_size(size: float, fee_bps: float = 3.0) -> dict:
    """Return (fill_prob, net_edge_pp, expected_pnl_pp) at a given size & fee."""
    cell = net_edge_pp(size, fee_bps, fee_model="one_sided")
    # Fill prob: use empirical ceiling × haircut. Anchors at $200/$500/$1000/$2000;
    # we interpolate linearly between anchors for intermediate sizes.
    anchors = {200: 0.8667, 500: 0.8333, 1000: 0.80, 2000: 0.7417}
    if size <= 200:
        ceiling = anchors[200]
    elif size >= 2000:
        ceiling = anchors[2000]
    else:
        # linear interp between surrounding anchors
        keys = sorted(anchors.keys())
        for lo, hi in zip(keys, keys[1:]):
            if lo <= size <= hi:
                t = (size - lo) / (hi - lo)
                ceiling = anchors[lo] + t * (anchors[hi] - anchors[lo])
                break
    fill = ceiling * FILL_CAP_HAIRCUT
    exp_edge_pp = fill * cell["net_edge_pp"]
    return {"fill_prob": fill, "net_edge_pp": cell["net_edge_pp"],
            "expected_edge_pp": exp_edge_pp}


def capital_deployment() -> dict:
    """At each capital level × correction factor, compute annualized $ return.

    Sizing policy: we scale position size with capital, capped at $2000 per bet
    and floored such that concurrent positions do not exceed bankroll.
      concurrent ≈ bets_per_month * (7 days / 30 days)
      pos_size   = min($2000, max($200, capital / (concurrent × 2)))
    The ×2 buffer leaves slack for variance; in practice you'd size to Kelly or
    similar, but the goal here is to show the shape across capital levels.

    Expected dollar P&L per year =
        bets_per_year × pos_size × expected_edge_per_bet_pp / 100
    where expected_edge_per_bet_pp is fill-prob × net_edge at that pos_size.
    """
    bets_mid = sum(BETS_PER_MONTH_RANGE) / 2  # 17.5
    bets_per_year = bets_mid * 12             # 210/yr
    concurrent = bets_mid * (7 / 30)          # ~4.1 simultaneous T-7d positions

    results = []
    for cap in CAPITAL_LEVELS:
        # Scale position size with capital, but cap at $2000 and floor at $200
        raw_size = cap / (concurrent * 2)
        pos_size = max(200.0, min(2000.0, raw_size))

        stats = _pnl_for_size(pos_size, fee_bps=3.0)

        pnl_net_yr = bets_per_year * pos_size * (stats["expected_edge_pp"] / 100)
        # Raw scenario: measured raw edge (25.8pp) × full fill — perfect-world ceiling
        # still weight by fill prob to keep it comparable
        pnl_raw_yr = bets_per_year * pos_size * (stats["fill_prob"] * RAW_EDGE_PP / 100)

        entry = {
            "capital_usd": cap,
            "position_size_usd": round(pos_size, 0),
            "bets_per_year": bets_per_year,
            "concurrent_positions": round(concurrent, 2),
            "fill_prob": round(stats["fill_prob"], 3),
            "net_edge_pp": round(stats["net_edge_pp"], 2),
            "expected_edge_per_bet_pp": round(stats["expected_edge_pp"], 2),
            "raw": {
                "edge_pp_nominal": RAW_EDGE_PP,
                "annual_pnl_usd": round(pnl_raw_yr, 0),
                "annual_return_pct": round(100 * pnl_raw_yr / cap, 1),
            },
            "net_adjusted": {
                "edge_pp_effective": round(stats["expected_edge_pp"], 2),
                "annual_pnl_usd": round(pnl_net_yr, 0),
                "annual_return_pct": round(100 * pnl_net_yr / cap, 1),
            },
            "correction_factors": {},
        }
        for name, factor in [("optimistic_div2", 2), ("moderate_div3", 3),
                             ("conservative_div5", 5)]:
            adj_pnl = pnl_net_yr / factor
            entry["correction_factors"][name] = {
                "divisor": factor,
                "annual_pnl_usd": round(adj_pnl, 0),
                "annual_return_pct": round(100 * adj_pnl / cap, 1),
            }
        results.append(entry)

    return {
        "assumptions": {
            "bets_per_month_low": BETS_PER_MONTH_RANGE[0],
            "bets_per_month_high": BETS_PER_MONTH_RANGE[1],
            "bets_per_month_mid": bets_mid,
            "concurrent_positions": round(concurrent, 2),
            "sizing_policy": "pos_size = clip($200, capital / (concurrent × 2), $2000)",
            "fee_bps_assumed": 3.0,
            "fee_model": "one_sided (buy + hold to resolution)",
            "raw_scenario_note": "fill-prob weighted; uses raw +25.8pp edge with execution friction zeroed out",
            "net_scenario_note": "full friction stack: half-spread + slippage + fees + fill-prob haircut",
        },
        "rows": results,
    }


# ---------------------------------------------------------------------------
# Matrix 3 — Fill probability × size
# ---------------------------------------------------------------------------
def fill_prob_matrix(df: pd.DataFrame) -> dict:
    mask = (df["price_tm7d"] >= 0.55) & (df["price_tm7d"] < 0.60)
    sub = df[mask]
    rows = []
    for size in ORDER_SIZES:
        # Empirical ceiling: fraction of bucket markets with max_single_trade >= size
        ceiling = float((sub["max_single_trade_usd"] >= size).mean())
        # Haircut-adjusted fill probability:
        fill = ceiling * FILL_CAP_HAIRCUT
        # Net edge at this size, 3bps (sports default), one-sided fees:
        cell = net_edge_pp(size, 3.0, fee_model="one_sided")
        net = cell["net_edge_pp"]
        # Expected P&L per bet at this size = fill_prob × net_edge × size
        expected_pnl_per_bet = fill * (net / 100) * size
        # Fill-prob-weighted P&L in dollars per qualifying bet opportunity
        rows.append({
            "order_size_usd": size,
            "ceiling_from_data": ceiling,
            "fill_prob_adjusted": fill,
            "net_edge_pp_at_3bps": net,
            "expected_pnl_per_bet_usd": expected_pnl_per_bet,
            "expected_pnl_per_bet_pct_of_notional": 100 * expected_pnl_per_bet / size,
        })
    return {
        "assumptions": {
            "fill_cap_haircut": FILL_CAP_HAIRCUT,
            "source": "e16 sports-deep parquet, 0.55-0.60 bucket, n=120",
            "fee_bps": 3.0,
            "fee_model": "one_sided (buy + hold to resolution)",
        },
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# Sensitivity: fee-model comparison (one-sided vs two-sided)
# ---------------------------------------------------------------------------
def fee_model_comparison() -> dict:
    """Side-by-side at operating cell $500, 3bps fee."""
    one = net_edge_pp(500, 3.0, fee_model="one_sided")
    two = net_edge_pp(500, 3.0, fee_model="two_sided")
    return {"one_sided": one, "two_sided": two,
            "delta_pp": one["net_edge_pp"] - two["net_edge_pp"]}


def main():
    df = pd.read_parquet(PARQUET)

    bstats = bucket_stats(df)
    m1_one = build_net_edge_matrix("one_sided")
    m1_two = build_net_edge_matrix("two_sided")
    m2 = capital_deployment()
    m3 = fill_prob_matrix(df)
    fm = fee_model_comparison()

    (DATA_DIR / "bucket_depth_stats.json").write_text(json.dumps(bstats, indent=2))
    (DATA_DIR / "net_edge_matrix.json").write_text(json.dumps(
        {"one_sided": m1_one, "two_sided": m1_two}, indent=2))
    (DATA_DIR / "capital_deployment.json").write_text(json.dumps(m2, indent=2))
    (DATA_DIR / "fill_probability_matrix.json").write_text(json.dumps(m3, indent=2))
    (DATA_DIR / "fee_model_comparison.json").write_text(json.dumps(fm, indent=2))

    # Pretty-print summary
    print(f"=== Bucket 0.55-0.60 stats (n={bstats['n']}) ===")
    print(f"  yes_rate = {bstats['yes_rate']:.3f}")
    print(f"  median_trade_usd p50 = ${bstats['median_trade_usd_p50']:.1f}")
    print(f"  max_single_trade_usd p50 = ${bstats['max_single_trade_usd_p50']:.1f}")
    print(f"  fill_ceiling_pct: {bstats['fill_ceiling_pct']}")
    print()
    print("=== Matrix 1 — Net edge (one-sided fee, buy-and-hold) ===")
    print(f"  {'Size':>6} | {'0 bps':>8} {'3 bps':>8} {'7.2 bps':>8} {'15 bps':>8}")
    for size in ORDER_SIZES:
        line = f"  ${size:>5} |"
        for bps in FEE_SCENARIOS_BPS:
            cell = next(c for c in m1_one["cells"]
                        if c["order_size"] == size and c["fee_bps"] == bps)
            line += f" {cell['net_edge_pp']:>7.2f}pp"
        print(line)
    print()
    print("=== Matrix 2 — Capital deployment (annualized $) ===")
    for row in m2["rows"]:
        print(f"  ${row['capital_usd']:>6,}: "
              f"raw ${row['raw']['annual_pnl_usd']:>7,.0f} "
              f"({row['raw']['annual_return_pct']:.1f}%)  "
              f"net ${row['net_adjusted']['annual_pnl_usd']:>7,.0f} "
              f"({row['net_adjusted']['annual_return_pct']:.1f}%)")
        for k, v in row["correction_factors"].items():
            print(f"     {k}: ${v['annual_pnl_usd']:>7,.0f} "
                  f"({v['annual_return_pct']:.1f}%)")
    print()
    print("=== Matrix 3 — Fill prob × size ===")
    for row in m3["rows"]:
        print(f"  ${row['order_size_usd']:>5}: fill_prob={row['fill_prob_adjusted']:.3f} "
              f"net_edge={row['net_edge_pp_at_3bps']:+.2f}pp "
              f"E[pnl]=${row['expected_pnl_per_bet_usd']:+.2f}")

    print()
    print(f"=== Fee-model comparison @ $500, 3bps ===")
    print(f"  one-sided (hold to resolution): {fm['one_sided']['net_edge_pp']:+.2f}pp")
    print(f"  two-sided (buy+sell before):    {fm['two_sided']['net_edge_pp']:+.2f}pp")
    print(f"  delta: {fm['delta_pp']:+.2f}pp")


if __name__ == "__main__":
    main()
