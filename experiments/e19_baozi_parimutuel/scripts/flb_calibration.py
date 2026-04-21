"""Baozi FLB calibration from final-pool implied probabilities.

Takes the parquet produced by `probe_baozi.py`, filters to resolved markets,
computes implied_yes_close = yes_pool / (yes_pool + no_pool), buckets in 5pp
bands, and reports yes_rate, deviation, z-score per bucket.

This matches the e16 Polymarket methodology EXCEPT:
  - Snapshot time = market CLOSE (T-0), not T-7d, because we only have current
    on-chain pool state, not a time series. Pari-mutuel pools are monotonic in
    the sense that late money doesn't revise the odds of earlier money — each
    dollar bet at time t implies probability yes_pool(t) / total_pool(t). For
    a T-7d snapshot we'd need to replay bets from `getSignaturesForAddress`.
  - Category inferred from question-text keywords, not from a tagged field.

Z-score formula (same as e16):  z = |deviation| / sqrt(mid * (1 - mid) / n)

Usage:
    uv run python scripts/flb_calibration.py \\
        --in data/baozi_markets.parquet \\
        --out-json data/baozi_flb.json \\
        --min-pool-sol 0.5
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


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


def zscore(yes_rate: float, mid: float, n: int) -> float:
    if n <= 0 or mid <= 0 or mid >= 1:
        return 0.0
    se = math.sqrt(mid * (1 - mid) / n)
    return abs(yes_rate - mid) / se if se else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="data/baozi_markets.parquet")
    ap.add_argument("--out-json", default="data/baozi_flb.json")
    ap.add_argument("--min-pool-sol", type=float, default=0.5,
                    help="min total pool size (SOL) to include — filters spam/test markets.")
    ap.add_argument("--status-include", nargs="+", default=["Resolved"])
    args = ap.parse_args()

    df = pd.read_parquet(args.inp)
    print(f"loaded {len(df):,} rows from {args.inp}")

    df = df[df["market_type"] == "boolean"]
    df = df[df["status"].isin(args.status_include)]
    df = df[df["total_pool_sol"] >= args.min_pool_sol]
    df = df[df["winning_outcome"].notna()]
    df = df[df["implied_yes_close"].notna()]
    print(f"after filters: {len(df):,}  (min_pool={args.min_pool_sol} SOL, "
          f"status in {args.status_include})")

    if len(df) == 0:
        print("nothing to analyze"); return 1

    df["yes"] = (df["winning_outcome"] == 0).astype(int)  # 0=YES per decoded enum
    df["bucket"] = df["implied_yes_close"].apply(bucket_label)
    df["bucket_mid"] = df["implied_yes_close"].apply(bucket_mid)

    corr = df["implied_yes_close"].corr(df["yes"])

    def summarize(sub: pd.DataFrame) -> list[dict]:
        g = (sub.groupby("bucket")
                .agg(n=("yes", "size"), yes_rate=("yes", "mean"),
                     mid=("bucket_mid", "mean"))
                .reset_index()
                .sort_values("bucket"))
        g["deviation"] = g["yes_rate"] - g["mid"]
        g["z"] = g.apply(lambda r: zscore(r["yes_rate"], r["mid"], int(r["n"])), axis=1)
        return g.to_dict(orient="records")

    overall = summarize(df)
    sports = summarize(df[df["category"] == "sports"])
    nonsports = summarize(df[df["category"] != "sports"])

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "venue": "baozi",
        "n_resolved_markets": int(len(df)),
        "corr_price_yes": float(corr) if not pd.isna(corr) else None,
        "snapshot": "close (T-0), final pool ratio",
        "methodology_caveat": "Not directly comparable to Polymarket T-7d; "
            "Baozi at-close typically contains more info, so FLB should be "
            "weaker than T-7d baseline. If Baozi close FLB > PM T-7d FLB, "
            "that is a STRONG pari-mutuel signal.",
        "by_bucket_all": overall,
        "by_bucket_sports": sports,
        "by_bucket_non_sports": nonsports,
    }
    Path(args.out_json).write_text(json.dumps(out, indent=2, default=str))
    print(f"wrote {args.out_json}")

    print(f"\n=== BAOZI FLB AT-CLOSE (n={len(df):,}  corr={corr:+.4f}) ===")
    print(f"  {'bucket':<12} {'n':>5}  {'mid':>5}  {'yes_rate':>9}  {'dev':>7}  {'z':>5}")
    for r in overall:
        if r["n"] >= 3:
            print(f"  {r['bucket']:<12} {int(r['n']):>5,}  {r['mid']:>5.3f}  "
                  f"{r['yes_rate']:>9.3f}  {r['deviation']:>+7.3f}  {r['z']:>5.2f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
