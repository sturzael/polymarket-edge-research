"""LlamaEnjoyer realized P&L over the last 30 days.

The v3 e12 plan calls out LlamaEnjoyer (`0x9b97...e12`) as a known sports
post-event operator. Per the user's critical-path additions: pull this
wallet's last 30 days of trades and compute realized P&L. Cross-check
against the assumption that "operators like this" extract meaningful edge
from sports settlement-lag arb.

Method:
  1. Resolve the full address from the truncated `0x9b97...e12` by streaming
     users.parquet for any address matching that prefix+suffix
  2. Pull all trades for the resolved wallet within the last 30 days
     (relative to the dataset cutoff = 2026-03-31)
  3. Compute realized P&L per market:
       - For each closed position: entry price × shares − exit/resolution × shares
       - Resolution price comes from markets.parquet outcome_prices
  4. Aggregate: total realized PnL, win rate, avg edge per trade,
     per-market breakdown

Output:
  data/09_llamaenjoyer_pnl.json
"""
from __future__ import annotations

import ast
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from huggingface_hub import HfFileSystem

DATASET = "SII-WANGZJ/Polymarket_data"
DATA_DIR = Path(__file__).parent / "data"
PROBE_JSON = DATA_DIR / "01_probe.json"
OUT_JSON = DATA_DIR / "09_llamaenjoyer_pnl.json"

ADDR_PREFIX = "0x9b97"
ADDR_SUFFIX = "e12"
LOOKBACK_DAYS = 30
DATASET_CUTOFF_TS = pd.Timestamp("2026-03-31", tz="UTC").timestamp()
WINDOW_START_TS = DATASET_CUTOFF_TS - LOOKBACK_DAYS * 86400

MAX_USER_RG_FOR_RESOLVE = 50    # search early for address discovery
MAX_USER_RG_FULL = 939          # all of users.parquet
EARLY_EXIT_AFTER_RESOLVE = True


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


def addr_hex(b) -> str:
    if isinstance(b, (bytes, bytearray)):
        return b.hex()
    return str(b)


def find_full_address(fs: HfFileSystem) -> str | None:
    """Stream users.parquet looking for any address matching prefix+suffix."""
    print(f"[1/4] Resolving 0x{ADDR_PREFIX}...{ADDR_SUFFIX} from users.parquet...")
    path = f"datasets/{DATASET}/users.parquet"
    candidates = set()
    with fs.open(path, "rb") as f:
        pf = pq.ParquetFile(f)
        cols = ["address"]
        for rg_idx in range(min(pf.metadata.num_row_groups, MAX_USER_RG_FOR_RESOLVE)):
            rg = pf.read_row_group(rg_idx, columns=cols).to_pandas()
            rg["_addr"] = rg["address"].apply(addr_hex)
            hits = rg[(rg["_addr"].str.lower().str.startswith(ADDR_PREFIX.lower())) &
                      (rg["_addr"].str.lower().str.endswith(ADDR_SUFFIX.lower()))]
            candidates.update(hits["_addr"].str.lower().tolist())
            if rg_idx % 10 == 0:
                print(f"      RG {rg_idx+1}: {len(candidates)} candidates so far")
            if EARLY_EXIT_AFTER_RESOLVE and len(candidates) >= 1:
                # keep going a few more groups to ensure we don't miss alts
                if rg_idx >= 20:
                    break
    print(f"      {len(candidates)} unique addresses match prefix+suffix")
    if not candidates:
        return None
    if len(candidates) == 1:
        return next(iter(candidates))
    # If multiple, return the one with most appearances
    return None  # signal ambiguity


def find_address_disambiguate(fs: HfFileSystem, candidates: list[str]) -> str:
    """If multiple addresses match, pick the one with the most trades."""
    print(f"[1b] Multiple matches; picking one with most volume...")
    path = f"datasets/{DATASET}/users.parquet"
    counts = {a: 0 for a in candidates}
    with fs.open(path, "rb") as f:
        pf = pq.ParquetFile(f)
        cols = ["address"]
        for rg_idx in range(min(pf.metadata.num_row_groups, 100)):
            rg = pf.read_row_group(rg_idx, columns=cols).to_pandas()
            rg["_addr"] = rg["address"].apply(addr_hex).str.lower()
            for a in candidates:
                counts[a] += int((rg["_addr"] == a).sum())
    return max(counts, key=counts.get)


