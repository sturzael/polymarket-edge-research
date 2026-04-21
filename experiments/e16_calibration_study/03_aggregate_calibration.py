"""Merge 4 part-price parquets with markets-audit, bucket prices, compute
empirical resolution rate per (category, price_bucket).

Inputs:
    data/01_markets_audit.parquet              (condition_id, category, resolution, ...)
    data/02_prices_part{1,2,3,4}.parquet        (condition_id, vwap_7d, n_trades, last_ts, last_price)

Output:
    data/03_calibration.parquet                 (one row per market with joined fields)
    data/03_calibration_table.json              (aggregated table)
    stdout                                       (human report)

Calibration interpretation:
  - bucket midpoint = implied probability the market priced
  - empirical YES rate = actual resolution rate
  - deviation = empirical - bucket_mid. Positive = market UNDER-priced YES.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
AUDIT = DATA_DIR / "01_markets_audit.parquet"
OUT_PARQUET = DATA_DIR / "03_calibration.parquet"
OUT_JSON = DATA_DIR / "03_calibration_table.json"

# Buckets: 0-5, 5-10, 10-15, ..., 95-100 (20 buckets of 5 percentage points)
BUCKETS = [(i / 100.0, (i + 5) / 100.0) for i in range(0, 100, 5)]


def bucket_label(p: float) -> str:
    for lo, hi in BUCKETS:
        if lo <= p < hi:
            return f"{lo:.2f}-{hi:.2f}"
    return "0.95-1.00"


def main() -> int:
    audit = pd.read_parquet(AUDIT)
    print(f"audit: {len(audit):,} resolved markets")

    parts = []
    for n in (1, 2, 3, 4):
        p = DATA_DIR / f"02_prices_part{n}.parquet"
        if not p.exists():
            print(f"  MISSING: {p} — aborting")
            return 1
        parts.append(pd.read_parquet(p))

    prices = pd.concat(parts, ignore_index=True)
    print(f"prices: {len(prices):,} rows across 4 parts (pre-dedup)")

    # If same condition appears in multiple parts, combine: weighted average
    # by n_trades, keep latest last_ts + last_price from the latest part.
    agg = (prices.groupby("condition_id", as_index=False)
                  .apply(lambda g: pd.Series({
                      "vwap_7d": (g["vwap_7d"] * g["n_trades"]).sum() / g["n_trades"].sum()
                                  if g["n_trades"].sum() > 0 else g["vwap_7d"].mean(),
                      "n_trades": int(g["n_trades"].sum()),
                      "last_price": float(g.loc[g["last_ts"].idxmax(), "last_price"]),
                      "last_ts": int(g["last_ts"].max()),
                  }))
                  .reset_index(drop=True))
    print(f"prices: {len(agg):,} unique markets after part-merge")

    # Join with audit
    j = audit.merge(agg, on="condition_id", how="inner")
    print(f"joined: {len(j):,} markets with both resolution + pre-resolution price")

    # Filter: need at least 3 trades in the 7-day window for stable VWAP
    j = j[j["n_trades"] >= 3].copy()
    print(f"filtered n_trades>=3: {len(j):,}")

    # Price bucket (use vwap_7d as the canonical pre-close price)
    j["bucket"] = j["vwap_7d"].apply(bucket_label)
    j["bucket_mid"] = j["vwap_7d"].apply(
        lambda p: next((lo + 0.025 for lo, hi in BUCKETS if lo <= p < hi), 0.975)
    )
    j["yes"] = (j["resolution"] == "YES").astype(int)

    j.to_parquet(OUT_PARQUET, index=False)

    # Aggregate: (category, bucket) -> n, yes_rate, deviation, total_volume
    grouped = (j.groupby(["category", "bucket"])
                 .agg(n=("yes", "size"),
                      yes_rate=("yes", "mean"),
                      bucket_mid=("bucket_mid", "mean"),
                      mean_price=("vwap_7d", "mean"),
                      total_volume=("volume", "sum"))
                 .reset_index())
    grouped["deviation"] = grouped["yes_rate"] - grouped["bucket_mid"]
    grouped["abs_deviation"] = grouped["deviation"].abs()

    # Overall table: aggregate across all categories by bucket
    overall = (j.groupby("bucket")
                 .agg(n=("yes", "size"),
                      yes_rate=("yes", "mean"),
                      bucket_mid=("bucket_mid", "mean"),
                      total_volume=("volume", "sum"))
                 .reset_index())
    overall["deviation"] = overall["yes_rate"] - overall["bucket_mid"]

    # Category summaries
    cat_summary = (j.groupby("category")
                     .agg(n=("yes", "size"),
                          yes_rate_overall=("yes", "mean"),
                          mean_price_overall=("vwap_7d", "mean"),
                          total_volume=("volume", "sum"))
                     .reset_index())
    cat_summary["yes_rate_vs_price"] = (
        cat_summary["yes_rate_overall"] - cat_summary["mean_price_overall"])

    # Top cells by |deviation| where n >= 30 (actionable signals)
    actionable = grouped[(grouped["n"] >= 30)].sort_values(
        "abs_deviation", ascending=False).head(30)

    # Detailed: for every category, print each non-empty bucket
    out_payload = {
        "n_markets_final": int(len(j)),
        "overall_by_bucket": overall.to_dict(orient="records"),
        "category_summary": cat_summary.to_dict(orient="records"),
        "by_category_bucket": grouped.to_dict(orient="records"),
        "top_actionable_cells": actionable.to_dict(orient="records"),
    }
    OUT_JSON.write_text(json.dumps(out_payload, indent=2, default=str))

    print(f"\n=== OVERALL CALIBRATION (all categories) ===")
    print(f"  {'bucket':<12} {'n':>6}  {'mid':>6}  {'yes_rate':>9}  {'dev':>7}")
    for _, r in overall.iterrows():
        print(f"  {r['bucket']:<12} {int(r['n']):>6,}  {r['bucket_mid']:>6.3f}  "
              f"{r['yes_rate']:>9.3f}  {r['deviation']:>+7.3f}")

    print(f"\n=== CATEGORY-LEVEL (n>=30 cells, sorted by |deviation|) ===")
    print(f"  {'category':<22} {'bucket':<12} {'n':>5}  {'mid':>5}  "
          f"{'yes_rate':>8}  {'dev':>6}  vol")
    for _, r in actionable.iterrows():
        print(f"  {r['category']:<22} {r['bucket']:<12} {int(r['n']):>5,}  "
              f"{r['bucket_mid']:>5.2f}  {r['yes_rate']:>8.3f}  {r['deviation']:>+6.3f}  "
              f"${r['total_volume']:>10,.0f}")

    print(f"\n  wrote {OUT_PARQUET} and {OUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
