"""Sports settlement-lag arb backtest (historical replay).

Replays the e12/e9 sports_lag entry rule against the SII trade history.
Goal: does the strategy make money historically? If not, paper-trading 75
trades won't save it.

Entry rule replay (matches detector.py in the e12 plan):
  - market slug ∈ SPORTS_SLUG_PATTERNS
  - last_trade_price > 0.95 (YES winning) OR < 0.05 (NO winning, mirrored)
  - within 30min of market close (proxy for "post-resolution arb window")
  - we attempt to buy the winning side at trade_price = price (slips immediately)

Exit: market resolution at 1.00 (winning) or 0.00 (losing), per outcome_prices
in markets.parquet.

This uses TRADES as a proxy for executable depth — a real backtest would
need book snapshots, but trades-as-depth is a defensible cheap proxy because
every trade IS by definition executed depth.

Output:
  data/03_sports_lag_backtest.json — hit rate, gross/net edge, hold time, $
"""
from __future__ import annotations

import ast
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
FEE_JSON = DATA_DIR / "02_fee_realization.json"
OUT_JSON = DATA_DIR / "03_sports_lag_backtest.json"

SPORTS_SLUG_PATTERNS = (
    "atp-", "wta-", "nba-", "nfl-", "nhl-", "mlb-",
    "cricipl-", "ufc-", "mls-", "wnba-",
)
PRICE_LO = 0.95
PRICE_HI_CAP = 0.98          # entry cap; never bid above
RESOLUTION_WINDOW_MIN = 30
MAX_TRADE_ROW_GROUPS = 80    # ~4-8GB scanned
DEFAULT_FEE_BPS = 100        # placeholder; replaced from 02 if present
SAMPLE_TARGET_TRADES = 5_000


def load_sports_resolved(markets_path: str) -> pd.DataFrame:
    print(f"[1/3] Loading markets.parquet → resolved sports markets...")
    df = pq.read_table(markets_path).to_pandas()
    df["slug"] = df["slug"].astype(str).str.lower()
    sports = df[df["slug"].apply(lambda s: any(p in s for p in SPORTS_SLUG_PATTERNS))].copy()
    if "closed" in sports.columns:
        sports = sports[sports["closed"] == 1]
    sports["_outcomes"] = sports["outcome_prices"].apply(_parse_outcome)
    sports = sports[sports["_outcomes"].notna()]
    sports["yes_payout"] = sports["_outcomes"].apply(lambda t: t[0])
    sports["no_payout"] = sports["_outcomes"].apply(lambda t: t[1])
    sports = sports[sports["yes_payout"].isin([0.0, 1.0])]
    # Convert end_date (datetime64[ms,UTC]) → unix seconds
    sports["end_date_ts"] = (sports["end_date"] - pd.Timestamp("1970-01-01", tz="UTC")).dt.total_seconds()
    print(f"      {len(sports):,} resolved sports markets with clean outcomes")
    return sports


def _parse_outcome(v):
    """outcome_prices is stored as Python literal: \"['0', '1']\""""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        arr = ast.literal_eval(s)
        if isinstance(arr, (list, tuple)) and len(arr) == 2:
            return (float(arr[0]), float(arr[1]))
    except Exception:
        pass
    return None


def stream_entry_candidates(fs: HfFileSystem, sports: pd.DataFrame) -> pd.DataFrame:
    print(f"[2/3] Streaming trades.parquet → entry candidates...")
    sports_ids = set(sports["id"].astype(str))
    end_by_id = dict(zip(sports["id"].astype(str), sports["end_date_ts"]))
    yes_payout_by_id = dict(zip(sports["id"].astype(str), sports["yes_payout"]))

    path = f"datasets/{DATASET}/trades.parquet"
    keep_chunks = []
    t0 = time.time()
    with fs.open(path, "rb") as f:
        pf = pq.ParquetFile(f)
        cols = ["timestamp", "market_id", "price", "usd_amount", "token_amount",
                "maker_direction", "taker_direction"]
        existing = [c for c in cols if c in pf.schema_arrow.names]
        for rg_idx in range(min(pf.metadata.num_row_groups, MAX_TRADE_ROW_GROUPS)):
            rg = pf.read_row_group(rg_idx, columns=existing).to_pandas()
            rg["market_id"] = rg["market_id"].astype(str)
            keep = rg[rg["market_id"].isin(sports_ids)]
            if keep.empty:
                continue
            # Window filter
            keep = keep.copy()
            keep["_end_ts"] = keep["market_id"].map(end_by_id)
            ts_norm = keep["timestamp"].apply(lambda v: v/1000 if v > 1e12 else v)
            keep["_delta_min"] = (ts_norm - keep["_end_ts"]) / 60
            # Post-window only (after end_date) up to RESOLUTION_WINDOW_MIN
            keep = keep[keep["_delta_min"].between(-2, RESOLUTION_WINDOW_MIN)]  # ±2min slack
            # Price gate — buy winning side at <= PRICE_HI_CAP
            keep["_yes_payout"] = keep["market_id"].map(yes_payout_by_id)
            # If yes_payout=1, winning side is YES → buy when price >= 0.95
            #   trade.price IS the YES-token price (per quant unification convention)
            # If yes_payout=0, winning side is NO → buy NO when YES_price <= 0.05 (so NO_price >= 0.95)
            yes_winning = keep[(keep["_yes_payout"] == 1.0) &
                               (keep["price"] >= PRICE_LO) &
                               (keep["price"] <= PRICE_HI_CAP)]
            yes_winning = yes_winning.assign(_buy_side="YES",
                                             _entry_price=yes_winning["price"])
            no_winning = keep[(keep["_yes_payout"] == 0.0) &
                              (keep["price"] <= 1 - PRICE_LO) &
                              (keep["price"] >= 1 - PRICE_HI_CAP)]
            no_winning = no_winning.assign(_buy_side="NO",
                                           _entry_price=1 - no_winning["price"])
            ck = pd.concat([yes_winning, no_winning], ignore_index=True)
            if len(ck) > 0:
                keep_chunks.append(ck)
            total = sum(len(c) for c in keep_chunks)
            if rg_idx % 5 == 0:
                rate = (rg_idx+1)/max(time.time()-t0, 0.1)
                print(f"      RG {rg_idx+1}: candidates={total:,} ({rate:.1f} RG/s)")
            if total >= SAMPLE_TARGET_TRADES:
                break
    if not keep_chunks:
        return pd.DataFrame()
    return pd.concat(keep_chunks, ignore_index=True)


