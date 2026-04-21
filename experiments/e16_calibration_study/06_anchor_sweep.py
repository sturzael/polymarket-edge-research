"""Anchor-curve sweep: re-anchor the sports-deep sample at multiple T-minus points.

Fixes the market universe to the 2,025 sports markets from
`05_tm7d_prices_sports_deep.parquet` (measured +25.8pp FLB at 0.55-0.60, T-7d)
and computes the T-minus calibration at four additional anchors so we can see
whether the bias is stable across the market's life or collapses near close.

Anchors computed:
  T-3d    (±12h window)
  T-1d    (±6h  window)
  T-60min (±15min window)
  T-10min (±5min window)

Why this design:
  The existing 05 script randomly samples per category and requires duration >=
  offset_days + 1, so re-running it at different offsets produces different
  market universes — not apples-to-apples. This script pins the universe.

  Short anchors need float window_hours, which 05 didn't support.

Outputs (under `data/anchor_curve/`):
  anchor_t{X}_prices.parquet       — per-market snapshot at anchor X
  anchor_t{X}_calibration.json     — bucket table + sports-aggregate stats
  anchor_curve_summary.json        — side-by-side 0.55-0.60 bucket across all 5 anchors
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
OUT_DIR = DATA_DIR / "anchor_curve"
OUT_DIR.mkdir(exist_ok=True)

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


def snapshot_price(trades: list[dict]) -> dict | None:
    """VWAP snapshot with YES-equivalent prices (mirrors 05_fixed_time_calibration.py)."""
    if len(trades) < 3:
        return None
    yes_prices, sizes, usd_notionals = [], [], []
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
        usd_notionals.append(s * float(t["price"]))
    if len(yes_prices) < 3:
        return None
    if sum(sizes) > 0:
        price = sum(p * s for p, s in zip(yes_prices, sizes)) / sum(sizes)
    else:
        price = sum(yes_prices) / len(yes_prices)
    sorted_usd = sorted(usd_notionals)
    return {
        "price_tm7d": round(price, 5),
        "n_trades_window": len(yes_prices),
        "total_usd_window": round(sum(usd_notionals), 2),
        "max_single_trade_usd": round(max(usd_notionals) if usd_notionals else 0.0, 2),
        "median_trade_usd": round(sorted_usd[len(sorted_usd) // 2] if sorted_usd else 0.0, 2),
    }

ANCHORS: list[tuple[str, float, float]] = [
    # (label, offset_days, window_hours)
    ("t3d",    3.0,      12.0),
    ("t1d",    1.0,       6.0),
    ("t60min", 60/1440,   0.25),   # 60 min offset, ±15 min window
    ("t10min", 10/1440,   0.1),    # 10 min offset, ±6 min window
]


def fetch_trades_near_float(client: httpx.Client, condition_id: str,
                             target_ts: int, window_hours: float,
                             max_pages: int = 10) -> list[dict]:
    """Like fetch_trades_near in 05 but accepts float window_hours."""
    out: list[dict] = []
    offset = 0
    window_s = int(window_hours * 3600)
    start_ts = target_ts - window_s
    end_ts = target_ts + window_s
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
        if batch and int(batch[-1].get("timestamp", 0)) < start_ts:
            break
        offset += 500
    return out


def build_universe() -> pd.DataFrame:
    """Join sports-deep parquet with audit to get end_date for each market."""
    deep = pd.read_parquet(DATA_DIR / "05_tm7d_prices_sports_deep.parquet")
    audit = pd.read_parquet(DATA_DIR / "01_markets_audit.parquet")[
        ["condition_id", "end_date", "created_at"]
    ]
    uni = deep.merge(audit, on="condition_id", how="left")
    missing = uni["end_date"].isna().sum()
    if missing:
        print(f"  dropping {missing} rows with no end_date")
        uni = uni.dropna(subset=["end_date"])
    print(f"universe: {len(uni):,} sports markets "
          f"({uni['category'].nunique()} sports)")
    return uni


def run_anchor(client: httpx.Client, universe: pd.DataFrame,
                label: str, offset_days: float, window_hours: float) -> pd.DataFrame:
    print(f"\n=== anchor {label}: offset={offset_days:g}d, window=±{window_hours:g}h ===")
    records: list[dict] = []
    t0 = time.time()
    offset_s = int(offset_days * 86400)
    for i, row in enumerate(universe.itertuples()):
        ed = row.end_date
        end_ts = int(ed.timestamp()) if hasattr(ed, "timestamp") else int(ed)
        target_ts = end_ts - offset_s
        trades = fetch_trades_near_float(client, row.condition_id, target_ts,
                                          window_hours)
        snap = snapshot_price(trades)
        if snap:
            records.append({
                "condition_id": row.condition_id,
                "slug": row.slug,
                "category": row.category,
                "resolution": row.resolution,
                "volume": float(row.volume),
                "duration_days": float(row.duration_days),
                "price_tm7d_original": float(row.price_tm7d),
                **{k.replace("_tm7d", f"_{label}"): v for k, v in snap.items()},
            })
        if (i + 1) % 100 == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            kept = len(records)
            print(f"  {i+1}/{len(universe)}  kept={kept}  "
                  f"rate={rate:.1f}/s  elapsed={elapsed:.0f}s", flush=True)
    df = pd.DataFrame(records)
    out_parquet = OUT_DIR / f"anchor_{label}_prices.parquet"
    df.to_parquet(out_parquet, index=False)
    print(f"  wrote {out_parquet} — {len(df):,} markets with {label} snapshot")
    return df


def summarize_anchor(df: pd.DataFrame, label: str, offset_days: float,
                     window_hours: float) -> dict:
    if df.empty:
        return {"label": label, "offset_days": offset_days, "n_markets": 0}

    price_col = f"price_{label}"
    df = df.copy()
    df["bucket"] = df[price_col].apply(bucket_label)
    df["bucket_mid"] = df[price_col].apply(bucket_mid)
    df["yes"] = (df["resolution"] == "YES").astype(int)

    corr = df[price_col].corr(df["yes"])
    overall = (df.groupby("bucket")
                 .agg(n=("yes", "size"),
                      yes_rate=("yes", "mean"),
                      mid=("bucket_mid", "mean"))
                 .reset_index()
                 .sort_values("bucket"))
    overall["deviation"] = overall["yes_rate"] - overall["mid"]
    overall["z"] = overall.apply(
        lambda r: (r["deviation"] / ((r["mid"] * (1 - r["mid"]) / r["n"]) ** 0.5))
                   if r["n"] > 0 and 0 < r["mid"] < 1 else 0.0, axis=1)

    cat_bucket = (df.groupby(["category", "bucket"])
                    .agg(n=("yes", "size"),
                         yes_rate=("yes", "mean"),
                         mid=("bucket_mid", "mean"))
                    .reset_index())
    cat_bucket["deviation"] = cat_bucket["yes_rate"] - cat_bucket["mid"]

    out = {
        "label": label,
        "offset_days": offset_days,
        "window_hours": window_hours,
        "n_markets": int(len(df)),
        "corr_price_yes": round(float(corr), 4),
        "overall_by_bucket": overall.to_dict(orient="records"),
        "by_category_bucket": cat_bucket.to_dict(orient="records"),
    }
    out_json = OUT_DIR / f"anchor_{label}_calibration.json"
    out_json.write_text(json.dumps(out, indent=2, default=str))
    print(f"  wrote {out_json}")

    # Print the critical bucket
    crit = overall[overall["bucket"] == "0.55-0.60"]
    if not crit.empty:
        r = crit.iloc[0]
        print(f"  0.55-0.60 bucket: n={int(r['n'])}  yes_rate={r['yes_rate']:.3f}  "
              f"dev={r['deviation']:+.3f}  z={r['z']:+.2f}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None,
                    help="only run these anchors (e.g. t3d t1d)")
    args = ap.parse_args()

    universe = build_universe()

    summaries: list[dict] = []
    with httpx.Client() as client:
        for label, offset_days, window_hours in ANCHORS:
            if args.only and label not in args.only:
                continue
            df = run_anchor(client, universe, label, offset_days, window_hours)
            summaries.append(summarize_anchor(df, label, offset_days, window_hours))

    # Combined summary: 0.55-0.60 bucket across all 5 anchors (including T-7d from the input)
    # Pull T-7d baseline from the sports-deep parquet.
    deep = pd.read_parquet(DATA_DIR / "05_tm7d_prices_sports_deep.parquet")
    deep["bucket"] = deep["price_tm7d"].apply(bucket_label)
    deep["bucket_mid"] = deep["price_tm7d"].apply(bucket_mid)
    deep["yes"] = (deep["resolution"] == "YES").astype(int)
    t7_crit = deep[deep["bucket"] == "0.55-0.60"]
    t7_n = int(len(t7_crit))
    t7_yes = float(t7_crit["yes"].mean()) if t7_n else None
    t7_dev = (t7_yes - 0.575) if t7_yes is not None else None

    curve = [{
        "anchor": "t7d", "offset_days": 7.0, "window_hours": 12.0,
        "n_markets": int(len(deep)),
        "bucket_0.55_0.60": {"n": t7_n, "yes_rate": t7_yes,
                              "deviation": t7_dev},
    }]
    for s in summaries:
        crit = [b for b in s["overall_by_bucket"] if b["bucket"] == "0.55-0.60"]
        c = crit[0] if crit else {"n": 0, "yes_rate": None, "deviation": None}
        curve.append({
            "anchor": s["label"], "offset_days": s["offset_days"],
            "window_hours": s["window_hours"],
            "n_markets": s["n_markets"],
            "bucket_0.55_0.60": {"n": int(c["n"]),
                                  "yes_rate": c.get("yes_rate"),
                                  "deviation": c.get("deviation")},
        })

    summary_json = OUT_DIR / "anchor_curve_summary.json"
    summary_json.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "universe": "05_tm7d_prices_sports_deep.parquet (n=2025 sports)",
        "critical_bucket": "0.55-0.60",
        "curve": curve,
    }, indent=2, default=str))
    print(f"\nwrote {summary_json}")

    print("\n=== ANCHOR CURVE at 0.55-0.60 bucket ===")
    print(f"  {'anchor':<8} {'n(all)':>7}  {'n(bucket)':>9}  {'yes_rate':>9}  {'dev':>8}")
    for row in curve:
        b = row["bucket_0.55_0.60"]
        yr = f"{b['yes_rate']:.3f}" if b["yes_rate"] is not None else "n/a"
        dv = f"{b['deviation']:+.3f}" if b["deviation"] is not None else "n/a"
        print(f"  {row['anchor']:<8} {row['n_markets']:>7,}  {b['n']:>9,}  "
              f"{yr:>9}  {dv:>8}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