def pull_wallet_trades(fs: HfFileSystem, addr: str) -> pd.DataFrame:
    """Pull all rows for `addr` in users.parquet within last 30 days."""
    print(f"[2/4] Pulling trades for 0x{addr} (last {LOOKBACK_DAYS} days)...")
    path = f"datasets/{DATASET}/users.parquet"
    chunks = []
    t0 = time.time()
    with fs.open(path, "rb") as f:
        pf = pq.ParquetFile(f)
        cols = ["timestamp", "address", "role", "direction",
                "usd_amount", "token_amount", "price", "market_id", "nonusdc_side"]
        existing = [c for c in cols if c in pf.schema_arrow.names]
        for rg_idx in range(min(pf.metadata.num_row_groups, MAX_USER_RG_FULL)):
            rg = pf.read_row_group(rg_idx, columns=existing).to_pandas()
            rg["_addr"] = rg["address"].apply(addr_hex).str.lower()
            keep = rg[rg["_addr"] == addr.lower()]
            if keep.empty:
                if rg_idx % 50 == 0:
                    print(f"      RG {rg_idx+1}: 0 hits")
                continue
            keep = keep.copy()
            ts_norm = keep["timestamp"].apply(lambda v: v/1000 if v > 1e12 else v)
            keep = keep[ts_norm >= WINDOW_START_TS]
            if len(keep) > 0:
                chunks.append(keep)
            if rg_idx % 25 == 0:
                tot = sum(len(c) for c in chunks)
                print(f"      RG {rg_idx+1}: trades_in_window={tot:,} "
                      f"(elapsed {time.time()-t0:.0f}s)")
    if not chunks:
        return pd.DataFrame()
    return pd.concat(chunks, ignore_index=True)


def compute_pnl(trades: pd.DataFrame, markets_path: str) -> dict:
    print(f"[3/4] Computing P&L on {len(trades):,} trades...")
    if trades.empty:
        return {"error": "no trades in window"}

    markets = pq.read_table(markets_path,
                            columns=["id", "slug", "outcome_prices", "closed", "end_date"]).to_pandas()
    markets["id"] = markets["id"].astype(str)
    markets["_outcomes"] = markets["outcome_prices"].apply(_parse_outcome)
    yes_payout_by_id = dict(zip(markets["id"], markets["_outcomes"].apply(
        lambda t: t[0] if t is not None else None)))
    closed_by_id = dict(zip(markets["id"], markets["closed"]))
    slug_by_id = dict(zip(markets["id"], markets["slug"]))

    trades = trades.copy()
    trades["market_id"] = trades["market_id"].astype(str)
    trades["yes_payout"] = trades["market_id"].map(yes_payout_by_id)
    trades["closed"] = trades["market_id"].map(closed_by_id)
    trades["slug"] = trades["market_id"].map(slug_by_id)

    # Per-market net position via the convention in users.parquet:
    # token_amount is signed (+ buy YES, - sell YES). Per docs: "split records,
    # each trade becomes 2 records (maker + taker)". To avoid double-counting
    # a wallet appearing as both sides (rare for a single wallet), filter to
    # role == 'taker' as the canonical view.
    if "role" in trades.columns:
        trades["_role"] = trades["role"].apply(addr_hex)
        # handle bytes / str
        is_taker = trades["_role"].str.lower() == "taker"
        canonical = trades[is_taker].copy()
        if canonical.empty:
            canonical = trades.copy()  # fallback if encoding differs
    else:
        canonical = trades.copy()

    # Realized PnL per market: payoff = 1 if YES side bought and YES wins, etc.
    # Approximation: for each market_id, compute net token_amount (shares held
    # at resolution if positive = long YES, negative = long NO equivalent).
    # Pmt at resolution = (shares × yes_payout) for shares>0, else (|shares| × (1-yes_payout))
    # Cost basis = sum(usd_amount * sign) where sign matches direction
    # Net = payout - cost_basis
    grp = canonical.groupby("market_id").agg(
        net_tokens=("token_amount", "sum"),
        net_usd_paid=("usd_amount", "sum"),
        n_trades=("market_id", "size"),
        first_ts=("timestamp", "min"),
        last_ts=("timestamp", "max"),
    ).reset_index()
    grp["yes_payout"] = grp["market_id"].map(yes_payout_by_id)
    grp["slug"] = grp["market_id"].map(slug_by_id)
    grp["closed"] = grp["market_id"].map(closed_by_id)

    # Only score markets that resolved cleanly with YES payout in {0,1}
    resolved = grp[grp["yes_payout"].isin([0.0, 1.0]) & (grp["closed"] == 1)].copy()
    # Naive payout: if net_tokens > 0 (long YES) and yes wins → net_tokens × 1
    # If net_tokens > 0 and no wins → 0
    # If net_tokens < 0 (short YES = long NO) and no wins → |net_tokens| × 1
    # If net_tokens < 0 and yes wins → 0
    def payout_row(r):
        nt = r["net_tokens"]
        yp = r["yes_payout"]
        if nt > 0:
            return nt * yp
        elif nt < 0:
            return abs(nt) * (1 - yp)
        return 0.0
    resolved["payout"] = resolved.apply(payout_row, axis=1)
    resolved["realized_pnl"] = resolved["payout"] - resolved["net_usd_paid"]

    open_pos = grp[~grp["market_id"].isin(resolved["market_id"])]

    out = {
        "lookback_days": LOOKBACK_DAYS,
        "dataset_cutoff": "2026-03-31",
        "window_start_unix": WINDOW_START_TS,
        "n_trade_records_total": int(len(trades)),
        "n_trade_records_canonical_taker": int(len(canonical)),
        "n_distinct_markets": int(grp["market_id"].nunique()),
        "n_resolved_markets": int(len(resolved)),
        "n_open_or_unresolved": int(len(open_pos)),
        "total_realized_pnl_usd": round(float(resolved["realized_pnl"].sum()), 2),
        "total_usd_invested": round(float(resolved["net_usd_paid"].sum()), 2),
        "win_rate": round(float((resolved["realized_pnl"] > 0).mean()), 3) if len(resolved) > 0 else None,
        "avg_pnl_per_market_usd": round(float(resolved["realized_pnl"].mean()), 2) if len(resolved) > 0 else None,
        "median_pnl_per_market_usd": round(float(resolved["realized_pnl"].median()), 2) if len(resolved) > 0 else None,
    }
    if len(resolved) > 0:
        # Top 10 winners and losers
        top_wins = resolved.nlargest(10, "realized_pnl")[["slug", "n_trades", "net_tokens",
                                                          "net_usd_paid", "payout", "realized_pnl"]]
        top_losses = resolved.nsmallest(10, "realized_pnl")[["slug", "n_trades", "net_tokens",
                                                            "net_usd_paid", "payout", "realized_pnl"]]
        out["top_10_winners"] = top_wins.to_dict("records")
        out["top_10_losers"] = top_losses.to_dict("records")

    return out


