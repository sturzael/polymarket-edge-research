"""SII fee-realization probe.

Goal: answer H3 (fee gate) by computing the actual fee_bps that takers
paid on sports markets in the post-resolution window.

Schema realities (confirmed by 01):
  markets.parquet: id, slug, condition_id, token1, token2, end_date
  trades.parquet: timestamp, market_id, price, usd_amount, token_amount,
                  maker_direction, taker_direction, transaction_hash, log_index
  orderfilled_part{1..4}.parquet: transaction_hash, log_index, taker_fee,
                                  maker_fee, protocol_fee (uint256 BE bytes)

Method:
  1. markets → sports market_ids (slug match)
  2. Stream trades.parquet row groups → keep rows where:
        market_id ∈ sports
        AND price >= 0.95
        AND timestamp within ±30min of corresponding market end_date
        (proxy for "post-resolution window")
     Collect (tx_hash, log_index) keys plus price for fee_bps calc.
  3. Stream orderfilled_part{1..4}.parquet row groups → join on
     (tx_hash, log_index), pull taker_fee, decode uint256 → USDC.
  4. fee_bps = (taker_fee_usdc / (token_amount * min(price, 1-price))) * 10000

Storage: nothing persisted beyond aggregates + final JSON.

Sample target: SAMPLE_TARGET keys; stop early when reached.

NOTE: takes ~10-30 min depending on sample target and HF latency. The
trade row groups are ~50-100MB each; the script uses pyarrow byte-range
reads via HfFileSystem, so only matched rows enter memory.
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
OUT_JSON = DATA_DIR / "02_fee_realization.json"
PROBE_JSON = DATA_DIR / "01_probe.json"

SPORTS_SLUG_PATTERNS = (
    "atp-", "wta-", "nba-", "nfl-", "nhl-", "mlb-",
    "cricipl-", "ufc-", "mls-", "wnba-",
)
PRICE_LO = 0.95
RESOLUTION_WINDOW_MIN = 30
SAMPLE_TARGET_KEYS = 5_000        # taker fills to find
MAX_TRADE_ROW_GROUPS = 60         # ~3-6GB of trades scanned
MAX_OF_ROW_GROUPS_PER_PART = 80   # ~4-8GB of orderfilled per part

USDC_DECIMALS = 6
USDC_SCALE = 10 ** USDC_DECIMALS
SHARE_DECIMALS = 6  # outcome share decimals on Polymarket
SHARE_SCALE = 10 ** SHARE_DECIMALS


def decode_uint256(b) -> int:
    if b is None:
        return 0
    if isinstance(b, (bytes, bytearray)):
        if len(b) == 0 or all(byte == 0 for byte in b):
            return 0
        return int.from_bytes(b, "big")
    try:
        return int(b)
    except Exception:
        return 0


def load_sports_markets(markets_path: str) -> pd.DataFrame:
    print(f"[1/4] Loading markets.parquet → sports filter...")
    t = time.time()
    df = pq.read_table(markets_path,
                       columns=["id", "slug", "condition_id",
                                "token1", "token2", "end_date", "closed"]).to_pandas()
    df["slug"] = df["slug"].astype(str).str.lower()
    sports = df[df["slug"].apply(lambda s: any(p in s for p in SPORTS_SLUG_PATTERNS))].copy()
    sports["end_date_ts"] = (sports["end_date"] - pd.Timestamp("1970-01-01", tz="UTC")).dt.total_seconds()
    print(f"      {len(sports):,} sports markets ({time.time()-t:.1f}s)")
    return sports


def stream_sports_trades(fs: HfFileSystem, sports: pd.DataFrame) -> pd.DataFrame:
    """Stream trades.parquet, keep sports + post-resolution window."""
    print(f"[2/4] Streaming trades.parquet (target {SAMPLE_TARGET_KEYS:,} keys, "
          f"max {MAX_TRADE_ROW_GROUPS} row groups)...")
    sports_ids = set(sports["id"].astype(str))
    end_by_id = dict(zip(sports["id"].astype(str), sports["end_date_ts"]))

    path = f"datasets/{DATASET}/trades.parquet"
    matched = []
    keys_collected = 0
    t0 = time.time()

    with fs.open(path, "rb") as f:
        pf = pq.ParquetFile(f)
        cols = ["timestamp", "transaction_hash", "log_index", "market_id",
                "price", "usd_amount", "token_amount",
                "maker_direction", "taker_direction"]
        existing = [c for c in cols if c in pf.schema_arrow.names]
        for rg_idx in range(min(pf.metadata.num_row_groups, MAX_TRADE_ROW_GROUPS)):
            rg = pf.read_row_group(rg_idx, columns=existing).to_pandas()
            rg["market_id"] = rg["market_id"].astype(str)
            keep = rg[rg["market_id"].isin(sports_ids)]
            if "price" in keep.columns:
                keep = keep[keep["price"] >= PRICE_LO]
            # Post-resolution window filter
            if "timestamp" in keep.columns and len(keep) > 0:
                keep = keep.copy()
                keep["_end_ts"] = keep["market_id"].map(end_by_id)
                ts_norm = keep["timestamp"].apply(lambda v: v/1000 if v > 1e12 else v)
                delta_min = (ts_norm - keep["_end_ts"]).abs() / 60
                keep = keep[delta_min <= RESOLUTION_WINDOW_MIN]
            if len(keep) > 0:
                matched.append(keep)
            keys_collected = sum(len(m) for m in matched)
            if rg_idx % 5 == 0 or keys_collected >= SAMPLE_TARGET_KEYS:
                rate = (rg_idx+1) / max(time.time()-t0, 0.1)
                print(f"      RG {rg_idx+1}/{min(pf.metadata.num_row_groups, MAX_TRADE_ROW_GROUPS)}: "
                      f"keys={keys_collected:,} ({rate:.1f} RG/s)")
            if keys_collected >= SAMPLE_TARGET_KEYS:
                break

    if not matched:
        return pd.DataFrame()
    out = pd.concat(matched, ignore_index=True)
    print(f"      collected {len(out):,} sports post-resolution trades")
    return out


def stream_orderfilled_for_keys(fs: HfFileSystem, keys: set[tuple]) -> pd.DataFrame:
    """Stream orderfilled_part{1..4}, return rows whose (tx_hash, log_index) is in keys."""
    print(f"[3/4] Streaming orderfilled parts to join {len(keys):,} keys...")
    target_hashes = {k[0] for k in keys}  # quick filter on tx hash
    matched = []
    t0 = time.time()

    for part_idx in range(1, 5):
        path = f"datasets/{DATASET}/orderfilled_part{part_idx}.parquet"
        keys_remaining = len(keys) - sum(len(m) for m in matched)
        if keys_remaining <= 0:
            break
        print(f"      part{part_idx} ({keys_remaining:,} keys still to find)...")
        with fs.open(path, "rb") as f:
            pf = pq.ParquetFile(f)
            cols = ["transaction_hash", "log_index", "taker", "maker",
                    "maker_fee", "taker_fee", "protocol_fee",
                    "maker_amount_filled", "taker_amount_filled",
                    "maker_asset_id", "taker_asset_id"]
            existing = [c for c in cols if c in pf.schema_arrow.names]
            for rg_idx in range(min(pf.metadata.num_row_groups, MAX_OF_ROW_GROUPS_PER_PART)):
                rg = pf.read_row_group(rg_idx, columns=existing).to_pandas()
                # Normalize tx_hash to bytes-as-hex string for comparison
                if "transaction_hash" in rg.columns:
                    rg["_th"] = rg["transaction_hash"].apply(
                        lambda b: b.hex() if isinstance(b, (bytes, bytearray)) else str(b))
                else:
                    continue
                hits = rg[rg["_th"].isin(target_hashes)]
                if len(hits) > 0:
                    # Tighten by (tx_hash, log_index)
                    hits = hits.assign(_key=list(zip(hits["_th"], hits["log_index"])))
                    hits = hits[hits["_key"].isin(keys)]
                if len(hits) > 0:
                    matched.append(hits)
                if rg_idx % 10 == 0:
                    found = sum(len(m) for m in matched)
                    elapsed = time.time() - t0
                    print(f"        RG {rg_idx+1}: found={found:,} elapsed={elapsed:.0f}s")
                if sum(len(m) for m in matched) >= len(keys):
                    break
    if not matched:
        return pd.DataFrame()
    return pd.concat(matched, ignore_index=True)


def compute_fee_bps(trades: pd.DataFrame, fills: pd.DataFrame) -> dict:
    print(f"[4/4] Joining {len(trades):,} trades with {len(fills):,} on-chain fills...")
    if fills.empty:
        return {"error": "no fills found"}

    # Trades has price + token_amount + tx_hash + log_index
    trades = trades.copy()
    trades["_th"] = trades["transaction_hash"].apply(
        lambda b: b.hex() if isinstance(b, (bytes, bytearray)) else str(b))
    trades["_key"] = list(zip(trades["_th"], trades["log_index"]))

    if "_key" not in fills.columns:
        return {"error": "fills missing _key"}

    # Drop dupes per key (one trade may map to one fill)
    trades_u = trades.drop_duplicates("_key")
    fills_u = fills.drop_duplicates("_key")
    j = trades_u.merge(fills_u[["_key", "taker_fee", "maker_fee", "protocol_fee",
                                "taker_amount_filled", "maker_amount_filled"]],
                       on="_key", how="inner")
    if j.empty:
        return {"error": "join produced 0 rows"}

    # Decode fees
    j["taker_fee_usdc"] = j["taker_fee"].apply(decode_uint256) / USDC_SCALE
    j["maker_fee_usdc"] = j["maker_fee"].apply(decode_uint256) / USDC_SCALE
    j["protocol_fee_usdc"] = j["protocol_fee"].apply(decode_uint256) / USDC_SCALE

    # Notional in USDC = price × token_amount (token_amount is shares)
    j["notional_usdc"] = j["price"] * j["token_amount"]
    j = j[j["notional_usdc"] > 0]
    j = j[j["price"].between(0.005, 0.995)]
    if j.empty:
        return {"error": "no rows after sanity filter"}

    # Polymarket fee formula: charged on min(price, 1-price) * shares
    j["denom"] = j["token_amount"] * np.minimum(j["price"], 1 - j["price"])
    j["taker_fee_bps"] = (j["taker_fee_usdc"] / j["denom"].replace(0, np.nan)) * 10_000
    j["maker_fee_bps"] = (j["maker_fee_usdc"] / j["denom"].replace(0, np.nan)) * 10_000
    j = j.dropna(subset=["taker_fee_bps"])

    out = {"n_joined": int(len(j))}

    def stats(s, key):
        s = s.dropna()
        if len(s) == 0:
            return {}
        return {
            f"{key}_median": round(float(s.median()), 2),
            f"{key}_mean": round(float(s.mean()), 2),
            f"{key}_p25": round(float(s.quantile(0.25)), 2),
            f"{key}_p75": round(float(s.quantile(0.75)), 2),
            f"{key}_p95": round(float(s.quantile(0.95)), 2),
            f"{key}_frac_zero": round(float((s == 0).mean()), 3),
        }

    out["taker_fee_bps"] = stats(j["taker_fee_bps"], "bps")
    out["maker_fee_bps"] = stats(j["maker_fee_bps"], "bps")

    bands = [(0.95, 0.96), (0.96, 0.97), (0.97, 0.98), (0.98, 0.99)]
    band_stats = {}
    for lo, hi in bands:
        sl = j[j["price"].between(lo, hi)]
        if len(sl) > 0:
            band_stats[f"{lo:.2f}-{hi:.2f}"] = {
                "n": int(len(sl)),
                "taker_bps_median": round(float(sl["taker_fee_bps"].median()), 2),
                "taker_bps_p95": round(float(sl["taker_fee_bps"].quantile(0.95)), 2),
            }
    out["by_price_band"] = band_stats
    return out


def main():
    if not PROBE_JSON.exists():
        print(f"ABORT: {PROBE_JSON} missing — run 01 first")
        return 2
    probe = json.loads(PROBE_JSON.read_text())
    if not probe.get("kill_criteria", {}).get("pass"):
        print("ABORT: 01 probe did not pass — fee work is moot")
        return 2

    DATA_DIR.mkdir(exist_ok=True)
    fs = HfFileSystem()

    sports = load_sports_markets(probe["markets"]["path"])
    if sports.empty:
        OUT_JSON.write_text(json.dumps({"error": "no sports markets"}, indent=2))
        return 2

    trades = stream_sports_trades(fs, sports)
    if trades.empty:
        result = {"error": "no sports post-resolution trades found in scanned RGs",
                  "max_trade_row_groups": MAX_TRADE_ROW_GROUPS}
    else:
        # Build keys for join
        trades = trades.copy()
        trades["_th"] = trades["transaction_hash"].apply(
            lambda b: b.hex() if isinstance(b, (bytes, bytearray)) else str(b))
        keys = set(zip(trades["_th"], trades["log_index"]))
        fills = stream_orderfilled_for_keys(fs, keys)
        result = compute_fee_bps(trades, fills)

    result["probed_at"] = datetime.now(timezone.utc).isoformat()
    OUT_JSON.write_text(json.dumps(result, indent=2, default=str))
    print()
    print("=" * 60)
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
