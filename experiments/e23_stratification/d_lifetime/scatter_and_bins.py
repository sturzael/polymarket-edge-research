"""Supplementary analysis — deviation-vs-lifetime via a finer-grained split,
and (duration × price-bucket) heatmap aggregated at the 0.55-0.60 bucket.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "e16_calibration_study" / "data" / "05_tm7d_prices_sports_deep.parquet"
OUTDIR = Path(__file__).parent / "data"


def z_for_dev(yes_rate: float, mid: float, n: int) -> float:
    if n <= 0:
        return 0.0
    se = math.sqrt(mid * (1.0 - mid) / n)
    if se == 0:
        return 0.0
    return (yes_rate - mid) / se


def main() -> int:
    df = pd.read_parquet(INPUT)
    df = df.copy()
    df["yes"] = (df["resolution"] == "YES").astype(int)

    # Finer duration buckets
    bins = [(0, 8.5), (8.5, 10), (10, 12), (12, 14), (14, 21), (21, 30), (30, 60), (60, 1000)]
    rows = []
    for lo, hi in bins:
        sub = df[(df["duration_days"] > lo) & (df["duration_days"] <= hi)]
        b_all = sub  # across buckets
        b55 = sub[(sub["price_tm7d"] >= 0.55) & (sub["price_tm7d"] < 0.60)]
        # favorites bucket 0.50-0.80 (the lifted region)
        bfav = sub[(sub["price_tm7d"] >= 0.50) & (sub["price_tm7d"] < 0.80)]
        row = {
            "duration_range": f"{lo:g}-{hi:g}d",
            "n_total": int(len(b_all)),
            "n_0p55_0p60": int(len(b55)),
            "yes_rate_0p55_0p60": round(float(b55["yes"].mean()), 4) if len(b55) > 0 else None,
            "dev_0p55_0p60_pp": round(float(b55["yes"].mean() - 0.575), 4) if len(b55) > 0 else None,
            "z_0p55_0p60": round(z_for_dev(float(b55["yes"].mean()), 0.575, len(b55)), 3) if len(b55) > 0 else None,
            "n_favorites_0p50_0p80": int(len(bfav)),
            "yes_rate_favorites": round(float(bfav["yes"].mean()), 4) if len(bfav) > 0 else None,
            "dev_favorites_pp": round(float(bfav["yes"].mean() - 0.625), 4) if len(bfav) > 0 else None,
        }
        rows.append(row)

    out = {
        "source_parquet": str(INPUT),
        "note": "finer-grained duration bins and the 0.50-0.80 favorites aggregation",
        "bins": rows,
    }
    out_json = OUTDIR / "lifetime_bins_finer.json"
    out_json.write_text(json.dumps(out, indent=2))
    print(f"wrote {out_json}")
    print()
    print(f"{'duration':<12}{'n_total':>9}{'n_0p55':>8}{'yes_0p55':>10}{'dev_pp':>9}{'z':>7}"
          f"{'n_fav':>8}{'yes_fav':>10}{'dev_fav':>9}")
    for r in rows:
        dv = r.get("dev_0p55_0p60_pp")
        yr = r.get("yes_rate_0p55_0p60")
        zs = r.get("z_0p55_0p60")
        dvf = r.get("dev_favorites_pp")
        yrf = r.get("yes_rate_favorites")
        fmt_num = lambda v, sign=False, fmt="7.3f": (
            (f"{{:+{fmt}}}".format(v) if sign else f"{{:{fmt}}}".format(v))
            if v is not None else f"{'--':>{int(fmt.split('.')[0])}}"
        )
        print(
            f"{r['duration_range']:<12}{r['n_total']:>9}{r['n_0p55_0p60']:>8}"
            f"{(yr if yr is not None else float('nan')):>10.3f}"
            f"{(dv if dv is not None else float('nan')):>+9.3f}"
            f"{(zs if zs is not None else float('nan')):>+7.2f}"
            f"{r['n_favorites_0p50_0p80']:>8}"
            f"{(yrf if yrf is not None else float('nan')):>10.3f}"
            f"{(dvf if dvf is not None else float('nan')):>+9.3f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
