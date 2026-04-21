"""Preview aggregation on only the parts available so far.

Same logic as 03_aggregate_calibration.py but tolerates missing parts so we
can inspect directional signal before all four finish streaming.

Usage:
    uv run python -m experiments.e16_calibration_study.03_preview
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"

BUCKETS = [(i / 100.0, (i + 5) / 100.0) for i in range(0, 100, 5)]


def bucket_label(p: float) -> str:
    for lo, hi in BUCKETS:
        if lo <= p < hi:
            return f"{lo:.2f}-{hi:.2f}"
    return "0.95-1.00"


def bucket_mid(p: float) -> float:
    for lo, hi in BUCKETS:
        if lo <= p < hi:
            return lo + 0.025
    return 0.975


def main() -> int:
    audit = pd.read_parquet(DATA_DIR / "01_markets_audit.parquet")

    parts_loaded = []
    for n in (1, 2, 3, 4):
        p = DATA_DIR / f"02_prices_part{n}.parquet"
        if p.exists() and p.stat().st_size > 0:
            try:
                parts_loaded.append((n, pd.read_parquet(p)))
            except Exception as e:
                print(f"  part {n} not readable yet: {e}")
    if not parts_loaded:
        print("no parts ready")
        return 1
    print(f"loaded parts: {[n for n, _ in parts_loaded]}")

    prices = pd.concat([p for _, p in parts_loaded], ignore_index=True)
    print(f"  {len(prices):,} price rows pre-dedup")

    agg = (prices.groupby("condition_id", as_index=False)
                  .agg(vwap_7d=("vwap_7d", "mean"),
                       n_trades=("n_trades", "sum"),
                       last_ts=("last_ts", "max")))
    print(f"  {len(agg):,} unique markets after part-merge")

    j = audit.merge(agg, on="condition_id", how="inner")
    j = j[j["n_trades"] >= 3].copy()
    j["bucket"] = j["vwap_7d"].apply(bucket_label)
    j["bucket_mid"] = j["vwap_7d"].apply(bucket_mid)
    j["yes"] = (j["resolution"] == "YES").astype(int)
    print(f"  joined + filtered (n_trades>=3): {len(j):,} markets")

    # Overall
    overall = (j.groupby("bucket")
                 .agg(n=("yes", "size"),
                      yes_rate=("yes", "mean"),
                      bucket_mid=("bucket_mid", "mean"))
                 .reset_index())
    overall["deviation"] = overall["yes_rate"] - overall["bucket_mid"]
    overall = overall.sort_values("bucket")

    print(f"\n=== OVERALL CALIBRATION (parts={[n for n,_ in parts_loaded]}) ===")
    print(f"  {'bucket':<12} {'n':>7}  {'mid':>6}  {'yes_rate':>9}  {'dev':>7}")
    for _, r in overall.iterrows():
        print(f"  {r['bucket']:<12} {int(r['n']):>7,}  {r['bucket_mid']:>6.3f}  "
              f"{r['yes_rate']:>9.3f}  {r['deviation']:>+7.3f}")

    # Category × bucket, n>=30
    grouped = (j.groupby(["category", "bucket"])
                 .agg(n=("yes", "size"),
                      yes_rate=("yes", "mean"),
                      bucket_mid=("bucket_mid", "mean"),
                      total_volume=("volume", "sum"))
                 .reset_index())
    grouped["deviation"] = grouped["yes_rate"] - grouped["bucket_mid"]
    grouped["abs_deviation"] = grouped["deviation"].abs()
    actionable = grouped[grouped["n"] >= 30].sort_values("abs_deviation", ascending=False).head(25)

    print(f"\n=== TOP DEVIATIONS (category x bucket, n>=30) ===")
    print(f"  {'category':<22} {'bucket':<12} {'n':>5}  {'mid':>5}  "
          f"{'yes_rate':>8}  {'dev':>+6}  {'vol':>12}")
    for _, r in actionable.iterrows():
        print(f"  {r['category']:<22} {r['bucket']:<12} {int(r['n']):>5,}  "
              f"{r['bucket_mid']:>5.2f}  {r['yes_rate']:>8.3f}  {r['deviation']:>+6.3f}  "
              f"${r['total_volume']:>12,.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
