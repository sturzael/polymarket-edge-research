"""Diagnose football 0.95-1.00 contamination."""
import pandas as pd
import pathlib

RAW = pathlib.Path(__file__).parent.parent / "data" / "raw_football"
frames = []
for p in sorted(RAW.glob("*.csv")):
    df = pd.read_csv(p, encoding="latin-1", on_bad_lines="skip", low_memory=False)
    df["__league"] = p.stem
    frames.append(df)
allm = pd.concat(frames, ignore_index=True)
print(f"total matches: {len(allm):,}")

for col in ["BFEH","BFED","BFEA","BFECH","BFECD","BFECA","PSH","PSD","PSA","B365H","B365D","B365A"]:
    if col in allm.columns:
        total = len(allm)
        notnull = allm[col].notna().sum()
        numeric = pd.to_numeric(allm[col], errors="coerce")
        valid = numeric[(numeric > 1.0) & (numeric < 1000)].count()
        gt_20 = (numeric >= 20).sum()
        print(f"  {col}: {notnull:,}/{total:,} notnull, {valid:,} valid (1<x<1000), {gt_20:,} >=20")
