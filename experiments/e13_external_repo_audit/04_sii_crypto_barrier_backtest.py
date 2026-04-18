"""Crypto-barrier residual arb backtest (historical replay).

Replays the e9 crypto-barrier entry rule against SII history. Same shape
as 03 but slug filter is crypto-barrier and we additionally measure
"crash rate" — how often the spot crossed the barrier post-entry, turning
a 0.97-entry into a 0.00-loss.

Limitation noted in plan: we don't have external BTC/ETH spot bars locally,
so we INFER crash by checking if the resolved outcome is the LOSING side
relative to the entry. This conflates "crash" with "we entered the wrong
side" but is a useful proxy: any time we bought the winning side at >= 0.95
and the market resolved AGAINST us, that's a binary "crash" event.

Output:
  data/04_crypto_barrier_backtest.json — entries, hit rate, crash rate, edge
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
OUT_JSON = DATA_DIR / "04_crypto_barrier_backtest.json"

CRYPTO_BARRIER_REQ_ANY = ("-reach-", "-dip-to-", "-hit-", "-above-", "-below-")
CRYPTO_BARRIER_REQ_ANY2 = ("bitcoin", "ethereum", "solana", "btc", "eth", "sol",
                           "xrp", "doge", "bnb")
PRICE_LO = 0.95
PRICE_HI_CAP = 0.98
ENTRY_WINDOW_HOURS = 2          # within 2h of resolution per e12 plan
MAX_TRADE_ROW_GROUPS = 80
DEFAULT_FEE_BPS = 100
SAMPLE_TARGET_TRADES = 5_000


def is_crypto_barrier(slug: str) -> bool:
    s = slug.lower()
    return (any(k in s for k in CRYPTO_BARRIER_REQ_ANY) and
            any(k in s for k in CRYPTO_BARRIER_REQ_ANY2))


def load_resolved_barriers(markets_path: str) -> pd.DataFrame:
    print("[1/3] Loading markets.parquet → resolved crypto-barrier markets...")
    df = pq.read_table(markets_path).to_pandas()
    df["slug"] = df["slug"].astype(str).str.lower()
    barr = df[df["slug"].apply(is_crypto_barrier)].copy()
    if "closed" in barr.columns:
        barr = barr[barr["closed"] == 1]
    barr["_outcomes"] = barr["outcome_prices"].apply(_parse_outcome)
    barr = barr[barr["_outcomes"].notna()]
    barr["yes_payout"] = barr["_outcomes"].apply(lambda t: t[0])
    barr = barr[barr["yes_payout"].isin([0.0, 1.0])]
    barr["end_date_ts"] = (barr["end_date"] - pd.Timestamp("1970-01-01", tz="UTC")).dt.total_seconds()
    print(f"      {len(barr):,} resolved crypto-barrier markets with clean outcomes")
    return barr


def _parse_outcome(v):
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


def stream_entry_candidates(fs: HfFileSystem, barr: pd.DataFrame) -> pd.DataFrame:
    print("[2/3] Streaming trades.parquet → barrier entry candidates...")
    barr_ids = set(barr["id"].astype(str))
    end_by_id = dict(zip(barr["id"].astype(str), barr["end_date_ts"]))
    yes_payout_by_id = dict(zip(barr["id"].astype(str), barr["yes_payout"]))

    path = f"datasets/{DATASET}/trades.parquet"
    keep_chunks = []
    t0 = time.time()
    with fs.open(path, "rb") as f:
        pf = pq.ParquetFile(f)
        cols = ["timestamp", "market_id", "price", "usd_amount", "token_amount"]
        existing = [c for c in cols if c in pf.schema_arrow.names]
        for rg_idx in range(min(pf.metadata.num_row_groups, MAX_TRADE_ROW_GROUPS)):
            rg = pf.read_row_group(rg_idx, columns=existing).to_pandas()
            rg["market_id"] = rg["market_id"].astype(str)
            keep = rg[rg["market_id"].isin(barr_ids)]
            if keep.empty:
                continue
            keep = keep.copy()
            keep["_end_ts"] = keep["market_id"].map(end_by_id)
            ts_norm = keep["timestamp"].apply(lambda v: v/1000 if v > 1e12 else v)
            keep["_hours_to_end"] = (keep["_end_ts"] - ts_norm) / 3600
            # Within ENTRY_WINDOW_HOURS of the END (pre-resolution), and price in band
            keep = keep[keep["_hours_to_end"].between(0, ENTRY_WINDOW_HOURS)]
            keep["_yes_payout"] = keep["market_id"].map(yes_payout_by_id)
            # Buy side that was trading high
            yes_strong = keep[(keep["price"] >= PRICE_LO) & (keep["price"] <= PRICE_HI_CAP)]
            yes_strong = yes_strong.assign(_buy_side="YES",
                                           _entry_price=yes_strong["price"],
                                           _winning=yes_strong["_yes_payout"] == 1.0)
            no_strong = keep[(keep["price"] <= 1 - PRICE_LO) & (keep["price"] >= 1 - PRICE_HI_CAP)]
            no_strong = no_strong.assign(_buy_side="NO",
                                         _entry_price=1 - no_strong["price"],
                                         _winning=no_strong["_yes_payout"] == 0.0)
            ck = pd.concat([yes_strong, no_strong], ignore_index=True)
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


def evaluate(candidates: pd.DataFrame, fee_bps: float) -> dict:
    if candidates.empty:
        return {"error": "no candidates"}
    candidates = candidates.copy()
    candidates["payout_per_share"] = np.where(candidates["_winning"], 1.0, 0.0)
    candidates["gross_pnl_per_share"] = candidates["payout_per_share"] - candidates["_entry_price"]
    candidates["fee_per_share"] = (fee_bps / 10_000) * np.minimum(
        candidates["_entry_price"], 1 - candidates["_entry_price"])
    candidates["net_pnl_per_share"] = candidates["gross_pnl_per_share"] - candidates["fee_per_share"]
    candidates["notional"] = candidates["usd_amount"]
    total_notional = float(candidates["notional"].sum())

    n = len(candidates)
    n_wins = int(candidates["_winning"].sum())
    n_crash = n - n_wins  # bought near 0.97, resolved 0.00 → crash event

    weighted_gross = float((candidates["gross_pnl_per_share"] * candidates["notional"]).sum() / max(total_notional, 1e-9))
    weighted_net = float((candidates["net_pnl_per_share"] * candidates["notional"]).sum() / max(total_notional, 1e-9))

    return {
        "n_entries": n,
        "fee_bps_assumed": fee_bps,
        "hit_rate": round(n_wins / n, 4),
        "crash_count": n_crash,
        "crash_rate": round(n_crash / n, 4),
        "gross_edge_avg": round(float(candidates["gross_pnl_per_share"].mean()), 4),
        "gross_edge_notional_weighted": round(weighted_gross, 4),
        "net_edge_avg": round(float(candidates["net_pnl_per_share"].mean()), 4),
        "net_edge_notional_weighted": round(weighted_net, 4),
        "total_notional_usd": round(total_notional, 2),
        "median_hours_to_end": round(float(candidates["_hours_to_end"].median()), 3),
    }


def main():
    if not PROBE_JSON.exists() or not json.loads(PROBE_JSON.read_text()).get("kill_criteria", {}).get("pass"):
        print("ABORT: 01 probe missing or did not pass")
        return 2
    probe = json.loads(PROBE_JSON.read_text())

    fee_bps = DEFAULT_FEE_BPS
    if FEE_JSON.exists():
        fee = json.loads(FEE_JSON.read_text())
        med = fee.get("taker_fee_bps", {}).get("bps_median")
        if isinstance(med, (int, float)) and med > 0:
            fee_bps = float(med)
            print(f"[fee] using realized median fee from 02: {fee_bps} bps")

    DATA_DIR.mkdir(exist_ok=True)
    fs = HfFileSystem()
    barr = load_resolved_barriers(probe["markets"]["path"])
    if barr.empty:
        OUT_JSON.write_text(json.dumps({"error": "no resolved crypto-barrier markets"}, indent=2))
        return 2

    candidates = stream_entry_candidates(fs, barr)
    print(f"[3/3] Evaluating crypto-barrier edge over {len(candidates):,} candidates...")
    result = evaluate(candidates, fee_bps=fee_bps)
    sensitivity = {}
    for f in (50, 100, 200, 300):
        sensitivity[f"fee_bps_{f}"] = evaluate(candidates, fee_bps=f).get("net_edge_notional_weighted")
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
