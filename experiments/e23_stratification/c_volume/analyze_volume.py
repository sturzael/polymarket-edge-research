"""Agent C (e23): Volume stratification of sports FLB.

Splits the sports T-7d calibration sample into three volume tiers based on
total_usd_window (USD transacted in the ±12h window around T-7d), and
produces tier-specific calibration tables plus tradability metrics.

Tiers:
    Tier 1: total_usd_window <  $500
    Tier 2: $500  <= total_usd_window < $5,000
    Tier 3:        total_usd_window >= $5,000

Reads:  experiments/e16_calibration_study/data/05_tm7d_prices_sports_deep.parquet
Writes: experiments/e23_stratification/c_volume/data/volume_calibration.json
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "experiments/e16_calibration_study/data/05_tm7d_prices_sports_deep.parquet"
OUT_DIR = Path(__file__).resolve().parent / "data"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_JSON = OUT_DIR / "volume_calibration.json"

BUCKETS = [(i / 100.0, (i + 5) / 100.0) for i in range(0, 100, 5)]
TIERS = [
    ("tier1_lt_500",     "<$500",     0.0,   500.0),
    ("tier2_500_5k",     "$500-$5k",  500.0, 5_000.0),
    ("tier3_ge_5k",      ">=$5k",     5_000.0, float("inf")),
]


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
    g = (df.groupby("bucket")
           .agg(n=("yes", "size"),
                yes_rate=("yes", "mean"),
                mid=("bucket_mid", "mean"))
           .reset_index()
           .sort_values("bucket"))
    g["deviation"] = g["yes_rate"] - g["mid"]
    return g


def trade_size_percentiles(df: pd.DataFrame) -> dict:
    """Percentiles of single-fill capacity in a tier."""
    pct = [25, 50, 75, 90, 95, 99]
    out = {}
    for col in ("max_single_trade_usd", "median_trade_usd", "total_usd_window", "n_trades_window"):
        out[col] = {f"p{p}": float(df[col].quantile(p / 100)) for p in pct}
        out[col]["mean"] = float(df[col].mean())
        out[col]["min"]  = float(df[col].min())
        out[col]["max"]  = float(df[col].max())
    return out


def main() -> None:
    df = pd.read_parquet(SRC)
    df["bucket"] = df["price_tm7d"].apply(bucket_label)
    df["bucket_mid"] = df["price_tm7d"].apply(bucket_mid)
    df["yes"] = (df["resolution"] == "YES").astype(int)

    assert (df["category"].str.startswith("sports_")).all(), "expect all sports"

    # Tier assignment
    def tier_of(v: float) -> str:
        for key, _, lo, hi in TIERS:
            if lo <= v < hi:
                return key
        return "tier3_ge_5k"  # inf upper open
    df["tier"] = df["total_usd_window"].apply(tier_of)

    focus_bucket = "0.55-0.60"
    focus_df = df[df["bucket"] == focus_bucket]
    total_focus = len(focus_df)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_parquet": str(SRC.relative_to(ROOT)),
        "n_markets_total": int(len(df)),
        "n_markets_focus_bucket_0p55_0p60": int(total_focus),
        "tiers_definition": {key: {"label": label, "lo": lo, "hi": hi} for key, label, lo, hi in TIERS},
        "by_tier": {},
        "overall": {
            "calibration": calibration_table(df).to_dict(orient="records"),
            "corr_price_yes": round(float(df["price_tm7d"].corr(df["yes"])), 4),
        },
        "focus_bucket_tier_fractions": {},
    }

    for key, label, lo, hi in TIERS:
        tdf = df[df["tier"] == key].copy()
        cal = calibration_table(tdf)
        # focus row
        focus_row = cal[cal["bucket"] == focus_bucket]
        if len(focus_row):
            n_focus = int(focus_row["n"].iloc[0])
            yr_focus = float(focus_row["yes_rate"].iloc[0])
            dev_focus = float(focus_row["deviation"].iloc[0])
        else:
            n_focus = 0
            yr_focus = float("nan")
            dev_focus = float("nan")

        tier_focus_fraction = (n_focus / total_focus) if total_focus else 0.0

        payload["by_tier"][key] = {
            "label": label,
            "n_markets": int(len(tdf)),
            "share_of_total": round(len(tdf) / len(df), 4),
            "calibration": cal.to_dict(orient="records"),
            "focus_bucket_n": n_focus,
            "focus_bucket_yes_rate": round(yr_focus, 4) if n_focus else None,
            "focus_bucket_deviation": round(dev_focus, 4) if n_focus else None,
            "focus_bucket_insufficient": bool(n_focus < 20),
            "tradability_percentiles": trade_size_percentiles(tdf) if len(tdf) else {},
            "corr_price_yes": round(float(tdf["price_tm7d"].corr(tdf["yes"])), 4) if len(tdf) > 1 else None,
            "yes_count": int(tdf["yes"].sum()),
        }
        payload["focus_bucket_tier_fractions"][key] = {
            "n_in_focus_bucket": n_focus,
            "fraction_of_focus_bucket": round(tier_focus_fraction, 4),
        }

    OUT_JSON.write_text(json.dumps(payload, indent=2, default=str))
    print(f"wrote {OUT_JSON}")

    # Console summary
    print("\n=== VOLUME STRATIFICATION (T-7d, sports, n={:,}) ===".format(len(df)))
    print(f"focus bucket 0.55-0.60 total n = {total_focus}\n")
    for key, label, _, _ in TIERS:
        t = payload["by_tier"][key]
        print(f"--- {label}  (n={t['n_markets']:,}, share={t['share_of_total']:.1%}) ---")
        print(f"  focus 0.55-0.60: n={t['focus_bucket_n']}  "
              f"yes_rate={t['focus_bucket_yes_rate']}  "
              f"dev={t['focus_bucket_deviation']}  "
              f"insufficient={t['focus_bucket_insufficient']}")
        if t["tradability_percentiles"]:
            mx = t["tradability_percentiles"]["max_single_trade_usd"]
            med = t["tradability_percentiles"]["median_trade_usd"]
            print(f"  max_single_trade_usd  p50={mx['p50']:.0f}  p90={mx['p90']:.0f}  p99={mx['p99']:.0f}")
            print(f"  median_trade_usd      p50={med['p50']:.0f}  p90={med['p90']:.0f}  p99={med['p99']:.0f}")
        print()


if __name__ == "__main__":
    main()
