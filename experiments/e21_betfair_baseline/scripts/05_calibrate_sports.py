"""Run favorite-longshot bias calibration on Betfair sports match-odds data.

Methodology matches e16_calibration_study/05_fixed_time_calibration.py:
- 5pp buckets (0.00-0.05, ..., 0.95-1.00)
- yes_rate per bucket = fraction of selections with IS_WINNER==1
- deviation = yes_rate - bucket_mid
- z = deviation / sqrt(bucket_mid * (1-bucket_mid) / n)

Anchor choice: BEST_BACK_PRICE_60_MIN_PRIOR is our closest fixed-time anchor.
Polymarket baseline is T-7d; Betfair sports have no liquid T-7d prices — 60min
is the deepest pre-event fixed snapshot in these CSVs. We treat the selection's
implied probability p = 1 / decimal_odds. (In a 2-way head-to-head this gives
p(YES) for that selection; overround across selections means p sums slightly
above 1.0, which we tolerate — it's a known Betfair characteristic and matches
how FLB studies are conducted.)

For each (EVENT_ID, MARKET_ID, SELECTION_ID) row:
  implied_p = 1.0 / BEST_BACK_PRICE_60_MIN_PRIOR   (or lay / mid of back+lay)
  resolution = IS_WINNER (0/1)

We use the MID of back and lay if both present — that's the standard academic
approach to normalize for the bid-ask spread.

Outputs:
  data/calibration_sports.json
  data/calibration_sports.csv
"""
from __future__ import annotations
import json, math, pathlib, sys
import pandas as pd
import numpy as np

DATA = pathlib.Path(__file__).parent.parent / "data"
RAW = DATA / "raw"

# 5pp buckets matching e16
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

# Anchor columns for each sport
# Each entry: (match_odds_only=True|False, back_col, lay_col)
# Most All_Markets CSVs have BEST_BACK_PRICE_60_MIN_PRIOR.
ANCHORS = [
    ("T-60min_back", "BEST_BACK_PRICE_60_MIN_PRIOR", "BEST_LAY_PRICE_60_MIN_PRIOR"),
    ("T-30min_back", "BEST_BACK_PRICE_30_MIN_PRIOR", "BEST_LAY_PRICE_30_MIN_PRIOR"),
    ("T-1min_back",  "BEST_BACK_PRICE_1_MIN_PRIOR",  "BEST_LAY_PRICE_1_MIN_PRIOR"),
    # Sports where anchor is kickoff / first-bounce / first-ball:
    ("kickoff",      "BEST_BACK_KICK_OFF",           "BEST_LAY_KICK_OFF"),
    ("first_bounce", "BEST_BACK_FIRST_BOUNCE",       "BEST_LAY_FIRST_BOUNCE"),
    ("first_ball",   "BEST_BACK_FIRST_BALL",         "BEST_LAY_FIRST_BALL"),
]

SPORT_CATEGORY = {
    "AFL": "sports_afl",
    "AFLW": "sports_afl",
    "NRL": "sports_nrl",
    "NRLW": "sports_nrl",
    "A-League": "sports_soccer",
    "BBL": "sports_cricket",
    "WBBL": "sports_cricket",
    "NBL": "sports_basketball",
    "WNBL": "sports_basketball",
}

def sport_of(fname: str) -> str:
    for prefix, cat in SPORT_CATEGORY.items():
        if fname.startswith(prefix + "_") or fname.startswith(prefix + ".csv") or fname.startswith(prefix):
            return cat
    return "sports_other"


def implied_prob_mid(back: float, lay: float) -> float | None:
    """Mid implied probability. Both back and lay are decimal odds. Return None
    if either is missing / unusable."""
    vals = []
    if back and back > 1.0:
        vals.append(1.0 / back)
    if lay and lay > 1.0:
        vals.append(1.0 / lay)
    if not vals:
        return None
    return sum(vals) / len(vals)


def process_file(path: pathlib.Path, sport_cat: str) -> list[dict]:
    """Return a list of row-dicts with implied_p at each available anchor."""
    try:
        df = pd.read_csv(path, low_memory=False, encoding="utf-8-sig")
    except Exception as e:
        print(f"  [ERR] {path.name}: {e}")
        return []

    # Filter to Match Odds market type only
    if "MARKET_NAME" in df.columns:
        match_odds_mask = df["MARKET_NAME"].astype(str).str.contains(
            "Match Odds|Head To Head", case=False, na=False
        )
        df = df[match_odds_mask].copy()

    if "IS_WINNER" not in df.columns:
        return []
    df = df[df["IS_WINNER"].isin([0, 1])]

    out = []
    for _, row in df.iterrows():
        rec = {
            "file": path.name,
            "sport": sport_cat,
            "event_id": row.get("EVENT_ID"),
            "market_id": row.get("MARKET_ID"),
            "selection_id": row.get("SELECTION_ID"),
            "is_winner": int(row["IS_WINNER"]),
            "total_matched": float(row.get("TOTAL_MATCHED_VOLUME") or 0),
        }
        for label, bcol, lcol in ANCHORS:
            back = row.get(bcol)
            lay = row.get(lcol)
            try:
                back = float(back) if back and not (isinstance(back, float) and math.isnan(back)) else None
            except Exception:
                back = None
            try:
                lay = float(lay) if lay and not (isinstance(lay, float) and math.isnan(lay)) else None
            except Exception:
                lay = None
            p = implied_prob_mid(back, lay)
            if p is not None and 0.0 < p < 1.0:
                rec[f"p_{label}"] = round(p, 5)
        out.append(rec)
    return out


