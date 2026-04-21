"""Per-sport T-7d FLB calibration stratification.

Reads the authoritative sports-deep parquet (n=2,025) from e16 and produces
a calibration table per sport using identical bucket/deviation/z-score
formulas as e16's 05_fixed_time_calibration.py.

Outputs:
  FINDINGS.md        — one calibration table per sport + comparison summary
  VERDICT.md         — deployable/non-deployable verdict
  DECISIONS.md       — methodology decisions
  data/per_sport_calibration.json
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
DATA_DIR = HERE / "data"
DATA_DIR.mkdir(exist_ok=True)
SPORTS_DEEP = (HERE.parent.parent / "e16_calibration_study" / "data"
               / "05_tm7d_prices_sports_deep.parquet")

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


def calibration_table(df: pd.DataFrame) -> pd.DataFrame:
    """Per-bucket n, yes_rate, deviation, z-score (binomial SE)."""
    df = df.copy()
    df["bucket"] = df["price_tm7d"].apply(bucket_label)
    df["mid"] = df["price_tm7d"].apply(bucket_mid)
    df["yes"] = (df["resolution"] == "YES").astype(int)
    g = (df.groupby("bucket")
           .agg(n=("yes", "size"),
                yes_rate=("yes", "mean"),
                mid=("mid", "mean"))
           .reset_index()
           .sort_values("bucket"))
    g["deviation"] = g["yes_rate"] - g["mid"]

    def z(row):
        # Match e16 FINDINGS.md formulation: binomial SE using observed yes_rate
        # (Wald). This is what gave the e16 z=7.6 at the 0.55-0.60 bucket.
        n = row["n"]
        p_hat = row["yes_rate"]
        if n <= 0:
            return 0.0
        # Guard against 0 or 1 (collapses SE to 0 — use mid-based SE as fallback)
        if p_hat in (0.0, 1.0):
            p0 = row["mid"]
            se = math.sqrt(p0 * (1 - p0) / n)
        else:
            se = math.sqrt(p_hat * (1 - p_hat) / n)
        if se == 0:
            return 0.0
        return row["deviation"] / se

    g["z"] = g.apply(z, axis=1)
    return g


def sport_name(category: str) -> str:
    """sports_nba -> NBA; sports_ufc_boxing -> UFC_BOXING."""
    prefix = "sports_"
    s = category[len(prefix):] if category.startswith(prefix) else category
    return s.upper()


def fmt_calib_table_md(tbl: pd.DataFrame, min_n: int = 1) -> str:
    lines = ["| bucket | n | mid | yes_rate | deviation | z |",
             "|---|---:|---:|---:|---:|---:|"]
    for _, r in tbl.iterrows():
        if r["n"] < min_n:
            continue
        dev_pp = r["deviation"] * 100
        star = " ***" if abs(r["z"]) >= 2 else ""
        lines.append(
            f"| {r['bucket']} | {int(r['n'])} | {r['mid']:.3f} | "
            f"{r['yes_rate']:.3f} | {dev_pp:+.1f}pp | {r['z']:+.2f}{star} |"
        )
    return "\n".join(lines)


def main():
    df = pd.read_parquet(SPORTS_DEEP)
    print(f"Loaded {len(df):,} sports markets")
    print("Categories:", df["category"].value_counts().to_dict())

    # Overall sanity check — should match e16 table
    overall = calibration_table(df)
    print("\n=== OVERALL SPORTS (all n=2,025) — sanity check vs e16 ===")
    print(overall.to_string(index=False))

    # Per-sport
    sports = sorted(df["category"].unique())
    per_sport = {}
    critical_bucket = "0.55-0.60"
    comparison_rows = []

    for cat in sports:
        sub = df[df["category"] == cat].copy()
        sp = sport_name(cat)
        tbl = calibration_table(sub)
        per_sport[sp] = {
            "category": cat,
            "n_total": int(len(sub)),
            "n_yes": int((sub["resolution"] == "YES").sum()),
            "calibration": tbl.to_dict(orient="records"),
        }
        # Extract 0.55-0.60 row
        crit = tbl[tbl["bucket"] == critical_bucket]
        if len(crit) == 0:
            n, yr, dev, z = 0, None, None, None
        else:
            r = crit.iloc[0]
            n = int(r["n"])
            yr = float(r["yes_rate"])
            dev = float(r["deviation"])
            z = float(r["z"])
        per_sport[sp]["critical_bucket"] = {
            "bucket": critical_bucket,
            "n": n,
            "yes_rate": yr,
            "deviation": dev,
            "z": z,
            "insufficient_sample": n < 20,
        }
        comparison_rows.append({
            "sport": sp,
            "n_total": int(len(sub)),
            "n_bucket": n,
            "yes_rate": yr,
            "deviation": dev,
            "z": z,
            "insufficient_sample": n < 20,
        })

    # Save JSON
    out_json = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": str(SPORTS_DEEP.relative_to(HERE.parent.parent.parent)),
        "n_total": int(len(df)),
        "critical_bucket": critical_bucket,
        "insufficient_threshold": 20,
        "per_sport": per_sport,
        "comparison_0p55_0p60": comparison_rows,
        "overall_calibration": overall.to_dict(orient="records"),
    }
    (DATA_DIR / "per_sport_calibration.json").write_text(
        json.dumps(out_json, indent=2, default=str)
    )
    print(f"\nWrote {DATA_DIR / 'per_sport_calibration.json'}")

    # Build FINDINGS.md
    lines = []
    lines.append("# Per-Sport FLB Stratification — Findings")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now(timezone.utc).isoformat()}  ")
    lines.append("**Source:** `experiments/e16_calibration_study/data/05_tm7d_prices_sports_deep.parquet`  ")
    lines.append(f"**Sample:** n={len(df):,} sports markets across {len(sports)} sport categories  ")
    lines.append("**Methodology:** identical to e16 — 5pp buckets, mid-point = lo+0.025, "
                 "deviation = yes_rate − mid, z = deviation / sqrt(yes_rate·(1−yes_rate)/n) "
                 "(observed-rate Wald SE, matches e16 FINDINGS.md table which reports z=7.6 at n=120).  ")
    lines.append("**Critical bucket:** 0.55–0.60 (e16 peak at yes_rate=0.833, dev=+25.8pp, z=7.6).  ")
    lines.append("**Insufficient-sample flag:** n < 20 in the 0.55–0.60 bucket.")
    lines.append("")

    lines.append("## 1. Cross-sport comparison (0.55–0.60 bucket)")
    lines.append("")
    lines.append("| sport | n_total | n_bucket | yes_rate | deviation | z | flag |")
    lines.append("|---|---:|---:|---:|---:|---:|---|")
    # Sort by z descending (strongest signal first)
    comp_sorted = sorted(
        comparison_rows,
        key=lambda r: (r["z"] if r["z"] is not None else -999),
        reverse=True,
    )
    for r in comp_sorted:
        flag = "INSUFFICIENT (n<20)" if r["insufficient_sample"] else "ok"
        yr = f"{r['yes_rate']:.3f}" if r["yes_rate"] is not None else "—"
        dev = f"{r['deviation']*100:+.1f}pp" if r["deviation"] is not None else "—"
        z = f"{r['z']:+.2f}" if r["z"] is not None else "—"
        lines.append(
            f"| {r['sport']} | {r['n_total']} | {r['n_bucket']} | {yr} | {dev} | {z} | {flag} |"
        )
    lines.append("")

    lines.append("### Interpretation of the comparison")
    lines.append("")
    lines.append("- **Only MLB survives the per-sport stratification test at the critical 0.55–0.60 bucket.**")
    lines.append("  MLB has n=54 in the bucket (45% of the entire 120-market bucket), yes_rate 94.4%, dev +36.9pp, z=+11.85 — a stronger signal than the aggregate.")
    lines.append("- **Seven of the eight sports are insufficient-sample at the critical bucket.** Their n_bucket ranges from 2 (F1) to 19 (NBA). We cannot cleanly test the 0.55–0.60 FLB in those sports from this dataset alone.")
    lines.append("- **Where the small-sample point estimates land is still informative, even if not significant.** NHL (n=11, +33.4pp, z=3.85), NFL (n=8, +30.0pp, z=2.57) both point in the same direction as MLB despite small n and reach z≥2; NBA is directionally positive but z=1.6.")
    lines.append("  UFC/boxing (+9.2pp), soccer (+9.2pp), tennis (+6.1pp), F1 (−7.5pp) show essentially no per-sport signal at the 0.55–0.60 cell — whether from true absence of bias or small-sample noise is undetermined.")
    lines.append("- **The aggregate +25.8pp is not uniformly distributed across sports.** MLB provides the bulk of the signal by both raw count and effect size. If MLB were excluded, the remaining 66 markets in the 0.55–0.60 bucket would show yes_rate ≈ 74%, dev ≈ +17pp — weaker but still positive.")
    lines.append("- **Broader FLB pattern (0.55–0.85 bucket range) per sport:** MLB, NBA, NHL, and tennis all show significant FLB in at least one bucket in the 0.60–0.80 range (z≥2.6 per their full tables). F1, soccer, and UFC/boxing do not consistently show it. This broadens the 'where to deploy' question beyond the single critical bucket — see VERDICT.md.")
    lines.append("")

    lines.append("## 2. Per-sport full calibration tables")
    lines.append("")
    # Sorted alphabetically for readability
    for sp in sorted(per_sport.keys()):
        info = per_sport[sp]
        tbl = pd.DataFrame(info["calibration"])
        lines.append(f"### {sp} (n={info['n_total']}, {info['n_yes']} YES overall)")
        lines.append("")
        # Only show buckets with n>=1 (keep full table; mark small n)
        lines.append(fmt_calib_table_md(tbl, min_n=1))
        lines.append("")
        crit = info["critical_bucket"]
        if crit["n"] == 0:
            lines.append("> **0.55–0.60 bucket:** no markets.")
        elif crit["insufficient_sample"]:
            lines.append(
                f"> **0.55–0.60 bucket:** n={crit['n']} (INSUFFICIENT, <20). "
                f"yes_rate={crit['yes_rate']:.3f}, dev={crit['deviation']*100:+.1f}pp, z={crit['z']:+.2f}."
            )
        else:
            lines.append(
                f"> **0.55–0.60 bucket:** n={crit['n']}, yes_rate={crit['yes_rate']:.3f}, "
                f"dev={crit['deviation']*100:+.1f}pp, z={crit['z']:+.2f}."
            )
        lines.append("")

    lines.append("## 3. Overall (all sports) — reference / sanity check vs e16")
    lines.append("")
    lines.append(fmt_calib_table_md(overall, min_n=1))
    lines.append("")
    lines.append("This should match the table in `experiments/e16_calibration_study/FINDINGS.md` §2e "
                 "(e16 reported 0.55–0.60: n=120, yes_rate=0.833, dev=+25.8pp, z=7.6).")

    (HERE / "FINDINGS.md").write_text("\n".join(lines))
    print(f"Wrote {HERE / 'FINDINGS.md'}")

    # VERDICT.md — generate based on thresholds
    deployable = [r for r in comparison_rows
                  if (r["z"] is not None and r["z"] >= 2 and not r["insufficient_sample"])]
    weak = [r for r in comparison_rows
            if (r["z"] is not None and r["z"] < 2 and not r["insufficient_sample"])]
    insufficient = [r for r in comparison_rows if r["insufficient_sample"]]

    v = []
    v.append("# Per-Sport Deployability Verdict")
    v.append("")
    v.append("**Criterion for deployability (0.55–0.60 bucket):** n ≥ 20 AND z ≥ 2 (the e16 "
             "study-wide two-sigma threshold). Z < 2 means we cannot reject the null of no FLB "
             "in that sport at the peak bucket, and n < 20 means sample is too small to test.")
    v.append("")

    def names(rs):
        return ", ".join(sorted(r["sport"] for r in rs)) or "(none)"

    v.append("**Deployable (signal survives per-sport stratification):** "
             f"{names(deployable)}.")
    v.append("")
    v.append("**Not deployable — sample too small to test in critical bucket:** "
             f"{names(insufficient)}.")
    v.append("")
    v.append("**Not deployable — signal does not reach z≥2 at sport level:** "
             f"{names(weak)}.")
    v.append("")
    v.append("**One-paragraph summary.** Of the 8 sport categories in the n=2,025 sports-deep sample, "
             f"only **MLB** passes both sample-size (n_bucket ≥ 20) and significance (z ≥ 2) hurdles at the "
             f"critical 0.55–0.60 bucket — with n=54, yes_rate 94.4%, dev +36.9pp, z=+11.85. MLB alone contributes "
             f"45% of the markets in the critical bucket and carries the bulk of the e16 aggregate signal. "
             f"Seven sports (NBA, NHL, NFL, tennis, F1, soccer, UFC/boxing) fall under the n<20 insufficient-sample "
             f"flag at the 0.55–0.60 bucket; of those, NHL (n=11, +33.4pp, z=3.85) and NFL (n=8, +30.0pp, z=2.57) "
             f"point strongly in the same direction as MLB despite small n, while NBA points positive but weakly "
             f"(n=19, z=1.60), and the remaining four show no or negative effect. **For deployment from this dataset alone: "
             f"MLB is the only sport where the 0.55–0.60 signal is firmly validated. NHL/NFL are directionally supportive but "
             f"need a larger sample before trading.** Adjacent favorite buckets (0.60–0.80) also show per-sport significance "
             f"for MLB, NBA, NHL, and tennis, so a broader-bucket deployment (not just 0.55–0.60) widens the deployable "
             f"universe to roughly those four sports — at the cost of mixing in cells that e16 did not single out as the peak. "
             f"F1, soccer, and UFC/boxing show no clear per-sport FLB at T-7d in this sample and should be excluded "
             f"pending more data. **Bottom line:** the e16 aggregate FLB is not a uniform 'all sports' phenomenon — it is "
             f"primarily an MLB phenomenon with supportive hints in NHL/NFL/NBA and weak-to-absent signal in F1, soccer, "
             f"UFC/boxing. A per-sport filter on entry is recommended over a blanket 'any sport' strategy.")
    v.append("")

    # Add detail lines
    v.append("## Detail per sport")
    v.append("")
    for r in comp_sorted:
        sp = r["sport"]
        if r["insufficient_sample"]:
            note = f"INSUFFICIENT SAMPLE — n_bucket={r['n_bucket']} < 20"
        elif r["z"] is not None and r["z"] >= 2:
            note = (f"DEPLOYABLE — n_bucket={r['n_bucket']}, "
                    f"dev={r['deviation']*100:+.1f}pp, z={r['z']:+.2f}")
        else:
            z_str = f"{r['z']:+.2f}" if r["z"] is not None else "n/a"
            note = f"SIGNAL WEAK — n_bucket={r['n_bucket']}, z={z_str}"
        v.append(f"- **{sp}** (n_total={r['n_total']}): {note}")
    v.append("")

    (HERE / "VERDICT.md").write_text("\n".join(v))
    print(f"Wrote {HERE / 'VERDICT.md'}")

    print("\nDone.")


if __name__ == "__main__":
    main()
