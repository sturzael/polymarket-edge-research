"""Calibration via gamma /trades endpoint (authoritative prices).

Bypasses the SII orderfilled decoding ambiguity. Per-market, fetches a small
page of actual trades around close, computes a pre-close VWAP already in
correct YES-equivalent form (using gamma's `outcomeIndex` field), buckets,
aggregates.

Sample: stratified by category, target 500-1500 markets. Pickups hit gamma at
~1 req/50ms (20 req/s, well under 4000/10s limit).

Inputs: data/01_markets_audit.parquet (condition_id, category, resolution,
        end_date, volume)

Output: data/04_gamma_prices.parquet  (one row per sampled market with real VWAP)
        data/04_calibration_gamma.json (aggregated table)

Usage:
    uv run python -m experiments.e16_calibration_study.04_gamma_calibration \\
        --per-category 80 --window-hours 24
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
OUT_PARQUET = DATA_DIR / "04_gamma_prices.parquet"
OUT_JSON = DATA_DIR / "04_calibration_gamma.json"

DATA_API = "https://data-api.polymarket.com"

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


def fetch_trades(client: httpx.Client, condition_id: str,
                 end_ts: int, window_hours: int = 24,
                 max_pages: int = 3) -> list[dict]:
    """Fetch taker trades for a market. Filters to last window_hours before end_ts
    by timestamp client-side (endpoint has no time filter)."""
    out = []
    offset = 0
    start_ts = end_ts - window_hours * 3600
    for _ in range(max_pages):
        try:
            r = client.get(
                f"{DATA_API}/trades",
                params={"takerOnly": "true", "market": condition_id,
                        "limit": 500, "offset": offset},
                timeout=15,
            )
        except Exception:
            return out
        if r.status_code != 200:
            return out
        batch = r.json()
        if not batch:
            break
        kept = [t for t in batch
                if start_ts <= int(t.get("timestamp", 0)) <= end_ts + 3600]
        out.extend(kept)
        if len(batch) < 500:
            break
        # gamma returns most-recent first; if we've gone past window, stop
        if batch and int(batch[-1].get("timestamp", 0)) < start_ts:
            break
        offset += 500
    return out


def aggregate_market(trades: list[dict]) -> dict | None:
    """YES-equivalent VWAP. outcomeIndex=0 → price of YES side; =1 → price of NO side
    which we invert to YES."""
    if not trades:
        return None
    yes_prices = []
    sizes = []
    for t in trades:
        try:
            p = float(t["price"])
            s = float(t.get("size") or 0)
            idx = int(t.get("outcomeIndex", 0))
        except Exception:
            continue
        if not (0 < p <= 1.0):
            continue
        if idx == 1:
            p = 1.0 - p
        yes_prices.append(p)
        sizes.append(s)
    if not yes_prices:
        return None
    if sum(sizes) > 0:
        vwap = sum(p * s for p, s in zip(yes_prices, sizes)) / sum(sizes)
    else:
        vwap = sum(yes_prices) / len(yes_prices)
    last_price = yes_prices[0]  # gamma returns most-recent-first; idx 0 is latest
    return {"vwap": round(vwap, 5), "last_price": round(last_price, 5),
            "n_trades": len(yes_prices)}


def sample_markets(audit: pd.DataFrame, per_category: int,
                   min_volume: float = 5_000, min_end_date: str = "2024-06-01") -> pd.DataFrame:
    """Stratified random sample across categories. Avoids the top-volume bias
    (those markets mostly settle decisively, giving all-or-nothing VWAPs).
    We want ambiguous middle-bucket markets too."""
    rows = []
    for cat, g in audit.groupby("category"):
        g2 = g[(g["volume"] >= min_volume) & (g["end_date"] >= min_end_date)]
        if len(g2) == 0:
            continue
        n = min(per_category, len(g2))
        rows.append(g2.sample(n=n, random_state=42))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-category", type=int, default=80)
    ap.add_argument("--window-hours", type=int, default=24)
    args = ap.parse_args()

    audit = pd.read_parquet(DATA_DIR / "01_markets_audit.parquet")
    print(f"audit: {len(audit):,} resolved markets")

    sample = sample_markets(audit, args.per_category)
    print(f"sample: {len(sample):,} markets "
          f"({args.per_category} per category, volume>=$1k)")

    records = []
    t0 = time.time()
    with httpx.Client() as client:
        for i, row in sample.iterrows():
            ed = row["end_date"]
            end_ts = int(ed.timestamp()) if hasattr(ed, "timestamp") else int(ed)
            trades = fetch_trades(client, row["condition_id"], end_ts,
                                   window_hours=args.window_hours)
            agg = aggregate_market(trades)
            if agg:
                records.append({
                    "condition_id": row["condition_id"],
                    "slug": row["slug"],
                    "category": row["category"],
                    "resolution": row["resolution"],
                    "volume": float(row["volume"]),
                    **agg,
                })
            if (len(records) + 1) % 50 == 0:
                rate = len(records) / (time.time() - t0) if time.time() > t0 else 0
                print(f"  progress: {len(records)}/{len(sample)} "
                      f"({rate:.1f}/s)", flush=True)

    df = pd.DataFrame(records)
    df.to_parquet(OUT_PARQUET, index=False)
    print(f"wrote {OUT_PARQUET} — {len(df):,} markets with gamma trades")

    if len(df) == 0:
        print("no data collected")
        return 1

    df["bucket"] = df["vwap"].apply(bucket_label)
    df["bucket_mid"] = df["vwap"].apply(bucket_mid)
    df["yes"] = (df["resolution"] == "YES").astype(int)

    # Overall
    overall = (df.groupby("bucket")
                 .agg(n=("yes", "size"),
                      yes_rate=("yes", "mean"),
                      bucket_mid=("bucket_mid", "mean"))
                 .reset_index()
                 .sort_values("bucket"))
    overall["deviation"] = overall["yes_rate"] - overall["bucket_mid"]

    # Correlation
    corr = df["vwap"].corr(df["yes"])

    # Per-category
    cat_grouped = (df.groupby(["category", "bucket"])
                     .agg(n=("yes", "size"),
                          yes_rate=("yes", "mean"),
                          bucket_mid=("bucket_mid", "mean"),
                          total_volume=("volume", "sum"))
                     .reset_index())
    cat_grouped["deviation"] = cat_grouped["yes_rate"] - cat_grouped["bucket_mid"]
    cat_grouped["abs_deviation"] = cat_grouped["deviation"].abs()
    actionable = cat_grouped[cat_grouped["n"] >= 15].sort_values("abs_deviation",
                                                                  ascending=False).head(30)

    OUT_JSON.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_markets": int(len(df)),
        "corr_vwap_yes": round(float(corr), 4),
        "overall": overall.to_dict(orient="records"),
        "top_actionable": actionable.to_dict(orient="records"),
    }, indent=2, default=str))

    print(f"\n=== GAMMA-CALIBRATION (n={len(df):,}  corr={corr:+.4f}) ===")
    print(f"  {'bucket':<12} {'n':>5}  {'mid':>5}  {'yes_rate':>8}  {'dev':>7}")
    for _, r in overall.iterrows():
        print(f"  {r['bucket']:<12} {int(r['n']):>5,}  {r['bucket_mid']:>5.2f}  "
              f"{r['yes_rate']:>8.3f}  {r['deviation']:>+7.3f}")

    print(f"\n=== TOP CATEGORY-BUCKET DEVIATIONS (n>=15) ===")
    for _, r in actionable.iterrows():
        print(f"  {r['category']:<22} {r['bucket']:<12} n={int(r['n']):>4,}  "
              f"mid={r['bucket_mid']:.2f}  yes_rate={r['yes_rate']:.3f}  "
              f"dev={r['deviation']:>+6.3f}  vol=${r['total_volume']:>10,.0f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
