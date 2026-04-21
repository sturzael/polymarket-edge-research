"""Stream orderfilled_part{N}.parquet, extract pre-resolution reference price
per market. Designed to run in parallel across the 4 parts.

Per-market tracking: for each condition_id, remember the last K=20 trades
whose timestamp is within [end_date - 7d, end_date]. Output per-market VWAP
over that window.

Inputs:
    data/01_markets_audit.parquet  (our market set with token1/token2/end_date)
    SII orderfilled_part{N}.parquet (streamed from HF)

Output:
    data/02_prices_part{N}.parquet  — rows: condition_id, vwap_7d, n_trades, last_ts

Usage:
    uv run python -m experiments.e16_calibration_study.02_extract_prices --part 1

Parallel:
    for n in 1 2 3 4; do
        uv run python -m experiments.e16_calibration_study.02_extract_prices --part $n &
    done; wait
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import os
# Configure HF timeouts BEFORE importing the library to take effect.
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "30")
os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "15")

import pandas as pd
import pyarrow.parquet as pq
from huggingface_hub import HfFileSystem

DATASET = "SII-WANGZJ/Polymarket_data"
DATA_DIR = Path(__file__).parent / "data"

WINDOW_SECONDS = 7 * 86400  # 7-day pre-close window


def load_market_lookup() -> tuple[dict, dict]:
    """Returns (asset_id -> condition_id) and (condition_id -> end_date_unix).

    token1 in markets.parquet is the YES token (integer string); token2 is NO.
    orderfilled uses 32-byte asset_id hex (keccak of the token). We need to
    convert tokens to the same representation.

    Observed: token1/token2 in markets.parquet are INTEGER STRINGS (uint256
    decimal), and orderfilled's {maker,taker}_asset_id is also a uint256
    but stored as bytes. We normalize both to decimal-string form.
    """
    src = DATA_DIR / "01_markets_audit.parquet"
    df = pd.read_parquet(src)
    asset_to_cond = {}
    cond_to_end = {}
    cond_to_side = {}  # (condition_id, asset_id) -> 'YES' | 'NO'
    for _, row in df.iterrows():
        cond = row["condition_id"]
        t1 = row["token1"]
        t2 = row["token2"]
        ed = row["end_date"]
        if pd.isna(ed):
            end = None
        elif isinstance(ed, pd.Timestamp):
            end = int(ed.timestamp())
        else:
            end = int(ed)
        if not t1 or not t2 or end is None:
            continue
        asset_to_cond[str(t1)] = cond
        asset_to_cond[str(t2)] = cond
        cond_to_end[cond] = end
        cond_to_side[(cond, str(t1))] = "YES"
        cond_to_side[(cond, str(t2))] = "NO"
    return asset_to_cond, cond_to_end, cond_to_side


def _hex_or_bytes_to_decstr(v) -> str:
    """orderfilled asset_id comes as FIXED_LEN_BYTE_ARRAY or hex string."""
    if v is None:
        return ""
    if isinstance(v, bytes):
        return str(int.from_bytes(v, "big"))
    s = str(v)
    if s.startswith("0x"):
        return str(int(s, 16))
    return s


def _amount_to_float(v, decimals: int = 6) -> float:
    """maker_amount / taker_amount are FIXED_LEN_BYTE_ARRAY uint256. Polymarket
    uses 6-decimal USDC on the 'collateral' side and 6-decimal CTF share units
    on the 'asset' side. We just scale by 10^6."""
    if v is None:
        return 0.0
    if isinstance(v, bytes):
        return int.from_bytes(v, "big") / (10 ** decimals)
    try:
        return float(v) / (10 ** decimals)
    except Exception:
        return 0.0


def _open_parquet(part_num: int):
    """Fresh HfFileSystem + open handle + ParquetFile. Caller keeps fs alive."""
    fs = HfFileSystem()
    path = f"datasets/{DATASET}/orderfilled_part{part_num}.parquet"
    f = fs.open(path, "rb")
    pf = pq.ParquetFile(f)
    return fs, f, pf


def stream_part(part_num: int, asset_to_cond: dict, cond_to_end: dict,
                cond_to_side: dict) -> dict:
    """Stream one orderfilled_partN.parquet. Returns per-condition trade list
    within the pre-close window. Retries on HF client-closed errors by
    reconnecting."""
    t0 = time.time()
    fs, fh, pf = _open_parquet(part_num)

    # Per-condition running list of (ts, price)
    trades: dict[str, list[tuple[int, float]]] = defaultdict(list)

    cols = ["timestamp", "maker_asset_id", "taker_asset_id",
            "maker_amount_filled", "taker_amount_filled"]

    n_rgs = pf.metadata.num_row_groups
    n_rows_total = pf.metadata.num_rows
    print(f"[part{part_num}] {n_rows_total:,} rows across {n_rgs} row-groups", flush=True)
    n_relevant = 0
    n_scanned = 0
    rg_idx = 0
    while rg_idx < n_rgs:
        try:
            batch = pf.read_row_group(rg_idx, columns=cols).to_pandas()
        except Exception as e:
            # HF httpx client can close mid-stream; reconnect and retry same rg
            print(f"[part{part_num}] rg {rg_idx} read failed: {type(e).__name__}: {e}; "
                  f"reconnecting...", flush=True)
            try:
                fh.close()
            except Exception:
                pass
            time.sleep(5)
            fs, fh, pf = _open_parquet(part_num)
            continue  # retry same rg_idx

        n_scanned += len(batch)

        # Convert asset_ids to decimal strings (vectorized)
        mak = batch["maker_asset_id"].apply(_hex_or_bytes_to_decstr)
        tak = batch["taker_asset_id"].apply(_hex_or_bytes_to_decstr)

        for ts, m, t, ma, ta in zip(batch["timestamp"], mak, tak,
                                     batch["maker_amount_filled"],
                                     batch["taker_amount_filled"]):
            cond = asset_to_cond.get(m) or asset_to_cond.get(t)
            if not cond:
                continue
            end_ts = cond_to_end.get(cond)
            if end_ts is None:
                continue
            ts_i = int(ts)
            if ts_i < end_ts - WINDOW_SECONDS or ts_i > end_ts:
                continue
            share_asset = m if m in asset_to_cond else t
            side = cond_to_side.get((cond, share_asset))
            if side is None:
                continue
            # CTFExchange convention: maker_amount_filled = amount of taker_asset
            # that flowed to the maker; taker_amount_filled = amount of maker_asset
            # that flowed to the taker.
            share_amt = _amount_to_float(ta) if share_asset == m else _amount_to_float(ma)
            coll_amt  = _amount_to_float(ma) if share_asset == m else _amount_to_float(ta)
            if share_amt <= 0 or coll_amt <= 0:
                continue
            price_yes_token = coll_amt / share_amt
            if not (0 < price_yes_token <= 1.0001):
                continue
            if side == "NO":
                price_yes_token = 1.0 - price_yes_token
            trades[cond].append((ts_i, price_yes_token))
            n_relevant += 1

        rg_idx += 1
        if rg_idx % 20 == 0 or rg_idx == n_rgs:
            elapsed = time.time() - t0
            pct = 100 * rg_idx / n_rgs
            print(f"[part{part_num}] rg {rg_idx}/{n_rgs} ({pct:.0f}%) "
                  f"scanned={n_scanned:,} relevant={n_relevant:,} "
                  f"markets={len(trades):,} elapsed={elapsed:.0f}s",
                  flush=True)
    try:
        fh.close()
    except Exception:
        pass
    return trades


def aggregate(trades: dict) -> pd.DataFrame:
    rows = []
    for cond, tlist in trades.items():
        if not tlist:
            continue
        tlist.sort()
        ts_arr = [t for t, _ in tlist]
        p_arr = [p for _, p in tlist]
        # VWAP (uniform weights since we already dropped size; use mean)
        vwap = sum(p_arr) / len(p_arr)
        rows.append({
            "condition_id": cond,
            "vwap_7d": round(vwap, 5),
            "n_trades": len(tlist),
            "last_ts": max(ts_arr),
            "last_price": round(p_arr[-1], 5),
        })
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", type=int, required=True, choices=[1, 2, 3, 4])
    args = ap.parse_args()

    print(f"loading market lookup...", flush=True)
    asset_to_cond, cond_to_end, cond_to_side = load_market_lookup()
    print(f"  {len(asset_to_cond):,} asset_ids across {len(cond_to_end):,} markets",
          flush=True)

    trades = stream_part(args.part, asset_to_cond, cond_to_end, cond_to_side)
    df = aggregate(trades)
    out = DATA_DIR / f"02_prices_part{args.part}.parquet"
    df.to_parquet(out, index=False)
    print(f"[part{args.part}] wrote {out}  ({len(df):,} markets with in-window trades)",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
