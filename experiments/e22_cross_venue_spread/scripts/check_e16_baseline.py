"""Compare e22 findings to e16 baseline shape."""
import pandas as pd

# The T-7d calibration data
path = "experiments/e16_calibration_study/data/05_tm7d_prices.parquet"
df = pd.read_parquet(path)
print("e16 T-7d data:")
print("  columns:", list(df.columns))
print("  n:", len(df))
print("  categories:", df["category"].value_counts().head(10).to_dict())

# Bucket, 0.55-0.60, sports
if "price_tm7d" in df.columns:
    print("\n=== e16 T-7d per-bucket ALL ===")
    df["bucket"] = (df["price_tm7d"] * 20).astype(int) / 20
    df["resolved_yes"] = (df["resolution"] == "YES").astype(int)
    for b, g in df.groupby("bucket"):
        if 0.05 <= b <= 0.85 and len(g) >= 3:
            rate = g["resolved_yes"].mean()
            print(f"  [{b:.2f}-{b+0.05:.2f})  n={len(g):>4}  price={g['price_tm7d'].mean():.3f}  yes_rate={rate:.3f}  dev={rate-(b+0.025):+.3f}")

    # Sports only
    sp = df[df["category"].str.startswith("sports_")]
    print(f"\n=== e16 T-7d SPORTS ONLY (n={len(sp)}) ===")
    for b, g in sp.groupby("bucket"):
        if 0.05 <= b <= 0.85 and len(g) >= 3:
            rate = g["resolved_yes"].mean()
            print(f"  [{b:.2f}-{b+0.05:.2f})  n={len(g):>4}  price={g['price_tm7d'].mean():.3f}  yes_rate={rate:.3f}  dev={rate-(b+0.025):+.3f}")