def calibrate(records: list[dict], anchor: str, category_filter: str | None = None):
    """Bucket records and compute yes_rate, deviation, z."""
    rows = []
    for r in records:
        if category_filter and r["sport"] != category_filter:
            continue
        p = r.get(f"p_{anchor}")
        if p is None:
            continue
        rows.append({"p": p, "y": r["is_winner"], "sport": r["sport"]})
    if not rows:
        return None
    df = pd.DataFrame(rows)
    df["bucket"] = df["p"].apply(bucket_label)
    df["mid"] = df["p"].apply(bucket_mid)
    g = df.groupby("bucket").agg(n=("y","size"), yes_rate=("y","mean"), mid=("mid","mean")).reset_index().sort_values("bucket")
    g["deviation"] = g["yes_rate"] - g["mid"]
    g["se"] = np.sqrt(g["mid"] * (1 - g["mid"]) / g["n"])
    g["z"] = g["deviation"] / g["se"]
    g["abs_z"] = g["z"].abs()
    return {
        "n_total": int(len(df)),
        "corr_p_y": round(float(df["p"].corr(df["y"])), 4),
        "buckets": g.to_dict(orient="records"),
    }


def main():
    records = []
    for path in sorted(RAW.glob("*.csv")):
        if path.name.startswith("ANZ_") or path.name.startswith("UK_IE") or "_Model_" in path.name:
            continue  # skip horse racing and model files — handled separately
        sport_cat = sport_of(path.name)
        recs = process_file(path, sport_cat)
        print(f"  {path.name}: {len(recs):,} selections  ({sport_cat})")
        records.extend(recs)
    print(f"\ntotal selections: {len(records):,}")

    # Save raw records
    pd.DataFrame(records).to_parquet(DATA / "sports_records.parquet", index=False)

    # Run calibration at each anchor, plus overall sports
    anchors_to_try = [a[0] for a in ANCHORS]

    results = {"n_records": len(records), "by_anchor": {}}
    for anchor in anchors_to_try:
        cal = calibrate(records, anchor)
        if cal and cal["n_total"] >= 100:
            results["by_anchor"][anchor] = cal
            print(f"\n=== ANCHOR: {anchor}  (n={cal['n_total']:,}, corr={cal['corr_p_y']:+.4f}) ===")
            print(f"  {'bucket':<12} {'n':>5}  {'mid':>5}  {'yes_rate':>8}  {'dev':>7}  {'z':>6}")
            for b in cal["buckets"]:
                if b["n"] >= 20:
                    marker = " ***" if abs(b["z"]) >= 2 else ""
                    print(f"  {b['bucket']:<12} {int(b['n']):>5,}  {b['mid']:>5.3f}  "
                          f"{b['yes_rate']:>8.3f}  {b['deviation']:>+7.3f}  {b['z']:>+6.2f}{marker}")

    # Per-sport at best anchor (T-60min_back if it has enough data, else kickoff)
    for anchor in anchors_to_try:
        cal_all = results["by_anchor"].get(anchor)
        if cal_all and cal_all["n_total"] >= 500:
            primary_anchor = anchor
            break
    else:
        primary_anchor = "kickoff"

    results["primary_anchor"] = primary_anchor
    results["by_sport"] = {}
    for sport in sorted(set(r["sport"] for r in records)):
        cal_s = calibrate(records, primary_anchor, category_filter=sport)
        if cal_s and cal_s["n_total"] >= 50:
            results["by_sport"][sport] = cal_s
            print(f"\n=== SPORT: {sport}  anchor={primary_anchor}  n={cal_s['n_total']:,}  corr={cal_s['corr_p_y']:+.4f} ===")
            print(f"  {'bucket':<12} {'n':>5}  {'mid':>5}  {'yes_rate':>8}  {'dev':>7}  {'z':>6}")
            for b in cal_s["buckets"]:
                if b["n"] >= 10:
                    marker = " ***" if abs(b["z"]) >= 2 else ""
                    print(f"  {b['bucket']:<12} {int(b['n']):>5,}  {b['mid']:>5.3f}  "
                          f"{b['yes_rate']:>8.3f}  {b['deviation']:>+7.3f}  {b['z']:>+6.2f}{marker}")

    (DATA / "calibration_sports.json").write_text(json.dumps(results, indent=2, default=str))
    print(f"\nwrote {DATA / 'calibration_sports.json'}")


if __name__ == "__main__":
    main()
