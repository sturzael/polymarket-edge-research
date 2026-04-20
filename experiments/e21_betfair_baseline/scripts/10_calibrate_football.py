"""FLB calibration on football-data.co.uk Betfair Exchange closing odds.

Columns:
  FTR = full-time result (H/D/A)
  BFEH, BFED, BFEA = Betfair Exchange closing decimal odds for home/draw/away
  BFECH, BFECD, BFECA = Betfair Exchange closing (alt version, sometimes consistent)

We'll use BFE* as "closing" odds (closest to pre-kickoff fixed-time anchor).
Each match yields 3 selections (home/draw/away), each with an implied prob and
a 0/1 outcome. This is our football equivalent of Betfair pre-kickoff.

For each (league, season) combine; then calibrate.
"""
from __future__ import annotations
import json, pathlib
import pandas as pd
import numpy as np

DATA = pathlib.Path(__file__).parent.parent / "data"
RAW = DATA / "raw_football"

def bucket_label(p):
    for i in range(0,20):
        lo, hi = i*0.05, (i+1)*0.05
        if lo <= p < hi:
            return f"{lo:.2f}-{hi:.2f}"
    return "0.95-1.00"

def bucket_mid(p):
    for i in range(0,20):
        lo, hi = i*0.05, (i+1)*0.05
        if lo <= p < hi:
            return lo + 0.025
    return 0.975


def load_all():
    frames = []
    for p in sorted(RAW.glob("*.csv")):
        try:
            # football-data has legacy latin-1 encoding issues sometimes
            df = pd.read_csv(p, encoding="latin-1", on_bad_lines="skip", low_memory=False)
        except Exception as e:
            print(f"  [ERR] {p.name}: {e}")
            continue
        df["__source"] = p.name
        league = p.stem.rsplit("_", 1)[0]
        df["__league"] = league
        frames.append(df)
    if not frames:
        return None
    return pd.concat(frames, ignore_index=True)


def to_selections(df: pd.DataFrame, col_h: str, col_d: str, col_a: str) -> pd.DataFrame:
    """Explode one row-per-match into three row-per-selection."""
    rows = []
    for _, row in df.iterrows():
        if pd.isna(row.get("FTR")):
            continue
        ftr = str(row["FTR"]).strip().upper()
        for outcome, colname in [("H", col_h), ("D", col_d), ("A", col_a)]:
            odds = row.get(colname)
            try:
                odds = float(odds)
            except Exception:
                continue
            # NaN fails comparison-based checks silently; test explicitly.
            import math as _math
            if odds is None or _math.isnan(odds) or odds <= 1.0 or odds > 1000:
                continue
            rows.append({
                "league": row.get("__league"),
                "source": row.get("__source"),
                "date": row.get("Date"),
                "outcome": outcome,
                "odds": odds,
                "implied_p": 1.0 / odds,
                "is_winner": int(ftr == outcome),
            })
    return pd.DataFrame(rows)


def calibrate(df, label=""):
    if len(df) < 100:
        return None
    df = df.copy()
    df["bucket"] = df["implied_p"].apply(bucket_label)
    df["mid"] = df["implied_p"].apply(bucket_mid)
    g = df.groupby("bucket").agg(n=("is_winner","size"),
                                  yes_rate=("is_winner","mean"),
                                  mid=("mid","mean")).reset_index().sort_values("bucket")
    g["deviation"] = g["yes_rate"] - g["mid"]
    g["se"] = np.sqrt(g["mid"] * (1 - g["mid"]) / g["n"])
    g["z"] = g["deviation"] / g["se"]
    return {
        "label": label,
        "n_total": int(len(df)),
        "corr": round(float(df["implied_p"].corr(df["is_winner"])), 4),
        "buckets": g.to_dict(orient="records"),
    }


def print_cal(cal, label):
    if not cal:
        print(f"  [no data] {label}")
        return
    print(f"\n=== {label}  n={cal['n_total']:,}  corr={cal['corr']:+.4f} ===")
    print(f"  {'bucket':<12} {'n':>5}  {'mid':>5}  {'yes_rate':>8}  {'dev':>7}  {'z':>6}")
    for b in cal["buckets"]:
        if b["n"] >= 20:
            marker = " ***" if abs(b["z"]) >= 2 else ""
            print(f"  {b['bucket']:<12} {int(b['n']):>5,}  {b['mid']:>5.3f}  "
                  f"{b['yes_rate']:>8.3f}  {b['deviation']:>+7.3f}  {b['z']:>+6.2f}{marker}")


def main():
    allm = load_all()
    print(f"loaded {len(allm):,} rows across {allm['__league'].nunique()} leagues")

    # Use BFE closing Betfair Exchange odds
    cols_bfe = ("BFEH", "BFED", "BFEA")
    cols_bfe_closing = ("BFECH", "BFECD", "BFECA")
    cols_b365 = ("B365H", "B365D", "B365A")  # Bet365 opening odds
    cols_ps = ("PSH", "PSD", "PSA")  # Pinnacle pre-kickoff (sharp book)

    results = {}

    for cols, label in [
        (cols_bfe, "Betfair Exchange pre-kickoff (BFE)"),
        (cols_bfe_closing, "Betfair Exchange closing (BFEC)"),
        (cols_b365, "Bet365 opening (B365)"),
        (cols_ps, "Pinnacle (PS) pre-kickoff"),
    ]:
        if cols[0] not in allm.columns:
            continue
        sub = to_selections(allm, *cols)
        print(f"\n{label}: {len(sub):,} selections  ({sub['is_winner'].sum():,} winners)")
        cal = calibrate(sub, label)
        results[label] = cal
        print_cal(cal, label)

    # Compare BFE head-to-head vs market-aggregate "average odds" columns
    for cols, label in [
        (("MaxH","MaxD","MaxA"), "Max bookie odds"),
        (("AvgH","AvgD","AvgA"), "Average bookie odds"),
    ]:
        if cols[0] not in allm.columns:
            continue
        sub = to_selections(allm, *cols)
        cal = calibrate(sub, label)
        results[label] = cal
        print_cal(cal, label)

    (DATA / "calibration_football.json").write_text(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()