def main():
    if not PROBE_JSON.exists() or not json.loads(PROBE_JSON.read_text()).get("kill_criteria", {}).get("pass"):
        print("ABORT: 01 probe missing or did not pass")
        return 2
    probe = json.loads(PROBE_JSON.read_text())
    DATA_DIR.mkdir(exist_ok=True)
    fs = HfFileSystem()

    addr = find_full_address(fs)
    if not addr:
        print("ABORT: no address found matching prefix+suffix in early RGs.")
        print("       Either expand MAX_USER_RG_FOR_RESOLVE or supply the full address manually.")
        OUT_JSON.write_text(json.dumps({"error": "address not found"}, indent=2))
        return 2
    print(f"      RESOLVED: 0x{addr}")

    trades = pull_wallet_trades(fs, addr)
    if trades.empty:
        print("      WARNING: 0 trades in last 30 days for this wallet")
        result = {"resolved_address": f"0x{addr}",
                  "n_trades_in_window": 0,
                  "note": "wallet had no on-chain trades in the last 30 days of the dataset"}
    else:
        result = compute_pnl(trades, probe["markets"]["path"])
        result["resolved_address"] = f"0x{addr}"

    result["probed_at"] = datetime.now(timezone.utc).isoformat()
    OUT_JSON.write_text(json.dumps(result, indent=2, default=str))
    print()
    print("=" * 60)
    # Truncate top10 listings for stdout
    summary = {k: v for k, v in result.items() if k not in ("top_10_winners", "top_10_losers")}
    print(json.dumps(summary, indent=2, default=str))
    if "top_10_winners" in result:
        print(f"\nTop 10 winning markets:")
        for w in result["top_10_winners"]:
            print(f"  {w['slug'][:50]:50s} pnl=${w['realized_pnl']:>8.2f}")
        print(f"\nTop 10 losing markets:")
        for w in result["top_10_losers"]:
            print(f"  {w['slug'][:50]:50s} pnl=${w['realized_pnl']:>8.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
