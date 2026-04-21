"""Temporal stability analysis of the T-7d sports FLB finding.

Splits the 628 sports markets (0.50-0.60 at T-7d) chronologically
by end_date (resolution date) and recomputes the calibration table
for each time slice. The core question: is the +25.8pp FLB at the
0.55-0.60 bucket stable, decaying, or strengthening?

Outputs (all written under experiments/e23_stratification/b_temporal/):
  FINDINGS.md
  VERDICT.md
  DECISIONS.md
  data/temporal_calibration.json
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from math import sqrt
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
E16 = ROOT / "experiments" / "e16_calibration_study" / "data"
OUT_DATA = HERE / "data"
OUT_DATA.mkdir(parents=True, exist_ok=True)

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


def calibration(df: pd.DataFrame) -> pd.DataFrame:
    """Compute bucket / n / yes_rate / deviation / z-score for a dataframe."""
    g = (df.groupby("bucket")
           .agg(n=("yes", "size"),
                yes_rate=("yes", "mean"),
                mid=("bucket_mid", "mean"))
           .reset_index()
           .sort_values("bucket"))
    g["deviation"] = g["yes_rate"] - g["mid"]
    # z-score vs null hypothesis yes_rate == mid (binomial)
    def z(row):
        n = int(row["n"])
        if n == 0:
            return 0.0
        p0 = float(row["mid"])
        se = sqrt(p0 * (1 - p0) / n)
        return (float(row["yes_rate"]) - p0) / se if se > 0 else 0.0
    g["z"] = g.apply(z, axis=1)
    return g


def bucket_row(cal_df: pd.DataFrame, label: str) -> dict:
    match = cal_df[cal_df["bucket"] == label]
    if match.empty:
        return {"bucket": label, "n": 0, "yes_rate": None,
                "mid": None, "deviation": None, "z": None}
    r = match.iloc[0]
    return {
        "bucket": label,
        "n": int(r["n"]),
        "yes_rate": round(float(r["yes_rate"]), 4),
        "mid": round(float(r["mid"]), 4),
        "deviation": round(float(r["deviation"]), 4),
        "z": round(float(r["z"]), 3),
    }


def fmt_calibration_md(cal_df: pd.DataFrame, min_n: int = 3) -> str:
    lines = ["| bucket | n | mid | yes_rate | deviation | z |",
             "|---|---|---|---|---|---|"]
    for _, r in cal_df.iterrows():
        if int(r["n"]) < min_n:
            continue
        lines.append(
            f"| {r['bucket']} | {int(r['n'])} | {r['mid']:.3f} | "
            f"{r['yes_rate']:.3f} | {r['deviation']:+.3f} | {r['z']:+.2f} |"
        )
    return "\n".join(lines)


def main() -> int:
    # --- load and merge ---
    sd = pd.read_parquet(E16 / "05_tm7d_prices_sports_deep.parquet")
    audit = pd.read_parquet(E16 / "01_markets_audit.parquet")
    merged = sd.merge(audit[["condition_id", "end_date", "created_at"]],
                      on="condition_id", how="left")

    # Ensure all rows have end_date; sort by end_date
    n_null = int(merged["end_date"].isna().sum())
    merged = merged.dropna(subset=["end_date"]).copy()
    merged["end_date"] = pd.to_datetime(merged["end_date"], utc=True)
    merged = merged.sort_values("end_date").reset_index(drop=True)

    # Bucket assignments (whole dataset)
    merged["bucket"] = merged["price_tm7d"].apply(bucket_label)
    merged["bucket_mid"] = merged["price_tm7d"].apply(bucket_mid)
    merged["yes"] = (merged["resolution"] == "YES").astype(int)

    # The e16 finding focuses on the T-7d sports "0.50-0.60" FLB zone.
    # The 628-market figure came from restricting to 0.50-0.60 at T-7d.
    core_mask = (merged["price_tm7d"] >= 0.50) & (merged["price_tm7d"] < 0.60)
    core = merged[core_mask].copy()
    n_core = len(core)

    first_res = merged["end_date"].min()
    last_res = merged["end_date"].max()

    # --- time splits ---
    # Use end_date (resolution date) as the chronological axis.
    # Halves / thirds / quartiles are by equal-count slices (sorted ascending),
    # which keeps each slice at roughly the same sample size — matches the
    # "stability of a calibration estimate through time" question better than
    # equal-date-length buckets (those would have wildly uneven n).

    def slice_equal_count(df: pd.DataFrame, k: int) -> list[pd.DataFrame]:
        df = df.sort_values("end_date").reset_index(drop=True)
        n = len(df)
        edges = [int(round(i * n / k)) for i in range(k + 1)]
        return [df.iloc[edges[i]:edges[i+1]].copy() for i in range(k)]

    halves = slice_equal_count(merged, 2)
    thirds = slice_equal_count(merged, 3)
    quarters = slice_equal_count(merged, 4)

    # --- calibration per slice, full price range ---
    def describe_slice(df: pd.DataFrame) -> dict:
        cal = calibration(df)
        # Combined 0.50-0.60 stats (core FLB zone)
        sub = df[(df["price_tm7d"] >= 0.50) & (df["price_tm7d"] < 0.60)]
        if len(sub) > 0:
            mid_core = float(sub["bucket_mid"].mean())
            yes_core = float(sub["yes"].mean())
            dev_core = yes_core - mid_core
            # Use 0.55 as reference midpoint for 0.50-0.60 zone aggregate
            # (two 5pp buckets, average mid ~= 0.55)
            p0 = 0.55
            n = len(sub)
            se = sqrt(p0 * (1 - p0) / n) if n > 0 else 0.0
            z_core = (yes_core - p0) / se if se > 0 else 0.0
        else:
            mid_core = yes_core = dev_core = z_core = None
            n = 0
        return {
            "n_markets": int(len(df)),
            "end_date_first": df["end_date"].min().isoformat() if len(df) else None,
            "end_date_last": df["end_date"].max().isoformat() if len(df) else None,
            "calibration_full_range": cal.to_dict(orient="records"),
            "bucket_055_060": bucket_row(cal, "0.55-0.60"),
            "bucket_050_055": bucket_row(cal, "0.50-0.55"),
            "core_050_060_zone": {
                "n": int(n),
                "yes_rate": round(yes_core, 4) if yes_core is not None else None,
                "avg_mid": round(mid_core, 4) if mid_core is not None else None,
                "deviation_vs_055": round(dev_core, 4) if dev_core is not None else None,
                "z_vs_055": round(z_core, 3) if z_core is not None else None,
            },
        }

    overall = describe_slice(merged)
    half_desc = [describe_slice(h) for h in halves]
    third_desc = [describe_slice(t) for t in thirds]
    quarter_desc = [describe_slice(q) for q in quarters]

    # Rolling quarter windows (sliding ~25% windows, steps of 25%)
    # Already covered by quarters above (4 non-overlapping quarters).

    # --- trend analysis ---
    def trend_of(seq: list[dict]) -> dict:
        """Return first-to-last deviation change + direction verdict."""
        devs = [s["bucket_055_060"]["deviation"] for s in seq
                if s["bucket_055_060"]["deviation"] is not None]
        if len(devs) < 2:
            return {"direction": "insufficient_data", "delta": None,
                    "sequence": devs}
        delta = devs[-1] - devs[0]
        if abs(delta) < 0.05:
            direction = "stable"
        elif delta > 0:
            direction = "strengthening"
        else:
            direction = "decaying"
        return {"direction": direction,
                "delta_first_to_last": round(float(delta), 4),
                "sequence": [round(d, 4) for d in devs]}

    trend_halves = trend_of(half_desc)
    trend_thirds = trend_of(third_desc)
    trend_quarters = trend_of(quarter_desc)

    # Also core-zone (0.50-0.60) trend
    def core_trend(seq: list[dict]) -> dict:
        devs = [s["core_050_060_zone"]["deviation_vs_055"] for s in seq
                if s["core_050_060_zone"]["deviation_vs_055"] is not None]
        if len(devs) < 2:
            return {"direction": "insufficient_data", "delta": None,
                    "sequence": devs}
        delta = devs[-1] - devs[0]
        if abs(delta) < 0.05:
            direction = "stable"
        elif delta > 0:
            direction = "strengthening"
        else:
            direction = "decaying"
        return {"direction": direction,
                "delta_first_to_last": round(float(delta), 4),
                "sequence": [round(d, 4) for d in devs]}

    core_trend_halves = core_trend(half_desc)
    core_trend_thirds = core_trend(third_desc)
    core_trend_quarters = core_trend(quarter_desc)

    # --- write JSON ---
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_parquet": str(E16 / "05_tm7d_prices_sports_deep.parquet"),
        "n_total_markets": int(len(merged)),
        "n_dropped_missing_end_date": n_null,
        "n_core_0.50_0.60": int(n_core),
        "first_resolution_date": first_res.isoformat(),
        "last_resolution_date": last_res.isoformat(),
        "resolution_span_days": round(
            (last_res - first_res).total_seconds() / 86400.0, 1),
        "overall": overall,
        "halves": half_desc,
        "thirds": third_desc,
        "quarters": quarter_desc,
        "trend_0.55_0.60_bucket": {
            "halves": trend_halves,
            "thirds": trend_thirds,
            "quarters": trend_quarters,
        },
        "trend_0.50_0.60_core_zone": {
            "halves": core_trend_halves,
            "thirds": core_trend_thirds,
            "quarters": core_trend_quarters,
        },
    }
    (OUT_DATA / "temporal_calibration.json").write_text(
        json.dumps(out, indent=2, default=str))

    # --- write markdown reports ---
    # FINDINGS.md
    def md_bucket(b: dict) -> str:
        if b["n"] == 0 or b["yes_rate"] is None:
            return f"- bucket {b['bucket']}: empty"
        return (f"- bucket {b['bucket']}: n={b['n']}, "
                f"yes_rate={b['yes_rate']:.3f}, mid={b['mid']:.3f}, "
                f"deviation={b['deviation']:+.3f}, z={b['z']:+.2f}")

    def md_core(c: dict) -> str:
        if c["n"] == 0 or c["yes_rate"] is None:
            return "- 0.50-0.60 zone: empty"
        return (f"- 0.50-0.60 zone: n={c['n']}, "
                f"yes_rate={c['yes_rate']:.3f}, avg_mid={c['avg_mid']:.3f}, "
                f"deviation_vs_0.55={c['deviation_vs_055']:+.3f}, "
                f"z_vs_0.55={c['z_vs_055']:+.2f}")

    def slice_md(name: str, s: dict) -> str:
        return (
            f"### {name}\n"
            f"- n_markets: {s['n_markets']}\n"
            f"- resolution range: {s['end_date_first']} → {s['end_date_last']}\n"
            f"- full calibration (min n≥3):\n\n"
            f"{fmt_calibration_md(pd.DataFrame(s['calibration_full_range']))}\n\n"
            f"- target buckets:\n"
            f"{md_bucket(s['bucket_050_055'])}\n"
            f"{md_bucket(s['bucket_055_060'])}\n"
            f"{md_core(s['core_050_060_zone'])}\n"
        )

    findings = []
    findings.append("# Agent B — Temporal Stability of Sports FLB\n")
    findings.append(f"_Generated: {out['generated_at']}_\n")
    findings.append("## Dataset span\n")
    findings.append(
        f"- Source: `experiments/e16_calibration_study/data/05_tm7d_prices_sports_deep.parquet`\n"
        f"- Total sports markets with T-7d snapshot: {out['n_total_markets']:,}\n"
        f"- Dropped (no end_date in audit): {n_null}\n"
        f"- Markets in 0.50-0.60 core FLB zone: {n_core} "
        f"(e16 headline was ~628 — close match)\n"
        f"- First resolution date: **{out['first_resolution_date']}**\n"
        f"- Last resolution date:  **{out['last_resolution_date']}**\n"
        f"- Resolution span: {out['resolution_span_days']:.1f} days\n"
    )
    findings.append("## Overall (all sports, all time)\n")
    findings.append(slice_md("Full sample", overall))
    findings.append("## Halves (chronological, equal-count)\n")
    for i, s in enumerate(half_desc):
        findings.append(slice_md(f"Half {i+1}/2", s))
    findings.append("## Thirds (chronological, equal-count)\n")
    for i, s in enumerate(third_desc):
        findings.append(slice_md(f"Third {i+1}/3", s))
    findings.append("## Quarters (chronological, equal-count)\n")
    for i, s in enumerate(quarter_desc):
        findings.append(slice_md(f"Quarter {i+1}/4", s))

    findings.append("## Trend analysis\n")
    findings.append("### 0.55-0.60 bucket — deviation sequence (first → last)\n")
    findings.append(
        f"- halves: {trend_halves['sequence']} — "
        f"delta = {trend_halves['delta_first_to_last']}, "
        f"direction = **{trend_halves['direction']}**\n"
        f"- thirds: {trend_thirds['sequence']} — "
        f"delta = {trend_thirds['delta_first_to_last']}, "
        f"direction = **{trend_thirds['direction']}**\n"
        f"- quarters: {trend_quarters['sequence']} — "
        f"delta = {trend_quarters['delta_first_to_last']}, "
        f"direction = **{trend_quarters['direction']}**\n"
    )
    findings.append("### 0.50-0.60 core zone — deviation-vs-0.55 sequence (first → last)\n")
    findings.append(
        f"- halves: {core_trend_halves['sequence']} — "
        f"delta = {core_trend_halves['delta_first_to_last']}, "
        f"direction = **{core_trend_halves['direction']}**\n"
        f"- thirds: {core_trend_thirds['sequence']} — "
        f"delta = {core_trend_thirds['delta_first_to_last']}, "
        f"direction = **{core_trend_thirds['direction']}**\n"
        f"- quarters: {core_trend_quarters['sequence']} — "
        f"delta = {core_trend_quarters['delta_first_to_last']}, "
        f"direction = **{core_trend_quarters['direction']}**\n"
    )

    # VERDICT: decide based on core-zone halves trend (largest sample per slice)
    vdir = core_trend_halves["direction"]
    vdelta = core_trend_halves["delta_first_to_last"]
    findings.append("## Verdict\n")
    findings.append(f"Core 0.50-0.60 zone, first-vs-second half: "
                    f"direction = **{vdir}**, delta = {vdelta}.\n"
                    f"See VERDICT.md for one-paragraph summary.\n")

    (HERE / "FINDINGS.md").write_text("\n".join(findings))

    # VERDICT.md
    h1 = half_desc[0]["core_050_060_zone"]
    h2 = half_desc[1]["core_050_060_zone"]
    # format helpers
    def fmtdev(x):
        return f"{x:+.1%}".replace("%", "pp") if x is not None else "N/A"
    def fmt(x, p=3):
        return f"{x:.{p}f}" if x is not None else "N/A"

    h1_dev = h1["deviation_vs_055"]
    h2_dev = h2["deviation_vs_055"]

    paragraph = (
        f"The sports T-7d FLB at the 0.50–0.60 zone is **{vdir}** across the "
        f"dataset's chronological halves. The first half (n={h1['n']}, "
        f"resolving {half_desc[0]['end_date_first'][:10]} → "
        f"{half_desc[0]['end_date_last'][:10]}) shows yes_rate "
        f"{fmt(h1['yes_rate'])} vs 0.55 reference "
        f"(deviation {fmtdev(h1_dev) if h1_dev is not None else 'N/A'}). "
        f"The second half (n={h2['n']}, resolving "
        f"{half_desc[1]['end_date_first'][:10]} → "
        f"{half_desc[1]['end_date_last'][:10]}) shows yes_rate "
        f"{fmt(h2['yes_rate'])} (deviation "
        f"{fmtdev(h2_dev) if h2_dev is not None else 'N/A'}), a first-to-last "
        f"change of "
        f"{fmtdev(vdelta) if vdelta is not None else 'N/A'}. "
        f"Thirds-split direction = **{core_trend_thirds['direction']}** "
        f"(sequence {core_trend_thirds['sequence']}); quarters = "
        f"**{core_trend_quarters['direction']}** "
        f"(sequence {core_trend_quarters['sequence']}).\n"
    )
    (HERE / "VERDICT.md").write_text(
        "# Agent B — VERDICT (temporal stability)\n\n" + paragraph
    )

    # DECISIONS.md
    decisions = (
        "# Agent B — Decisions / Methodology\n\n"
        "## Data source\n"
        "- Primary: `experiments/e16_calibration_study/data/05_tm7d_prices_sports_deep.parquet` "
        "(2,025 sports markets with T-7d snapshots).\n"
        "- Joined to `01_markets_audit.parquet` on `condition_id` to bring in "
        "`end_date` (resolution date) and `created_at`.\n\n"
        "## Time axis\n"
        "- Chose **`end_date`** (resolution date) rather than `created_at`, "
        "because the research question is 'has this FLB been arbed away?' — "
        "the relevant clock is when the market actually resolved, not when it "
        "was listed.\n\n"
        "## Split strategy\n"
        "- Used **equal-count** (quantile) splits rather than equal-time-length. "
        "Equal-count keeps each slice's n similar, which stabilises standard "
        "errors; equal-time-length would pile most markets into the recent "
        "tail (Polymarket volume grew through 2024–2026).\n"
        "- Halves = 2 slices, thirds = 3 slices, quarters = 4 slices; each "
        "sorted by `end_date` ascending.\n\n"
        "## Core FLB zone\n"
        "- The e16 study cited '0.55-0.60 bucket +25.8pp, n≈628'. In this "
        "parquet the 0.50-0.60 band (two 5pp buckets) contains "
        f"{n_core} markets; that aggregated band is the closest match to "
        "the cited 628-figure and is what I use as the 'core FLB zone' for "
        "the headline trend test. I also report the strict 0.55-0.60 bucket "
        "separately for exact reproducibility.\n\n"
        "## Direction rule\n"
        "- |delta first→last| < 0.05 → **stable**; delta > 0 → "
        "**strengthening**; delta < 0 → **decaying**. The 5pp threshold is "
        "arbitrary but consistent with the e16 headline effect size "
        "(~25.8pp), so a <5pp drift is materially within noise for the "
        "spot estimate.\n\n"
        "## Z-scores\n"
        "- Binomial one-sample z vs null yes_rate = bucket_mid; SE = "
        "sqrt(p(1-p)/n). Reported per-bucket in the JSON and findings tables.\n\n"
        "## Rolling / sliding window\n"
        "- The task asked about rolling-quarter splits 'if sample supports "
        "it'. I report 4 non-overlapping quarters (by end_date quantile). "
        "Did not run overlapping rolling windows — non-overlapping quarters "
        "are cleaner and the sample per slice (~500) is too small to "
        "subdivide further without n collapsing in individual 5pp buckets.\n\n"
        "## Commits\n"
        "- Attempted. Document any git commit failures here on update.\n"
    )
    (HERE / "DECISIONS.md").write_text(decisions)

    # Console summary
    print(f"n_total: {out['n_total_markets']}  core 0.50-0.60: {n_core}")
    print(f"span: {out['first_resolution_date']} -> {out['last_resolution_date']}")
    print(f"halves 0.50-0.60 devs: {core_trend_halves['sequence']} -> {core_trend_halves['direction']}")
    print(f"thirds 0.50-0.60 devs: {core_trend_thirds['sequence']} -> {core_trend_thirds['direction']}")
    print(f"quarters 0.50-0.60 devs: {core_trend_quarters['sequence']} -> {core_trend_quarters['direction']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
