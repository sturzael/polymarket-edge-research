"""Re-run the clean calibration on whatever Gnosis data we have
so far, to confirm the finding replicates on a second chain.
"""
import json
import math
from collections import defaultdict
from pathlib import Path

IN = Path("/Users/elliotsturzaker/dev/event-impact-mvp/experiments/e20_azuro_amm/data/04_conditions_gnosis.jsonl")
OUT = Path("/Users/elliotsturzaker/dev/event-impact-mvp/experiments/e20_azuro_amm/data/13_gnosis_calibration.json")


def bucket_label(p):
    if p < 0 or p > 1: return None
    i = min(int(p * 20), 19)
    lo = i / 20.0; hi = (i + 1) / 20.0
    return f"{lo:.2f}-{hi:.2f}", lo + 0.025


def z_binomial(yes, n, mid):
    if n <= 0: return 0.0
    se = math.sqrt(mid * (1 - mid) / n)
    if se == 0: return 0.0
    return (yes / n - mid) / se


def bucketize(rows, key):
    b = defaultdict(lambda: {"n": 0, "yes": 0, "mid_sum": 0.0})
    for r in rows:
        p = r[key]
        lm = bucket_label(p)
        if lm is None: continue
        lbl, mid = lm
        x = b[lbl]; x["n"] += 1; x["yes"] += r["is_yes"]; x["mid_sum"] += mid
    out = []
    for lbl in sorted(b):
        x = b[lbl]
        mid = x["mid_sum"] / x["n"] if x["n"] else 0
        yr = x["yes"] / x["n"] if x["n"] else 0
        out.append({
            "bucket": lbl, "n": x["n"],
            "mid": round(mid, 4), "yes": x["yes"],
            "yes_rate": round(yr, 4),
            "deviation": round(yr - mid, 4),
            "z": round(z_binomial(x["yes"], x["n"], mid), 2),
        })
    return out


def main():
    # Stream — but need per-condition win count for multi-winner filter
    # so 2-pass: first collect conditions, then filter & bucketize
    rows_raw = []
    n_read = 0
    skipped = defaultdict(int)
    with open(IN) as f:
        for line in f:
            if not line.strip(): continue
            n_read += 1
            try:
                c = json.loads(line)
            except Exception:
                skipped["json_err"] += 1; continue
            outs = c.get("outcomes") or []
            if len(outs) < 2 or len(outs) > 8:
                skipped["bad_n_outcomes"] += 1; continue
            odds = []
            ok = True
            for o in outs:
                try:
                    od = float(o["currentOdds"])
                except Exception:
                    ok = False; break
                if od <= 1.0 or od > 500:
                    ok = False; break
                odds.append(od)
            if not ok:
                skipped["bad_odds"] += 1; continue
            overround = sum(1.0 / x for x in odds)
            if not (1.0 < overround <= 1.30):
                skipped["bad_overround"] += 1; continue
            won = set(str(w) for w in (c.get("wonOutcomeIds") or []))
            n_winners_local = sum(1 for o in outs if str(o["outcomeId"]) in won)
            if n_winners_local != 1:
                skipped["not_single_winner"] += 1; continue
            sport = ((c.get("game") or {}).get("sport") or {}).get("name", "?")
            for o, od in zip(outs, odds):
                raw_p = 1.0 / od
                norm_p = raw_p / overround
                rows_raw.append({
                    "is_yes": int(str(o["outcomeId"]) in won),
                    "norm_prob": norm_p,
                    "raw_prob": raw_p,
                    "sport": sport,
                    "n_out": len(outs),
                })
    print(f"gnosis: read {n_read:,}  kept {len(rows_raw):,}  skipped {dict(skipped)}")
    overall = bucketize(rows_raw, "norm_prob")

    by_sport = defaultdict(list)
    for r in rows_raw:
        by_sport[r["sport"]].append(r)
    per_sport = {
        s: {"n_rows": len(v), "calibration": bucketize(v, "norm_prob")}
        for s, v in by_sport.items()
    }

    out = {
        "chain": "gnosis",
        "n_conditions_read": n_read,
        "n_clean_rows": len(rows_raw),
        "overall_normalized": overall,
        "by_sport": per_sport,
    }
    OUT.write_text(json.dumps(out, indent=2))
    print(f"wrote {OUT}")

    print("\n=== GNOSIS OVERALL (clean, normalized) ===")
    print(f"  {'bucket':<12} {'n':>7} {'mid':>6} {'yes_rate':>9} {'dev':>8} {'z':>7}")
    for b in overall:
        star = "***" if abs(b["z"]) >= 2 else ""
        print(f"  {b['bucket']:<12} {b['n']:>7,} {b['mid']:>6.3f} {b['yes_rate']:>9.3f} {b['deviation']:>+8.3f} {b['z']:>+7.2f} {star}")


if __name__ == "__main__":
    main()
