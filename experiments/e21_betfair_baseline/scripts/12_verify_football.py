"""Check what's going into the 0.95-1.00 bucket."""
import pandas as pd
import pathlib

RAW = pathlib.Path(__file__).parent.parent / "data" / "raw_football"
frames = []
for p in sorted(RAW.glob("*.csv")):
    df = pd.read_csv(p, encoding="latin-1", on_bad_lines="skip", low_memory=False)
    df["__source"] = p.name
    frames.append(df)
allm = pd.concat(frames, ignore_index=True)

# Convert BFEH,BFED,BFEA to numeric
for col in ["BFEH","BFED","BFEA"]:
    allm[col] = pd.to_numeric(allm[col], errors="coerce")

# Check the distribution of BFEH (home)
print("BFEH distribution:")
print(allm["BFEH"].describe())
print(f"\nBFEH <= 1.05: {(allm['BFEH'] <= 1.05).sum()}")
print(f"BFEH <= 1.02: {(allm['BFEH'] <= 1.02).sum()}")
print(f"BFEH between 1.2 and 2.0: {((allm['BFEH'] >= 1.2) & (allm['BFEH'] <= 2.0)).sum()}")

# Sanity: for each match, sum of implied probs should be ~1 + overround
ip_sum = 1/allm["BFEH"] + 1/allm["BFED"] + 1/allm["BFEA"]
print(f"\nImplied prob sum across H+D+A:")
print(ip_sum.describe())

# Maybe I'm double-counting. Let me re-derive the 0.95-1.00 count
for col in ["BFEH","BFED","BFEA"]:
    p = 1.0 / allm[col]
    n_high = ((p >= 0.95) & (p < 1.0)).sum()
    print(f"{col} >= 0.95 prob (odds <= 1.053): {n_high}")
