"""Clean calibration: exclude multi-winner conditions (double-chance /
range markets). Only mutually-exclusive single-winner markets included.

Also: add margin-sanity filter. Azuro `margin` field is raw BigInt; actual
overround from the odds should be in [1.01, 1.20]. Drop any condition with
overround outside [1.00, 1.30].
"""
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

IN = Path("/Users/elliotsturzaker/dev/event-impact-mvp/experiments/e20_azuro_amm/data/07_close_rows.csv")
OUT_JSON = Path("/Users/elliotsturzaker/dev/event-impact-mvp/experiments/e20_azuro_amm/data/10_clean_calibration.json")


def bucket_label(p):
    if p < 0 or p > 1:
        return None
    i = min(int(p * 20), 19)
    lo = i / 20.0; hi = (i + 1) / 20.0
    return f"{lo:.2f}-{hi:.2f}", lo + 0.025


def z_binomial(yes, n, mid):
    if n <= 0: return 0.0
    se = math.sqrt(mid * (1 - mid) / n)
    if se == 0: return 0.0
    return (yes / n - mid) / se


def bucketize(rows, key="norm_prob"):
    b = defaultdict(lambda: {"n": 0, "yes": 0, "mid_sum": 0.0})
    for r in rows:
        p = float(r[key])
        lm = bucket_label(p)
        if lm is None: continue
        lbl, mid = lm
        x = b[lbl]; x["n"] += 1; x["yes"] += int(r["is_yes"]); x["mid_sum"] += mid
    out = []
    for lbl in sorted(b):
        x = b[lbl]
        mid = x["mid_sum"] / x["n"] if x["n"] else 0
        yr = x["yes"] / x["n"] if x["n"] else 0
        out.append({
            "bucket": lbl, "n": x["n"], "mid": round(mid, 4),
            "yes": x["yes"], "yes_rate": round(yr, 4),
            "deviation": round(yr - mid, 4),
            "z": round(z_binomial(x["yes"], x["n"], mid), 2),
        })
    return out


def main():
    rows = []
    wins_per_cond = defaultdict(int)
    overround_per_cond = {}
    with open(IN) as f:
        for r in csv.DictReader(f):
            cid = r["condition_id"]
            wins_per_cond[cid] += int(r["is_yes"])
            overround_per_cond[cid] = float(r["overround"])
            rows.append(r)

    total = len(rows)
    clean = [r for r in rows
             if wins_per_cond[r["condition_id"]] == 1
             and 1.00 < overround_per_cond[r["condition_id"]] <= 1.30]
    print(f"total rows: {total:,}  clean (1 winner, 1<overround<=1.3): {len(clean):,}")

    unique_conds = set(r["condition_id"] for r in clean)
    print(f"unique conditions: {len(unique_conds):,}")

    # Overall
    overall = bucketize(clean, "norm_prob")
    overall_raw = bucketize(clean, "raw_prob")

    # Per-sport
    by_sport = defaultdict(list)
    for r in clean:
        by_sport[r["sport"]].append(r)
    per_sport = {
        s: {"n_rows": len(v), "calibration": bucketize(v, "norm_prob")}
        for s, v in by_sport.items()
    }

    # By n_outcomes
    by_no = defaultdict(list)
    for r in clean:
        by_no[int(r["n_outcomes"])].append(r)
    per_no = {
        k: {"n_rows": len(v), "calibration": bucketize(v, "norm_prob")}
        for k, v in by_no.items()
    }

    # Duration ≥ 7 days subset (direct e16 comparability)
    long = [r for r in clean if float(r["duration_days"]) >= 7]
    long_cal = bucketize(long, "norm_prob")

    out = {
        "n_rows_total": total,
        "n_rows_clean": len(clean),
        "n_unique_conditions": len(unique_conds),
        "overall_normalized": overall,
        "overall_raw_margin_uncorrected": overall_raw,
        "long_duration_7d": {"n_rows": len(long), "calibration": long_cal},
        "by_sport": per_sport,
        "by_n_outcomes": per_no,
    }
    OUT_JSON.write_text(json.dumps(out, indent=2))
    print(f"\nwrote {OUT_JSON}")

    print("\n=== CLEAN OVERALL (normalized, margin-corrected) ===")
    print(f"  {'bucket':<12} {'n':>7} {'mid':>6} {'yes_rate':>9} {'dev':>8} {'z':>7}")
    for b in overall:
        star = "***" if abs(b["z"]) >= 2 else ""
        print(f"  {b['bucket']:<12} {b['n']:>7,} {b['mid']:>6.3f} {b['yes_rate']:>9.3f} {b['deviation']:>+8.3f} {b['z']:>+7.2f} {star}")

    print("\n=== CLEAN, 2-OUTCOME ONLY (pure binary sports) ===")
    two = per_no.get(2, {}).get("calibration", [])
    print(f"  {'bucket':<12} {'n':>7} {'mid':>6} {'yes_rate':>9} {'dev':>8} {'z':>7}")
    for b in two:
        star = "***" if abs(b["z"]) >= 2 else ""
        print(f"  {b['bucket']:<12} {b['n']:>7,} {b['mid']:>6.3f} {b['yes_rate']:>9.3f} {b['deviation']:>+8.3f} {b['z']:>+7.2f} {star}")

    print("\n=== CLEAN, 3-OUTCOME ONLY (3-way football) ===")
    three = per_no.get(3, {}).get("calibration", [])
    print(f"  {'bucket':<12} {'n':>7} {'mid':>6} {'yes_rate':>9} {'dev':>8} {'z':>7}")
    for b in three:
        star = "***" if abs(b["z"]) >= 2 else ""
        print(f"  {b['bucket']:<12} {b['n']:>7,} {b['mid']:>6.3f} {b['yes_rate']:>9.3f} {b['deviation']:>+8.3f} {b['z']:>+7.2f} {star}")

    print("\n=== PER SPORT — 0.55-0.60 bucket (the Polymarket anomaly bucket) ===")
    print(f"  {'sport':<22} {'n_rows_total':>12} {'n_bucket':>8} {'yes_rate':>9} {'mid':>6} {'dev':>8} {'z':>7}")
    for sport, v in sorted(per_sport.items(), key=lambda x: -x[1]["n_rows"]):
        if v["n_rows"] < 500: continue
        for b in v["calibration"]:
            if b["bucket"] == "0.55-0.60":
                star = "***" if abs(b["z"]) >= 2 else ""
                print(f"  {sport:<22} {v['n_rows']:>12,} {b['n']:>8,} {b['yes_rate']:>9.3f} {b['mid']:>6.3f} {b['deviation']:>+8.3f} {b['z']:>+7.2f} {star}")


if __name__ == "__main__":
    main()
