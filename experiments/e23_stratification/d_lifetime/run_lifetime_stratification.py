"""Agent D — market lifetime stratification of the T-7d FLB in sports.

Tiers (by total market lifespan = end_date - created_at):
  - short:  duration_days <= 14
  - medium: 14 < duration_days <= 30
  - long:   duration_days > 30

At T-7d a market with duration D has existed for (D - 7) days. Longer-lived
markets have had more wall-clock time to incorporate informed flow before
our snapshot; shorter-lived ones had not. If FLB concentrates in short-lived
markets, it's an early-flow artifact (hasn't corrected yet). If it persists
in long-lived markets, that's stronger evidence for durable mispricing.

Input:  experiments/e16_calibration_study/data/05_tm7d_prices_sports_deep.parquet
Output: experiments/e23_stratification/d_lifetime/data/lifetime_calibration.json
        experiments/e23_stratification/d_lifetime/data/lifetime_tiered.parquet
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "e16_calibration_study" / "data" / "05_tm7d_prices_sports_deep.parquet"
OUTDIR = Path(__file__).parent / "data"
OUTDIR.mkdir(parents=True, exist_ok=True)

OFFSET_DAYS = 7.0

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


def tier_label(d: float) -> str:
    if d <= 14.0:
        return "short"
    if d <= 30.0:
        return "medium"
    return "long"


def z_for_dev(yes_rate: float, mid: float, n: int) -> float:
    """Under H0: yes_rate == mid. SE = sqrt(mid*(1-mid)/n)."""
    if n <= 0:
        return 0.0
    se = math.sqrt(mid * (1.0 - mid) / n)
    if se == 0:
        return 0.0
    return (yes_rate - mid) / se


def calib_table(df: pd.DataFrame) -> list[dict]:
    if len(df) == 0:
        return []
    grouped = (df.groupby("bucket")
                 .agg(n=("yes", "size"),
                      yes_rate=("yes", "mean"),
                      mid=("bucket_mid", "mean"))
                 .reset_index()
                 .sort_values("bucket"))
    grouped["deviation"] = grouped["yes_rate"] - grouped["mid"]
    grouped["z"] = grouped.apply(
        lambda r: z_for_dev(r["yes_rate"], r["mid"], int(r["n"])),
        axis=1,
    )
    return grouped.to_dict(orient="records")


def summary_block(df: pd.DataFrame) -> dict:
    n = int(len(df))
    if n == 0:
        return {"n_markets": 0}
    dsc = (df["duration_days"] - OFFSET_DAYS)
    bucket_focus = df[(df["price_tm7d"] >= 0.55) & (df["price_tm7d"] < 0.60)]
    bf_n = int(len(bucket_focus))
    bf_yes = float(bucket_focus["yes"].mean()) if bf_n > 0 else float("nan")
    bf_dev = bf_yes - 0.575 if bf_n > 0 else float("nan")
    bf_z = z_for_dev(bf_yes, 0.575, bf_n) if bf_n > 0 else float("nan")
    corr = float(df["price_tm7d"].corr(df["yes"]))
    return {
        "n_markets": n,
        "corr_price_yes": round(corr, 4),
        "duration_days_mean": round(float(df["duration_days"].mean()), 2),
        "duration_days_median": round(float(df["duration_days"].median()), 2),
        "duration_days_min": round(float(df["duration_days"].min()), 2),
        "duration_days_max": round(float(df["duration_days"].max()), 2),
        "days_since_creation_at_snapshot_mean": round(float(dsc.mean()), 2),
        "days_since_creation_at_snapshot_median": round(float(dsc.median()), 2),
        "days_since_creation_at_snapshot_min": round(float(dsc.min()), 2),
        "days_since_creation_at_snapshot_max": round(float(dsc.max()), 2),
        "bucket_0p55_0p60": {
            "n": bf_n,
            "yes_rate": None if math.isnan(bf_yes) else round(bf_yes, 4),
            "deviation_pp": None if math.isnan(bf_dev) else round(bf_dev, 4),
            "z": None if math.isnan(bf_z) else round(bf_z, 3),
            "insufficient_sample": bf_n < 20,
        },
        "calibration": calib_table(df),
    }


def main() -> int:
    df = pd.read_parquet(INPUT)
    print(f"loaded {len(df):,} rows from {INPUT}")

    df = df.copy()
    df["yes"] = (df["resolution"] == "YES").astype(int)
    df["bucket"] = df["price_tm7d"].apply(bucket_label)
    df["bucket_mid"] = df["price_tm7d"].apply(bucket_mid)
    df["tier"] = df["duration_days"].apply(tier_label)
    df["days_since_creation_at_snapshot"] = df["duration_days"] - OFFSET_DAYS

    # Persist tiered parquet for inspection
    tiered_path = OUTDIR / "lifetime_tiered.parquet"
    df.to_parquet(tiered_path, index=False)
    print(f"wrote {tiered_path}")

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "offset_days": OFFSET_DAYS,
        "source_parquet": str(INPUT),
        "tier_definitions": {
            "short": "duration_days <= 14",
            "medium": "14 < duration_days <= 30",
            "long": "duration_days > 30",
        },
        "all_sports": summary_block(df),
        "tiers": {},
    }

    for name in ("short", "medium", "long"):
        sub = df[df["tier"] == name]
        block = summary_block(sub)
        out["tiers"][name] = block

    out_json = OUTDIR / "lifetime_calibration.json"
    out_json.write_text(json.dumps(out, indent=2, default=str))
    print(f"wrote {out_json}")

    # Print an at-a-glance table
    print()
    print("=== LIFETIME TIER OVERVIEW ===")
    print(f"{'tier':<8}{'n':>6}{'0.55-0.60 n':>13}{'yes_rate':>11}{'dev_pp':>9}{'z':>7}{'DSC med':>10}")
    for name in ("all_sports", "short", "medium", "long"):
        block = out["tiers"].get(name) if name != "all_sports" else out["all_sports"]
        if not block or block.get("n_markets", 0) == 0:
            continue
        bf = block.get("bucket_0p55_0p60", {})
        dsc_med = block.get("days_since_creation_at_snapshot_median", float("nan"))
        yr = bf.get("yes_rate")
        dv = bf.get("deviation_pp")
        z = bf.get("z")
        print(
            f"{name:<8}{block['n_markets']:>6}{bf.get('n',0):>13}"
            f"{(yr if yr is not None else float('nan')):>11.3f}"
            f"{(dv if dv is not None else float('nan')):>+9.3f}"
            f"{(z if z is not None else float('nan')):>+7.2f}"
            f"{dsc_med:>10.2f}"
        )

    print()
    print("=== PER-TIER CALIBRATION TABLES ===")
    for name in ("short", "medium", "long"):
        block = out["tiers"][name]
        n_total = block.get("n_markets", 0)
        print()
        print(f"--- tier={name}  n={n_total}  "
              f"DSC_median={block.get('days_since_creation_at_snapshot_median')}d ---")
        print(f"  {'bucket':<12}{'n':>5}{'mid':>7}{'yes_rate':>10}{'dev':>9}{'z':>7}")
        for r in block.get("calibration", []):
            if int(r["n"]) >= 3:
                print(f"  {r['bucket']:<12}{int(r['n']):>5}{r['mid']:>7.3f}"
                      f"{r['yes_rate']:>10.3f}{r['deviation']:>+9.3f}{r['z']:>+7.2f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
