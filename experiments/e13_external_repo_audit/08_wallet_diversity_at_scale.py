"""H1 wallet-diversity, second pass — broader scope, larger sample.

The first pass (05) was too narrow:
  - n=336 rows / 121 wallets / 41 markets
  - filter: price >= 0.95 AND ±30min of end_date
  - max 100 row groups of users.parquet (out of 939)

The original H1 measurement (per docs/OPPORTUNITY_SPORTS_EVENT_LAG_ARB.md) looked
at "the arb window flow" — top buyers per market — not a strict price band.
This rerun reproduces that scope:

  - Drop the price filter; keep only the post-resolution time window
  - Bump MAX_USER_ROW_GROUPS to 400 (~43% of users.parquet)
  - Report wallet concentration globally AND per-market (so we can compare
    "411 distinct wallets across 5 markets" to the docs claim apples-to-apples)

Output:
  data/08_wallet_diversity_at_scale.json
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from huggingface_hub import HfFileSystem

DATASET = "SII-WANGZJ/Polymarket_data"
DATA_DIR = Path(__file__).parent / "data"
PROBE_JSON = DATA_DIR / "01_probe.json"
OUT_JSON = DATA_DIR / "08_wallet_diversity_at_scale.json"

SPORTS_SLUG_PATTERNS = (
    "atp-", "wta-", "nba-", "nfl-", "nhl-", "mlb-",
    "cricipl-", "ufc-", "mls-", "wnba-",
)
RESOLUTION_WINDOW_MIN = 30
MAX_USER_ROW_GROUPS = 400


def gini(x: np.ndarray) -> float:
    if len(x) == 0:
        return 0.0
    x = np.sort(x.astype(float))
    n = len(x)
    if x.sum() == 0:
        return 0.0
    cum = np.cumsum(x)
    return (n + 1 - 2 * (cum.sum() / cum[-1])) / n


def main():
    if not PROBE_JSON.exists() or not json.loads(PROBE_JSON.read_text()).get("kill_criteria", {}).get("pass"):
        print("ABORT: 01 probe missing or did not pass")
        return 2
    probe = json.loads(PROBE_JSON.read_text())

    fs = HfFileSystem()
    print("[1/3] Loading sports market metadata...")
    df = pq.read_table(probe["markets"]["path"]).to_pandas()
    df["slug"] = df["slug"].astype(str).str.lower()
    sports = df[df["slug"].apply(lambda s: any(p in s for p in SPORTS_SLUG_PATTERNS))].copy()
    if "closed" in sports.columns:
        sports = sports[sports["closed"] == 1]
    sports["end_date_ts"] = (sports["end_date"] - pd.Timestamp("1970-01-01", tz="UTC")).dt.total_seconds()
    print(f"      {len(sports):,} resolved sports markets")
    sports_ids = set(sports["id"].astype(str))
    end_by_id = dict(zip(sports["id"].astype(str), sports["end_date_ts"]))

    print(f"[2/3] Streaming users.parquet (max {MAX_USER_ROW_GROUPS} RG, NO price filter)...")
    path = f"datasets/{DATASET}/users.parquet"
    chunks = []
    t0 = time.time()
    with fs.open(path, "rb") as f:
        pf = pq.ParquetFile(f)
        cols = ["timestamp", "address", "role", "direction",
                "usd_amount", "token_amount", "price", "market_id"]
        existing = [c for c in cols if c in pf.schema_arrow.names]
        for rg_idx in range(min(pf.metadata.num_row_groups, MAX_USER_ROW_GROUPS)):
            rg = pf.read_row_group(rg_idx, columns=existing).to_pandas()
            rg["market_id"] = rg["market_id"].astype(str)
            keep = rg[rg["market_id"].isin(sports_ids)]
            if keep.empty:
                continue
            keep = keep.copy()
            keep["_end_ts"] = keep["market_id"].map(end_by_id)
            ts_norm = keep["timestamp"].apply(lambda v: v/1000 if v > 1e12 else v)
            keep["_delta_min"] = (ts_norm - keep["_end_ts"]) / 60
            # Post-resolution window only (no price filter)
            keep = keep[keep["_delta_min"].between(-2, RESOLUTION_WINDOW_MIN)]
            if len(keep) > 0:
                chunks.append(keep)
            if rg_idx % 20 == 0:
                tot = sum(len(c) for c in chunks)
                rate = (rg_idx+1)/max(time.time()-t0, 0.1)
                print(f"      RG {rg_idx+1}: matched={tot:,} ({rate:.1f} RG/s)")

    if not chunks:
        out = {"error": "no sports post-resolution wallet rows in scanned RGs"}
    else:
        users = pd.concat(chunks, ignore_index=True)
        users["address"] = users["address"].apply(
            lambda b: b.hex() if isinstance(b, (bytes, bytearray)) else str(b))
        # Volume per wallet
        vol = users.groupby("address")["usd_amount"].sum().sort_values(ascending=False)
        total_vol = float(vol.sum())
        top_n = lambda n: float(vol.head(n).sum() / max(total_vol, 1e-9))

        # Per-market diversity (apples-to-apples vs docs' "411 wallets across 5 markets")
        per_mkt_distinct = users.groupby("market_id")["address"].nunique()

        out = {
            "n_rows": int(len(users)),
            "n_distinct_wallets": int(users["address"].nunique()),
            "n_distinct_markets": int(users["market_id"].nunique()),
            "wallets_per_market_avg": round(float(per_mkt_distinct.mean()), 1),
            "wallets_per_market_median": int(per_mkt_distinct.median()),
            "wallets_per_market_p95": int(per_mkt_distinct.quantile(0.95)),
            "total_volume_usd": round(total_vol, 2),
            "top1_share": round(top_n(1), 4),
            "top10_share": round(top_n(10), 4),
            "top50_share": round(top_n(50), 4),
            "top100_share": round(top_n(100), 4),
            "gini_volume": round(gini(vol.values), 4),
            "verdict_h1_diffuse": bool(top_n(10) < 0.50),
            "max_user_row_groups": MAX_USER_ROW_GROUPS,
            "rg_coverage_pct": round(MAX_USER_ROW_GROUPS / 939 * 100, 1),
        }
        # Top 10 wallets by volume (truncated addrs for sanity check)
        top10 = vol.head(10).reset_index()
        out["top10_wallets"] = [
            {"address_truncated": f"{r.address[:6]}...{r.address[-4:]}",
             "volume_usd": round(float(r.usd_amount), 2)}
            for r in top10.itertuples()
        ]
    out["probed_at"] = datetime.now(timezone.utc).isoformat()
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str))
    print()
    print("=" * 60)
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
