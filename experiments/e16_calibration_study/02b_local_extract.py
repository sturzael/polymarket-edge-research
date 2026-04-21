"""Download-then-process alternative to 02_extract_prices.

Sequentially downloads each orderfilled_part{N}.parquet to a local cache,
reads it locally (no network), writes the per-market VWAP parquet, deletes
the cache file, next part.

Avoids the HF streaming flakiness. Single-threaded but reliable.

Usage:
    uv run python -m experiments.e16_calibration_study.02b_local_extract
    uv run python -m experiments.e16_calibration_study.02b_local_extract --parts 2 3 4
    uv run python -m experiments.e16_calibration_study.02b_local_extract --keep-cache
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
from huggingface_hub import hf_hub_download

DATASET = "SII-WANGZJ/Polymarket_data"
DATA_DIR = Path(__file__).parent / "data"
CACHE_DIR = DATA_DIR / "orderfilled_cache"
WINDOW_SECONDS = 7 * 86400


def _hex_or_bytes_to_decstr(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bytes):
        return str(int.from_bytes(v, "big"))
    s = str(v)
    if s.startswith("0x"):
        return str(int(s, 16))
    return s


def _amount_to_float(v, decimals: int = 6) -> float:
    if v is None:
        return 0.0
    if isinstance(v, bytes):
        return int.from_bytes(v, "big") / (10 ** decimals)
    try:
        return float(v) / (10 ** decimals)
    except Exception:
        return 0.0


def load_market_lookup() -> tuple[dict, dict, dict]:
    src = DATA_DIR / "01_markets_audit.parquet"
    df = pd.read_parquet(src)
    asset_to_cond = {}
    cond_to_end = {}
    cond_to_side = {}
    for _, row in df.iterrows():
        cond = row["condition_id"]
        t1 = row["token1"]
        t2 = row["token2"]
        ed = row["end_date"]
        if pd.isna(ed):
            continue
        if isinstance(ed, pd.Timestamp):
            end = int(ed.timestamp())
        else:
            end = int(ed)
        if not t1 or not t2:
            continue
        asset_to_cond[str(t1)] = cond
        asset_to_cond[str(t2)] = cond
        cond_to_end[cond] = end
        cond_to_side[(cond, str(t1))] = "YES"
        cond_to_side[(cond, str(t2))] = "NO"
    return asset_to_cond, cond_to_end, cond_to_side


def process_part(part_num: int, asset_to_cond: dict, cond_to_end: dict,
                 cond_to_side: dict, keep_cache: bool = False) -> Path:
    """Downloads part if missing, reads locally, writes per-market VWAP parquet."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"orderfilled_part{part_num}.parquet"
    print(f"[part{part_num}] downloading (or using cache)...", flush=True)
    t_dl = time.time()
    local_path = hf_hub_download(
        repo_id=DATASET, filename=filename, repo_type="dataset",
        cache_dir=str(CACHE_DIR),
    )
    print(f"[part{part_num}] downloaded to {local_path} "
          f"in {time.time()-t_dl:.0f}s", flush=True)

    t0 = time.time()
    pf = pq.ParquetFile(local_path)
    n_rgs = pf.metadata.num_row_groups
    n_rows_total = pf.metadata.num_rows
    print(f"[part{part_num}] {n_rows_total:,} rows, {n_rgs} row-groups", flush=True)

    trades: dict[str, list[tuple[int, float]]] = defaultdict(list)
    cols = ["timestamp", "maker_asset_id", "taker_asset_id",
            "maker_amount_filled", "taker_amount_filled"]
    n_relevant = 0
    n_scanned = 0

    for rg_idx in range(n_rgs):
        batch = pf.read_row_group(rg_idx, columns=cols).to_pandas()
        n_scanned += len(batch)

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

        if (rg_idx + 1) % 20 == 0 or rg_idx + 1 == n_rgs:
            elapsed = time.time() - t0
            pct = 100 * (rg_idx + 1) / n_rgs
            print(f"[part{part_num}] rg {rg_idx+1}/{n_rgs} ({pct:.0f}%) "
                  f"scanned={n_scanned:,} relevant={n_relevant:,} "
                  f"markets={len(trades):,} elapsed={elapsed:.0f}s",
                  flush=True)

    rows = []
    for cond, tlist in trades.items():
        if not tlist:
            continue
        tlist.sort()
        prices = [p for _, p in tlist]
        ts_arr = [t for t, _ in tlist]
        vwap = sum(prices) / len(prices)
        rows.append({
            "condition_id": cond,
            "vwap_7d": round(vwap, 5),
            "n_trades": len(tlist),
            "last_ts": max(ts_arr),
            "last_price": round(prices[-1], 5),
        })
    out = DATA_DIR / f"02_prices_part{part_num}.parquet"
    pd.DataFrame(rows).to_parquet(out, index=False)
    print(f"[part{part_num}] wrote {out} ({len(rows):,} markets)", flush=True)

    if not keep_cache:
        try:
            os.remove(local_path)
            print(f"[part{part_num}] deleted cache {local_path}", flush=True)
        except Exception as e:
            print(f"[part{part_num}] could not delete cache: {e}", flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parts", nargs="*", type=int, default=[1, 2, 3, 4])
    ap.add_argument("--keep-cache", action="store_true")
    args = ap.parse_args()

    print(f"loading market lookup...", flush=True)
    a2c, c2e, c2s = load_market_lookup()
    print(f"  {len(a2c):,} asset_ids across {len(c2e):,} markets", flush=True)

    for n in args.parts:
        try:
            process_part(n, a2c, c2e, c2s, keep_cache=args.keep_cache)
        except Exception as e:
            print(f"[part{n}] FAILED: {type(e).__name__}: {e}", flush=True)
            raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
