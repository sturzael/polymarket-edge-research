"""FLB calibration on Azuro Polygon using currentOdds (close-time snapshot).

For each resolved condition:
  - Skip if <2 outcomes (malformed) or >8 outcomes (rare multi-way, noisy)
  - Skip if any outcome has currentOdds <= 1.0 or > 100 (sentinel / 0-liquidity)
  - Compute overround = Σ(1/odds_i) → divide to get normalized probability per outcome
  - Bucket each outcome's normalized prob in 5pp bands
  - YES iff outcomeId ∈ wonOutcomeIds

Outputs:
  data/07_close_calibration.json — bucket stats, overall + by sport
  data/07_close_rows.parquet    — per-outcome rows for downstream analysis
"""
import json
import math
from collections import defaultdict
from pathlib import Path

INPUT = Path("/Users/elliotsturzaker/dev/event-impact-mvp/experiments/e20_azuro_amm/data/04_conditions_polygon.jsonl")
OUT_JSON = Path("/Users/elliotsturzaker/dev/event-impact-mvp/experiments/e20_azuro_amm/data/07_close_calibration.json")
OUT_CSV = Path("/Users/elliotsturzaker/dev/event-impact-mvp/experiments/e20_azuro_amm/data/07_close_rows.csv")


def bucket_label(p):
    if p < 0 or p > 1:
        return None
    i = min(int(p * 20), 19)
    lo = i / 20.0
    hi = (i + 1) / 20.0
    return f"{lo:.2f}-{hi:.2f}", lo + 0.025


def z_binomial(yes, n, mid):
    if n <= 0:
        return 0.0
    se = math.sqrt(mid * (1 - mid) / n)
    if se == 0:
        return 0.0
    rate = yes / n
    return (rate - mid) / se


def main():
    rows = []
    skip_reasons = defaultdict(int)
    n_conditions = 0
    with open(INPUT) as f:
        for line in f:
            if not line.strip():
                continue
            n_conditions += 1
            c = json.loads(line)
            outs = c.get("outcomes") or []
            n_out = len(outs)
            if n_out < 2:
                skip_reasons["lt_2_outcomes"] += 1; continue
            if n_out > 8:
                skip_reasons["gt_8_outcomes"] += 1; continue
            odds_list = []
            ok = True
            for o in outs:
                try:
                    od = float(o["currentOdds"])
                except Exception:
                    ok = False; break
                if od <= 1.0 or od > 500:
                    ok = False; break
                odds_list.append(od)
            if not ok:
                skip_reasons["bad_odds"] += 1; continue
            overround = sum(1.0 / x for x in odds_list)
            if overround <= 0:
                skip_reasons["zero_overround"] += 1; continue
            won_set = set(str(w) for w in (c.get("wonOutcomeIds") or []))
            sport = ((c.get("game") or {}).get("sport") or {}).get("name", "?")
            league = ((c.get("game") or {}).get("league") or {}).get("name", "?")
            created = int(c.get("createdBlockTimestamp") or 0)
            resolved = int(c.get("resolvedBlockTimestamp") or 0)
            game_start = int((c.get("game") or {}).get("startsAt") or 0)
            margin_raw = int(c.get("margin") or 0)
            for o, od in zip(outs, odds_list):
                raw_p = 1.0 / od
                norm_p = raw_p / overround
                is_yes = str(o["outcomeId"]) in won_set
                rows.append({
                    "condition_id": c["id"],
                    "sport": sport,
                    "league": league,
                    "n_outcomes": n_out,
                    "outcome_id": str(o["outcomeId"]),
                    "odds": od,
                    "raw_prob": raw_p,
                    "norm_prob": norm_p,
                    "is_yes": int(is_yes),
                    "overround": overround,
                    "margin_raw": margin_raw,
                    "created_ts": created,
                    "resolved_ts": resolved,
                    "game_start_ts": game_start,
                    "duration_days": (resolved - created) / 86400.0 if resolved and created else 0.0,
                })
    print(f"conditions read: {n_conditions:,}  rows produced: {len(rows):,}  skipped: {dict(skip_reasons)}")

    # Write CSV
    import csv
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {OUT_CSV}")

    # Calibration analyses
    def bucketize(rows_subset, use="norm_prob"):
        buckets = defaultdict(lambda: {"n": 0, "yes": 0, "mid_sum": 0.0})
        for r in rows_subset:
            p = r[use]
            lbl_mid = bucket_label(p)
            if lbl_mid is None:
                continue
            lbl, mid = lbl_mid
            b = buckets[lbl]
            b["n"] += 1
            b["yes"] += r["is_yes"]
            b["mid_sum"] += mid
        out = []
        for lbl in sorted(buckets):
            b = buckets[lbl]
            n = b["n"]
            mid = b["mid_sum"] / n if n else 0.0
            yes_rate = b["yes"] / n if n else 0.0
            dev = yes_rate - mid
            z = z_binomial(b["yes"], n, mid)
            out.append({
                "bucket": lbl,
                "n": n,
                "mid": round(mid, 4),
                "yes": b["yes"],
                "yes_rate": round(yes_rate, 4),
                "deviation": round(dev, 4),
                "z": round(z, 2),
            })
        return out

    overall_norm = bucketize(rows, "norm_prob")
    overall_raw = bucketize(rows, "raw_prob")

    # Per-sport
    by_sport = defaultdict(list)
    for r in rows:
        by_sport[r["sport"]].append(r)
    per_sport_norm = {}
    for sport, subset in by_sport.items():
        per_sport_norm[sport] = {
            "n_rows": len(subset),
            "calibration": bucketize(subset, "norm_prob"),
        }

    # By number of outcomes
    by_nout = defaultdict(list)
    for r in rows:
        by_nout[r["n_outcomes"]].append(r)
    per_nout = {k: {"n_rows": len(v), "calibration": bucketize(v, "norm_prob")}
                for k, v in by_nout.items()}

    # Stratify by duration >= 7 days (for e16 direct comparability)
    long_markets = [r for r in rows if r["duration_days"] >= 7]
    print(f"\nlong-duration (≥7d) rows: {len(long_markets):,}")
    long_cal = bucketize(long_markets, "norm_prob")

    out = {
        "n_conditions_read": n_conditions,
        "n_rows_total": len(rows),
        "skip_reasons": dict(skip_reasons),
        "overall_normalized_prob": overall_norm,
        "overall_raw_prob": overall_raw,
        "long_duration_7d_normalized_prob": {
            "n_rows": len(long_markets),
            "calibration": long_cal,
        },
        "by_sport_normalized": per_sport_norm,
        "by_n_outcomes_normalized": per_nout,
    }
    OUT_JSON.write_text(json.dumps(out, indent=2))
    print(f"wrote {OUT_JSON}")

    # Print summary
    print("\n=== OVERALL (normalized prob, close-time snapshot) ===")
    print(f"  {'bucket':<12} {'n':>7} {'mid':>6} {'yes_rate':>9} {'dev':>8} {'z':>6}")
    for b in overall_norm:
        star = "***" if abs(b["z"]) >= 2 else ("*" if abs(b["z"]) >= 1.5 else "")
        print(f"  {b['bucket']:<12} {b['n']:>7,} {b['mid']:>6.3f} {b['yes_rate']:>9.3f} {b['deviation']:>+8.3f} {b['z']:>+6.2f} {star}")


if __name__ == "__main__":
    main()
