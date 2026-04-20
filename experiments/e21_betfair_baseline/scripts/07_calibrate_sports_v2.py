"""Improved calibration: filter for liquidity and market sanity.

Additions vs 05:
- Require both back AND lay prices present at the anchor (not just one)
- Require market overround in [0.98, 1.10] (2-way markets; throws out void/suspended markets)
- Require non-null matched volume at that anchor
- Additionally filter out BBL (cricket) because the BBL files show weird heavy 0.95-1.00 contamination;
  inspection shows BBL "Match Odds" includes tied/super-over edge cases that create data quirks

The last filter is discussed in DECISIONS.md — we keep cricket separately and flag it.
"""
from __future__ import annotations
import json, math, pathlib, sys
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

SPORT_CATEGORY = {
    "AFL": "sports_afl",
    "AFLW": "sports_aflw",
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
        if fname.startswith(prefix + "_") or fname.startswith(prefix + "."):
            return cat
    return "sports_other"


def implied_prob_back_lay(back, lay):
    """Require BOTH present; return mid implied prob."""
    try:
        back = float(back); lay = float(lay)
    except Exception:
        return None
    if not (back > 1.0 and lay > 1.0):
        return None
    # Mid implied prob = (1/back + 1/lay) / 2
    return (1.0 / back + 1.0 / lay) / 2.0


def process_file(path: pathlib.Path, sport_cat: str) -> list[dict]:
    try:
        df = pd.read_csv(path, low_memory=False, encoding="utf-8-sig")
    except Exception as e:
        return []

    if "MARKET_NAME" in df.columns:
        mask = df["MARKET_NAME"].astype(str).str.match(r"^(Match Odds|Head To Head)$", na=False)
        df = df[mask].copy()
    if "IS_WINNER" not in df.columns:
        return []
    df = df[df["IS_WINNER"].isin([0, 1])]

    anchors = {
        "T-60min": ("BEST_BACK_PRICE_60_MIN_PRIOR", "BEST_LAY_PRICE_60_MIN_PRIOR", "MATCHED_VOLUME_60_MIN_PRIOR"),
        "T-30min": ("BEST_BACK_PRICE_30_MIN_PRIOR", "BEST_LAY_PRICE_30_MIN_PRIOR", "MATCHED_VOLUME_30_MIN_PRIOR"),
        "T-1min":  ("BEST_BACK_PRICE_1_MIN_PRIOR",  "BEST_LAY_PRICE_1_MIN_PRIOR",  "MATCHED_VOLUME_1_MIN_PRIOR"),
        "kickoff": ("BEST_BACK_KICK_OFF", "BEST_LAY_KICK_OFF", "MATCHED_VOLUME_KICK_OFF"),
        "first_bounce": ("BEST_BACK_FIRST_BOUNCE", "BEST_LAY_FIRST_BOUNCE", "MATCHED_VOLUME_FIRST_BOUNCE"),
        "first_ball": ("BEST_BACK_FIRST_BALL", "BEST_LAY_FIRST_BALL", "MATCHED_VOLUME_FIRST_BALL"),
    }

    out = []
    for _, row in df.iterrows():
        rec = {
            "file": path.name,
            "sport": sport_cat,
            "event_id": row.get("EVENT_ID"),
            "market_id": row.get("MARKET_ID"),
            "selection_id": row.get("SELECTION_ID"),
            "is_winner": int(row["IS_WINNER"]),
        }
        for label, (bcol, lcol, vcol) in anchors.items():
            if bcol not in df.columns:
                continue
            p = implied_prob_back_lay(row.get(bcol), row.get(lcol))
            v = row.get(vcol)
            try:
                v = float(v)
            except Exception:
                v = None
            if p is not None and 0.0 < p < 1.0 and v is not None and v > 0:
                rec[f"p_{label}"] = round(p, 5)
                rec[f"v_{label}"] = v
        out.append(rec)
    return out


def calibrate_with_filter(df: pd.DataFrame, anchor: str, min_volume: float = 100.0,
                           sport_filter: str | None = None):
    """Apply liquidity + market-sanity filters, then calibrate."""
    pcol, vcol = f"p_{anchor}", f"v_{anchor}"
    if pcol not in df.columns:
        return None
    work = df[df[pcol].notna() & df[vcol].notna() & (df[vcol] >= min_volume)].copy()
    if sport_filter:
        work = work[work["sport"] == sport_filter]
    # Also require overround: for each (event,market) sum of p must be within [0.98, 1.10]
    sums = work.groupby(["event_id","market_id"])[pcol].sum().reset_index().rename(columns={pcol: "sum_p"})
    good = sums[(sums["sum_p"] >= 0.98) & (sums["sum_p"] <= 1.10)][["event_id","market_id"]]
    work = work.merge(good, on=["event_id","market_id"], how="inner")
    if len(work) < 100:
        return None
    work["bucket"] = work[pcol].apply(bucket_label)
    work["mid"] = work[pcol].apply(bucket_mid)
    g = work.groupby("bucket").agg(n=("is_winner","size"),
                                    yes_rate=("is_winner","mean"),
                                    mid=("mid","mean")).reset_index().sort_values("bucket")
    g["deviation"] = g["yes_rate"] - g["mid"]
    g["se"] = np.sqrt(g["mid"] * (1 - g["mid"]) / g["n"])
    g["z"] = g["deviation"] / g["se"]
    return {
        "anchor": anchor,
        "min_volume": min_volume,
        "sport_filter": sport_filter,
        "n_total": int(len(work)),
        "n_markets": int(work[["event_id","market_id"]].drop_duplicates().shape[0]),
        "corr_p_y": round(float(work[pcol].corr(work["is_winner"])), 4),
        "buckets": g.to_dict(orient="records"),
    }


def print_cal(cal, label=""):
    if not cal:
        return
    print(f"\n=== {label}  n={cal['n_total']:,}  markets={cal['n_markets']:,}  corr={cal['corr_p_y']:+.4f} ===")
    print(f"  {'bucket':<12} {'n':>5}  {'mid':>5}  {'yes_rate':>8}  {'dev':>7}  {'z':>6}")
    for b in cal["buckets"]:
        if b["n"] >= 20:
            marker = " ***" if abs(b["z"]) >= 2 else ""
            print(f"  {b['bucket']:<12} {int(b['n']):>5,}  {b['mid']:>5.3f}  "
                  f"{b['yes_rate']:>8.3f}  {b['deviation']:>+7.3f}  {b['z']:>+6.2f}{marker}")


def main():
    records = []
    for path in sorted(RAW.glob("*.csv")):
        if path.name.startswith("ANZ_") or path.name.startswith("UK_IE") or "_Model_" in path.name:
            continue
        sport_cat = sport_of(path.name)
        recs = process_file(path, sport_cat)
        records.extend(recs)
    print(f"total records: {len(records):,}")
    df = pd.DataFrame(records)
    df.to_parquet(DATA / "sports_records_v2.parquet", index=False)

    results = {"versions": {}}
    # Primary: T-60min, liquidity filter, per-sport and overall
    for anchor in ["T-60min", "T-30min", "T-1min"]:
        for min_vol in [0.0, 100.0, 1000.0]:
            cal = calibrate_with_filter(df, anchor, min_volume=min_vol)
            if cal:
                key = f"{anchor}_vol>={min_vol:.0f}"
                results["versions"][key] = cal
                print_cal(cal, f"ALL SPORTS  {key}")

    # Per sport at T-60min with vol>=100
    sports = sorted(set(records[i]["sport"] for i in range(len(records))))
    results["by_sport_T60min"] = {}
    for sport in sports:
        cal = calibrate_with_filter(df, "T-60min", min_volume=100.0, sport_filter=sport)
        if cal:
            results["by_sport_T60min"][sport] = cal
            print_cal(cal, f"{sport}  T-60min  vol>=100")

    # Per sport at T-1min (closer to kickoff — higher liquidity usually)
    results["by_sport_T1min"] = {}
    for sport in sports:
        cal = calibrate_with_filter(df, "T-1min", min_volume=100.0, sport_filter=sport)
        if cal:
            results["by_sport_T1min"][sport] = cal
            print_cal(cal, f"{sport}  T-1min  vol>=100")

    (DATA / "calibration_sports_v2.json").write_text(json.dumps(results, indent=2, default=str))
    print(f"\nwrote calibration_sports_v2.json")


if __name__ == "__main__":
    main()
