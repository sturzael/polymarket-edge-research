"""FLB calibration on Betfair Australian thoroughbred racing.

Horse racing is the classic FLB testbed (Thaler+Ziemba 1988, Ali 1977).
Betfair publishes monthly ANZ thoroughbred CSVs with BSP (Betfair Starting
Price) and preplay weighted average prices — both standard academic anchors.

Schema per runner:
  WIN_RESULT: "WINNER" | "LOSER"
  WIN_BSP: decimal odds at race start
  WIN_PREPLAY_WEIGHTED_AVERAGE_PRICE_TAKEN: VWAP over the entire preplay period
  WIN_PREPLAY_LAST_PRICE_TAKEN: last price before race starts
  BEST_AVAIL_BACK_AT_SCHEDULED_OFF / BEST_AVAIL_LAY_AT_SCHEDULED_OFF: top of book
  WIN_BSP_VOLUME: liquidity at BSP

Methodology:
  - Bucket by implied_p = 1 / decimal_odds at each anchor
  - yes_rate = fraction resolving WINNER
  - Filter: WIN_BSP_VOLUME >= 100 (exclude illiquid runners)
  - 5pp buckets, binomial SE z-score
  - Overround per race should sum to >1.0 (fair overround); filter egregious anomalies

We run the calibration at each anchor separately to triangulate the bias.
"""
from __future__ import annotations
import json, math, pathlib
import pandas as pd
import numpy as np

DATA = pathlib.Path(__file__).parent.parent / "data"
RAW = DATA / "raw"

def bucket_label(p: float) -> str:
    for i in range(0, 20):
        lo, hi = i*0.05, (i+1)*0.05
        if lo <= p < hi:
            return f"{lo:.2f}-{hi:.2f}"
    return "0.95-1.00"

def bucket_mid(p: float) -> float:
    for i in range(0, 20):
        lo, hi = i*0.05, (i+1)*0.05
        if lo <= p < hi:
            return lo + 0.025
    return 0.975


def calibrate(df: pd.DataFrame, price_col: str, min_volume: float = 100.0, label: str = ""):
    df = df[df["WIN_BSP_VOLUME"].notna() & (df["WIN_BSP_VOLUME"] >= min_volume)].copy()
    df = df[df[price_col].notna() & (df[price_col] > 1.0) & (df[price_col] < 1000.0)]
    df["implied_p"] = 1.0 / df[price_col]
    # Remove degenerate
    df = df[(df["implied_p"] > 0.0) & (df["implied_p"] < 1.0)]
    df["is_winner"] = (df["WIN_RESULT"].astype(str).str.upper() == "WINNER").astype(int)
    df["bucket"] = df["implied_p"].apply(bucket_label)
    df["mid"] = df["implied_p"].apply(bucket_mid)
    if len(df) < 100:
        return None
    g = df.groupby("bucket").agg(n=("is_winner","size"),
                                   yes_rate=("is_winner","mean"),
                                   mid=("mid","mean")).reset_index().sort_values("bucket")
    g["deviation"] = g["yes_rate"] - g["mid"]
    g["se"] = np.sqrt(g["mid"] * (1 - g["mid"]) / g["n"])
    g["z"] = g["deviation"] / g["se"]
    return {
        "label": label,
        "price_col": price_col,
        "min_volume": min_volume,
        "n_total": int(len(df)),
        "n_races": int(df["WIN_MARKET_ID"].nunique()),
        "corr_p_y": round(float(df["implied_p"].corr(df["is_winner"])), 4),
        "buckets": g.to_dict(orient="records"),
    }


def print_cal(cal, label=""):
    if not cal:
        return
    print(f"\n=== {label}  n={cal['n_total']:,}  races={cal['n_races']:,}  corr={cal['corr_p_y']:+.4f} ===")
    print(f"  {'bucket':<12} {'n':>6}  {'mid':>5}  {'yes_rate':>8}  {'dev':>7}  {'z':>6}")
    for b in cal["buckets"]:
        if b["n"] >= 10:
            marker = " ***" if abs(b["z"]) >= 2 else ""
            print(f"  {b['bucket']:<12} {int(b['n']):>6,}  {b['mid']:>5.3f}  "
                  f"{b['yes_rate']:>8.3f}  {b['deviation']:>+7.3f}  {b['z']:>+6.2f}{marker}")


def main():
    frames = []
    for path in sorted(RAW.glob("ANZ_Thoroughbreds_*.csv")):
        try:
            df = pd.read_csv(path, low_memory=False, encoding="utf-8-sig")
        except Exception as e:
            print(f"  [ERR] {path.name}: {e}")
            continue
        df["__file"] = path.name
        frames.append(df)
        print(f"  {path.name}: {len(df):,} runners")
    if not frames:
        print("no files")
        return
    allrun = pd.concat(frames, ignore_index=True)
    print(f"\ntotal runners: {len(allrun):,}")
    print(f"races: {allrun['WIN_MARKET_ID'].nunique():,}")

    results = {}
    for price_col, label in [
        ("WIN_BSP", "Betfair Starting Price (BSP)"),
        ("WIN_PREPLAY_WEIGHTED_AVERAGE_PRICE_TAKEN", "preplay VWAP"),
        ("WIN_PREPLAY_LAST_PRICE_TAKEN", "last preplay"),
        ("WIN_PREPLAY_MAX_PRICE_TAKEN", "preplay max"),
        ("WIN_PREPLAY_MIN_PRICE_TAKEN", "preplay min"),
        ("BEST_AVAIL_BACK_AT_SCHEDULED_OFF", "best back at off"),
    ]:
        for min_vol in [0.0, 100.0, 1000.0]:
            cal = calibrate(allrun, price_col, min_volume=min_vol, label=f"{label}  vol>={min_vol:.0f}")
            if cal:
                results[f"{price_col}_vol{min_vol:.0f}"] = cal
                print_cal(cal, f"{label}  vol>={min_vol:.0f}")

    (DATA / "calibration_racing.json").write_text(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()
