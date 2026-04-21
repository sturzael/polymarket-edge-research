"""Aggregate all cross-venue results — deduplicated and filtered.

Pulls from data/06 (football) and data/08 (US sports) and produces a
single canonical table, then computes the spread calibration by bucket
and by sport, separately, with volume filter to drop noise pairs.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

DATA_DIR = Path(__file__).parent.parent / "data"

def main():
    # Load both datasets
    df_fb = pd.read_parquet(DATA_DIR / "06_drilldown.parquet")
    df_fb["sport"] = "football_soccer"
    df_fb["vol_for_filter"] = df_fb["pm_vol24h"].fillna(df_fb["pm_vol"]).fillna(0)
    df_fb = df_fb.rename(columns={"pm_team":"team"})
    df_fb = df_fb[["team","sport","pm_yes","sm_mid","sm_bid","sm_offer",
                    "spread","vol_for_filter","pm_question"]]

    df_us = pd.read_parquet(DATA_DIR / "08_us_sports.parquet")
    df_us["vol_for_filter"] = df_us["pm_vol24h"].fillna(0)
    df_us["pm_question"] = df_us["pm_event"]
    df_us = df_us[["team","sport","pm_yes","sm_mid","sm_bid","sm_offer",
                    "spread","vol_for_filter","pm_question"]]

    df = pd.concat([df_fb, df_us], ignore_index=True)
    # Drop mismatches (huge spreads) and near-zero-vol noise
    df["abs_spread"] = df["spread"].abs()
    clean = df[(df["vol_for_filter"] >= 1) & (df["abs_spread"] <= 0.15)].copy()
    print(f"total: {len(df)}  with vol>=1: {(df['vol_for_filter']>=1).sum()}  "
          f"clean (<=15pp): {len(clean)}")

    # Deduplicate: keep one record per unique (pm_question, team) — sometimes
    # the same match is in both datasets or repeated across scripts.
    clean = clean.drop_duplicates(subset=["pm_question","team"], keep="first")
    print(f"after dedup: {len(clean)}")

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_raw": int(len(df)),
        "n_clean": int(len(clean)),
        "by_sport": {},
    }
    for sp, g in clean.groupby("sport"):
        summary["by_sport"][sp] = {
            "n": int(len(g)),
            "mean_spread": round(float(g["spread"].mean()), 4),
            "median_spread": round(float(g["spread"].median()), 4),
            "stdev_spread": round(float(g["spread"].std()), 4),
            "abs_mean_spread": round(float(g["spread"].abs().mean()), 4),
        }

    # Overall + by bucket
    summary["overall"] = {
        "n": int(len(clean)),
        "mean": round(float(clean["spread"].mean()), 4),
        "median": round(float(clean["spread"].median()), 4),
        "stdev": round(float(clean["spread"].std()), 4),
        "abs_mean": round(float(clean["spread"].abs().mean()), 4),
        "pct_gt_1pp": round(float((clean["abs_spread"] > 0.01).mean()), 4),
        "pct_gt_2pp": round(float((clean["abs_spread"] > 0.02).mean()), 4),
        "pct_gt_5pp": round(float((clean["abs_spread"] > 0.05).mean()), 4),
    }

    # By-bucket breakdown
    clean["bucket"] = (clean["pm_yes"] * 20).astype(int) / 20
    bucket_rows = []
    for b, g in clean.groupby("bucket"):
        if len(g) >= 2:
            bucket_rows.append({
                "bucket_lo": round(float(b), 4),
                "bucket_hi": round(float(b) + 0.05, 4),
                "n": int(len(g)),
                "pm_mean": round(float(g["pm_yes"].mean()), 4),
                "sm_mean": round(float(g["sm_mid"].mean()), 4),
                "spread_mean": round(float(g["spread"].mean()), 4),
                "spread_median": round(float(g["spread"].median()), 4),
                "abs_spread_mean": round(float(g["spread"].abs().mean()), 4),
            })
    summary["by_pm_bucket"] = bucket_rows

    # FLB-peak bucket specifically (0.55-0.60)
    fav = clean[(clean["pm_yes"] >= 0.55) & (clean["pm_yes"] < 0.60)]
    summary["fav_bucket_0.55_0.60"] = {
        "n": int(len(fav)),
        "pm_mean": round(float(fav["pm_yes"].mean()), 4),
        "sm_mean": round(float(fav["sm_mid"].mean()), 4),
        "spread_mean": round(float(fav["spread"].mean()), 4),
        "spread_stdev": round(float(fav["spread"].std()), 4),
    }

    # Extended favorite range 0.50-0.70
    favx = clean[(clean["pm_yes"] >= 0.50) & (clean["pm_yes"] < 0.70)]
    summary["fav_range_0.50_0.70"] = {
        "n": int(len(favx)),
        "spread_mean": round(float(favx["spread"].mean()), 4),
        "spread_median": round(float(favx["spread"].median()), 4),
        "spread_stdev": round(float(favx["spread"].std()), 4),
        "abs_spread_mean": round(float(favx["spread"].abs().mean()), 4),
    }

    print(f"\n=== FINAL SUMMARY ===")
    print(f"clean pairs: n={len(clean)}")
    print(f"  overall mean spread: {summary['overall']['mean']:+.4f}")
    print(f"  |spread| mean: {summary['overall']['abs_mean']:.4f}")
    print(f"  pct |spread|>2pp: {summary['overall']['pct_gt_2pp']:.1%}")
    print(f"\nBy sport:")
    for sp, s in summary["by_sport"].items():
        print(f"  {sp:<20} n={s['n']:>3}  mean={s['mean_spread']:+.4f}  "
              f"|mean|={s['abs_mean_spread']:.4f}")

    print(f"\n0.55-0.60 fav bucket:")
    f = summary["fav_bucket_0.55_0.60"]
    print(f"  n={f['n']}  pm_mean={f['pm_mean']:.4f}  sm_mean={f['sm_mean']:.4f}  "
          f"spread={f['spread_mean']:+.4f}  stdev={f['spread_stdev']:.4f}")

    print(f"\n0.50-0.70 favorite range:")
    f = summary["fav_range_0.50_0.70"]
    print(f"  n={f['n']}  spread_mean={f['spread_mean']:+.4f}  "
          f"median={f['spread_median']:+.4f}  stdev={f['spread_stdev']:.4f}")

    print("\n=== BY BUCKET ===")
    print(f"  {'bucket':<14}  {'n':>4}  {'pm':>6}  {'sm':>6}  {'sp_mean':>7}")
    for r in bucket_rows:
        print(f"  [{r['bucket_lo']:.2f},{r['bucket_hi']:.2f})    "
              f"{r['n']:>4}  {r['pm_mean']:>.3f}  {r['sm_mean']:>.3f}  "
              f"{r['spread_mean']:>+7.4f}")

    (DATA_DIR / "09_final_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    clean.to_parquet(DATA_DIR / "09_final_pairs.parquet", index=False)


if __name__ == "__main__":
    main()