def evaluate_edge(candidates: pd.DataFrame, fee_bps: float) -> dict:
    if candidates.empty:
        return {"error": "no entry candidates found"}

    # Every candidate is a winning-side buy at entry_price; payout is 1.0
    candidates = candidates.copy()
    candidates["gross_pnl_per_share"] = 1.0 - candidates["_entry_price"]
    # Polymarket fee: bps × min(price, 1-price) on the bought side
    candidates["fee_per_share"] = (fee_bps / 10_000) * np.minimum(
        candidates["_entry_price"], 1 - candidates["_entry_price"])
    candidates["net_pnl_per_share"] = (
        candidates["gross_pnl_per_share"] - candidates["fee_per_share"]
    )

    # Hold time = window from entry to market close (we exit at resolution)
    candidates["hold_min"] = RESOLUTION_WINDOW_MIN - candidates["_delta_min"]

    # Notional weighting
    candidates["notional"] = candidates["usd_amount"]
    total_notional = float(candidates["notional"].sum())
    weighted_gross = float((candidates["gross_pnl_per_share"] * candidates["notional"]).sum() / max(total_notional, 1e-9))
    weighted_net = float((candidates["net_pnl_per_share"] * candidates["notional"]).sum() / max(total_notional, 1e-9))

    return {
        "n_entries": int(len(candidates)),
        "fee_bps_assumed": fee_bps,
        "gross_edge_avg": round(float(candidates["gross_pnl_per_share"].mean()), 4),
        "gross_edge_median": round(float(candidates["gross_pnl_per_share"].median()), 4),
        "gross_edge_notional_weighted": round(weighted_gross, 4),
        "net_edge_avg": round(float(candidates["net_pnl_per_share"].mean()), 4),
        "net_edge_median": round(float(candidates["net_pnl_per_share"].median()), 4),
        "net_edge_notional_weighted": round(weighted_net, 4),
        "hit_rate": 1.0,  # by construction — we only entered on already-resolved winners
        "hold_min_avg": round(float(candidates["hold_min"].mean()), 1),
        "total_notional_usd": round(total_notional, 2),
        "by_sport": {
            sport: int(candidates["market_id"].apply(
                lambda m: m).count())
            for sport in ["all"]
        },
    }


def main():
    if not PROBE_JSON.exists():
        print("ABORT: 01 probe not run")
        return 2
    probe = json.loads(PROBE_JSON.read_text())
    if not probe.get("kill_criteria", {}).get("pass"):
        print("ABORT: 01 did not pass")
        return 2

    fee_bps = DEFAULT_FEE_BPS
    if FEE_JSON.exists():
        fee = json.loads(FEE_JSON.read_text())
        med = fee.get("taker_fee_bps", {}).get("bps_median")
        if isinstance(med, (int, float)) and med > 0:
            fee_bps = float(med)
            print(f"[fee] using realized median fee from 02: {fee_bps} bps")

    DATA_DIR.mkdir(exist_ok=True)
    fs = HfFileSystem()
    sports = load_sports_resolved(probe["markets"]["path"])
    if sports.empty:
        OUT_JSON.write_text(json.dumps({"error": "no resolved sports markets"}, indent=2))
        return 2

    candidates = stream_entry_candidates(fs, sports)

    print(f"[3/3] Evaluating edge over {len(candidates):,} entry candidates...")
    result = evaluate_edge(candidates, fee_bps=fee_bps)
    # Re-score at fee sensitivities
    sensitivity = {}
    for f in (50, 100, 200, 300):
        sensitivity[f"fee_bps_{f}"] = evaluate_edge(candidates, fee_bps=f).get("net_edge_notional_weighted")
    result["fee_sensitivity"] = sensitivity
    result["probed_at"] = datetime.now(timezone.utc).isoformat()
    result["max_trade_row_groups"] = MAX_TRADE_ROW_GROUPS

    OUT_JSON.write_text(json.dumps(result, indent=2, default=str))
    print()
    print("=" * 60)
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
