"""Fixed-time-to-close calibration (no VWAP, no path-dependence).

For each resolved market, find trades in a narrow window around T-7d (where
T = end_date). Compute the average price AT THAT MOMENT. Bucket + resolve.

Why this matters: the 24h-VWAP calibration from 04_gamma_calibration.py
inflates high-bucket yes_rate because markets captured with 24h-VWAP of 0.68
may have been 0.55 most of the window and 1.0 at close (mid-trajectory).
A fixed-time snapshot at T-7d measures market belief at one fixed moment,
not a trajectory.

Window: ±12h around (end_ts - 7 days). Requires trades in that window.
Markets with fewer than 3 trades in that window are excluded — they weren't
actively priced at T-7d, so any snapshot is meaningless.

Inputs:  data/01_markets_audit.parquet
Outputs: data/05_tm7d_prices.parquet
         data/05_tm7d_calibration.json

Usage:
    uv run python -m experiments.e16_calibration_study.05_fixed_time_calibration \\
        --per-category 150 --offset-days 7 --window-hours 12
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
OUT_PARQUET = DATA_DIR / "05_tm7d_prices.parquet"
OUT_JSON = DATA_DIR / "05_tm7d_calibration.json"

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


def fetch_trades_near(client: httpx.Client, condition_id: str,
                       target_ts: int, window_hours: int,
                       max_pages: int = 10) -> list[dict]:
    """Fetch taker trades; paginate from most-recent backward until we've gone
    past (target_ts - window_hours). Filter client-side to ±window_hours around
    target_ts."""
    out = []
    offset = 0
    start_ts = target_ts - window_hours * 3600
    end_ts = target_ts + window_hours * 3600
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
        for t in batch:
            ts = int(t.get("timestamp", 0))
            if start_ts <= ts <= end_ts:
                out.append(t)
        if len(batch) < 500:
            break
        # Earliest trade in this batch; if already past our start, stop
        if batch and int(batch[-1].get("timestamp", 0)) < start_ts:
            break
        offset += 500
    return out


def snapshot_price(trades: list[dict]) -> dict | None:
    if len(trades) < 3:
        return None
    yes_prices = []
    sizes = []
    usd_notionals = []
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
        # USD notional = shares × actual price paid (always in 0-1 range)
        actual_price = float(t["price"])  # price of whichever token traded
        usd_notionals.append(s * actual_price)
    if len(yes_prices) < 3:
        return None
    if sum(sizes) > 0:
        price = sum(p * s for p, s in zip(yes_prices, sizes)) / sum(sizes)
    else:
        price = sum(yes_prices) / len(yes_prices)
    total_usd = sum(usd_notionals)
    max_usd = max(usd_notionals) if usd_notionals else 0.0
    # Compute median size+usd for "typical single-fill capacity"
    sorted_usd = sorted(usd_notionals)
    median_usd = sorted_usd[len(sorted_usd) // 2] if sorted_usd else 0.0
    return {
        "price_tm7d": round(price, 5),
        "n_trades_window": len(yes_prices),
        "total_usd_window": round(total_usd, 2),
        "max_single_trade_usd": round(max_usd, 2),
        "median_trade_usd": round(median_usd, 2),
    }


def sample_markets(audit: pd.DataFrame, per_category: int,
                   min_volume: float, min_duration_days: float,
                   categories: list[str] | None = None) -> pd.DataFrame:
    """Must have ≥min_duration_days between created_at and end_date so T-7d
    is within the market's active window."""
    audit = audit.copy()
    audit["duration_days"] = (audit["end_date"] - audit["created_at"]
                              ).dt.total_seconds() / 86400.0
    if categories:
        audit = audit[audit["category"].isin(categories)]
    rows = []
    for cat, g in audit.groupby("category"):
        g2 = g[(g["volume"] >= min_volume)
               & (g["duration_days"] >= min_duration_days)]
        if len(g2) == 0:
            continue
        n = min(per_category, len(g2))
        rows.append(g2.sample(n=n, random_state=42))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-category", type=int, default=150)
    ap.add_argument("--offset-days", type=float, default=7.0,
                    help="snapshot at end_date - offset_days")
    ap.add_argument("--window-hours", type=int, default=12,
                    help="±window_hours around the snapshot target")
    ap.add_argument("--min-volume", type=float, default=5_000)
    ap.add_argument("--categories", nargs="*", default=None,
                    help="restrict to specified categories (e.g. sports_nba sports_nfl ...)")
    ap.add_argument("--output-suffix", default="",
                    help="append to output filenames to avoid overwriting")
    args = ap.parse_args()

    # Markets need duration > offset_days + some slack for T-7d to be meaningful
    min_duration = args.offset_days + 1.0

    audit = pd.read_parquet(DATA_DIR / "01_markets_audit.parquet")
    print(f"audit: {len(audit):,} resolved markets")
    sample = sample_markets(audit, args.per_category, args.min_volume, min_duration,
                             categories=args.categories)
    scope = ",".join(args.categories) if args.categories else "all"
    print(f"sample: {len(sample):,} markets (duration>={min_duration:.0f}d, "
          f"volume>=${args.min_volume:.0f}, scope={scope})")

    suffix = args.output_suffix
    out_parquet = DATA_DIR / f"05_tm7d_prices{suffix}.parquet"
    out_json = DATA_DIR / f"05_tm7d_calibration{suffix}.json"

    records = []
    t0 = time.time()
    with httpx.Client() as client:
        for i, row in enumerate(sample.iterrows()):
            _, row = row
            ed = row["end_date"]
            end_ts = int(ed.timestamp()) if hasattr(ed, "timestamp") else int(ed)
            target_ts = end_ts - int(args.offset_days * 86400)
            trades = fetch_trades_near(client, row["condition_id"], target_ts,
                                        args.window_hours)
            snap = snapshot_price(trades)
            if snap:
                records.append({
                    "condition_id": row["condition_id"],
                    "slug": row["slug"],
                    "category": row["category"],
                    "resolution": row["resolution"],
                    "volume": float(row["volume"]),
                    "duration_days": float(row["duration_days"]),
                    **snap,
                })
            if (i + 1) % 50 == 0:
                rate = (i + 1) / (time.time() - t0) if time.time() > t0 else 0
                kept = len(records)
                print(f"  progress: {i+1}/{len(sample)}  kept={kept}  "
                      f"({rate:.1f}/s)", flush=True)

    df = pd.DataFrame(records)
    df.to_parquet(out_parquet, index=False)
    print(f"\nwrote {out_parquet} — {len(df):,} markets with T-{args.offset_days:.0f}d snapshot")

    if len(df) == 0:
        print("no data")
        return 1

    df["bucket"] = df["price_tm7d"].apply(bucket_label)
    df["bucket_mid"] = df["price_tm7d"].apply(bucket_mid)
    df["yes"] = (df["resolution"] == "YES").astype(int)

    corr = df["price_tm7d"].corr(df["yes"])
    overall = (df.groupby("bucket")
                 .agg(n=("yes", "size"),
                      yes_rate=("yes", "mean"),
                      mid=("bucket_mid", "mean"))
                 .reset_index()
                 .sort_values("bucket"))
    overall["deviation"] = overall["yes_rate"] - overall["mid"]

    cat_grouped = (df.groupby(["category", "bucket"])
                     .agg(n=("yes", "size"),
                          yes_rate=("yes", "mean"),
                          mid=("bucket_mid", "mean"))
                     .reset_index())
    cat_grouped["deviation"] = cat_grouped["yes_rate"] - cat_grouped["mid"]

    out_json.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "offset_days": args.offset_days,
        "window_hours": args.window_hours,
        "n_markets": int(len(df)),
        "corr_price_yes": round(float(corr), 4),
        "overall_by_bucket": overall.to_dict(orient="records"),
        "by_category_bucket": cat_grouped.to_dict(orient="records"),
    }, indent=2, default=str))

    print(f"\n=== T-{args.offset_days:.0f}d CALIBRATION (n={len(df):,}  corr={corr:+.4f}) ===")
    print(f"  {'bucket':<12} {'n':>5}  {'mid':>5}  {'yes_rate':>9}  {'dev':>7}")
    for _, r in overall.iterrows():
        print(f"  {r['bucket']:<12} {int(r['n']):>5,}  {r['mid']:>5.3f}  "
              f"{r['yes_rate']:>9.3f}  {r['deviation']:>+7.3f}")

    # Non-sports subset
    ns = df[~df["category"].str.startswith("sports_")]
    if len(ns) >= 100:
        print(f"\n=== NON-SPORTS SUBSET (n={len(ns):,}) ===")
        ns_overall = (ns.groupby("bucket")
                        .agg(n=("yes","size"), yes_rate=("yes","mean"),
                             mid=("bucket_mid","mean")).reset_index()
                        .sort_values("bucket"))
        ns_overall["deviation"] = ns_overall["yes_rate"] - ns_overall["mid"]
        print(f"  {'bucket':<12} {'n':>4}  {'mid':>5}  {'yes_rate':>8}  {'dev':>7}")
        for _, r in ns_overall.iterrows():
            if r["n"] >= 5:
                print(f"  {r['bucket']:<12} {int(r['n']):>4,}  {r['mid']:>5.3f}  "
                      f"{r['yes_rate']:>8.3f}  {r['deviation']:>+7.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
