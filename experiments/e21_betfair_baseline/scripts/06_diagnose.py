"""Diagnose the 0.95-1.00 bucket anomaly.

Hypothesis: some rows have residual in-play prices after first-bounce/kickoff has
already been recorded, OR the BEST_BACK_PRICE_XX_MIN_PRIOR columns can sometimes
reflect post-event residuals.
"""
from __future__ import annotations
import pandas as pd
import pathlib

DATA = pathlib.Path(__file__).parent.parent / "data"
df = pd.read_parquet(DATA / "sports_records.parquet")
print(f"total records: {len(df):,}")

# Inspect p_T-60min_back between 0.95 and 1.0
anchor = "p_T-60min_back"
high = df[(df[anchor] >= 0.95) & (df[anchor] < 1.00)]
print(f"\n0.95-1.00 bucket at T-60min_back: {len(high):,}")
print(f"  is_winner mean: {high['is_winner'].mean():.3f}")
print(f"  sport breakdown:")
print(high.groupby("sport").agg(n=("is_winner","size"), yes_rate=("is_winner","mean")))

# Look at corresponding files
print(f"\n  file breakdown:")
print(high.groupby("file").agg(n=("is_winner","size"), yes_rate=("is_winner","mean")).sort_values("n", ascending=False).head(20))

# Check if these are "losing side" rows with price ~ 1/0.025 * (1-eps). For 2-way markets,
# the losing side shouldn't be priced at ~0.975 (implied) at T-60min unless something's wrong.
print(f"\n  sample 10 rows:")
print(high.sample(min(10, len(high)), random_state=42)[["file","event_id","market_id","selection_id","is_winner",anchor,"total_matched"]].to_string())

# Now check the LOWER 0.00-0.05 bucket — the mirror image
low = df[(df[anchor] >= 0.0) & (df[anchor] < 0.05)]
print(f"\n0.00-0.05 bucket at T-60min_back: {len(low):,}")
print(f"  is_winner mean: {low['is_winner'].mean():.3f}  (should be ~0.025)")

# Check: in a 2-way match-odds, for each (event_id, market_id) there should be 2 selections
# whose implied_p should sum to ~1 (with overround). Let's verify.
agg = df.groupby(["event_id","market_id"]).agg(
    n_sel=(anchor, "size"),
    sum_p=(anchor, "sum"),
    mean_p=(anchor, "mean"),
).reset_index()
print(f"\nmarket-level stats:")
print(f"  markets: {len(agg):,}")
print(f"  selections/market: mean={agg['n_sel'].mean():.2f}  median={agg['n_sel'].median():.0f}")
print(f"  sum_p stats (should be ~1.0+overround):")
print(agg["sum_p"].describe())

# Check what markets are in the 0.95-1.00 bucket
print(f"\nRunners priced at 0.95+ AND losing — look at market structure")
weird = high[high["is_winner"] == 0].head(5)
for _, row in weird.iterrows():
    mid = row["market_id"]
    ev = row["event_id"]
    same_market = df[(df["event_id"] == ev) & (df["market_id"] == mid)]
    print(f"\n  event={ev} market={mid} from {row['file']}")
    for _, sr in same_market.iterrows():
        p = sr.get(anchor)
        print(f"    selection={sr['selection_id']}  p={p}  is_winner={sr['is_winner']}  total_matched={sr['total_matched']}")
