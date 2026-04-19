"""Q2 retrospective: how long do neg-risk arb windows actually last?

For each sampled resolved neg-risk event:
  1. Pull all child markets' trades from SII quant.parquet
  2. Time-bucket trades into 1-min windows; carry-forward latest trade price
     per child market (treat as "implied mid" at that minute)
  3. For each minute where ALL active markets have a trade-derived price,
     compute sum_yes_implied
  4. Detect "arb windows" — runs of consecutive minutes where sum < 1.00
  5. Measure: window duration, min sum (= max edge), edge decay shape,
     proxy depth (sum of trade volume during window)

Reports:
  - Window duration distribution (n, median, p25, p75, p95)
  - Edge magnitude distribution
  - Edge decay shape: bucket windows by start-edge, plot end-edge vs duration
  - Volume-during-window distribution (proxy for capturable depth)

Caveats:
  - Trade prices ≠ ask prices. This UNDERSTATES edge (a market with sum=0.95 in
    trades had asks slightly higher; real arb might have been smaller).
  - Forward-filling is a proxy — gaps in trades don't mean book was empty.
    Limit to "all markets had a trade in the last 10 min" to avoid stale data.
  - Trades happen sporadically — we can only measure window resolution at
    the granularity of trade timestamps. Sub-minute windows under-counted.

Sample default: 30 events stratified across categories.
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from huggingface_hub import HfFileSystem

DATASET = "SII-WANGZJ/Polymarket_data"
HERE = Path(__file__).parent
DATA_DIR = HERE / "data"
OUT_JSON = DATA_DIR / "q2_persistence.json"

# We need the markets parquet from e13's cache to avoid re-downloading
E13_PROBE = HERE / "../e13_external_repo_audit/data/01_probe.json"


def parse_outcome_prices(raw):
    if raw is None: return None
    if isinstance(raw, list) and len(raw) == 2:
        try: return (float(raw[0]), float(raw[1]))
        except: return None
    if isinstance(raw, str):
        try:
            v = ast.literal_eval(raw)
            if isinstance(v, list) and len(v) == 2:
                return (float(v[0]), float(v[1]))
        except: pass
    return None


def load_events(markets_path: str, max_events: int):
    """Identify resolved neg-risk events from markets.parquet (group by event_id)."""
    print(f"[load_events] reading markets.parquet...")
    df = pq.read_table(markets_path).to_pandas()
    df["slug"] = df["slug"].astype(str)
    # neg_risk + closed
    closed_neg_risk = df[(df["closed"] == 1) & (df["neg_risk"] == 1)].copy()
    print(f"  {len(closed_neg_risk):,} closed neg-risk markets")
    # Group by event_id
    closed_neg_risk["_outcomes"] = closed_neg_risk["outcome_prices"].apply(parse_outcome_prices)
    closed_neg_risk["yes_payout"] = closed_neg_risk["_outcomes"].apply(lambda t: t[0] if t else None)
    grouped = closed_neg_risk.groupby("event_id").agg(
        n_markets=("id", "count"),
        market_ids=("id", lambda s: list(s.astype(str))),
        slugs=("slug", lambda s: list(s)),
        yes_winners=("yes_payout", lambda s: int((s == 1.0).sum())),
        end_dates=("end_date", lambda s: list(s)),
        event_slug=("event_slug", "first"),
    ).reset_index()
    # Want events where exactly one market resolved YES (clean resolution)
    eligible = grouped[(grouped["n_markets"] >= 2) & (grouped["yes_winners"] == 1)]
    print(f"  {len(eligible):,} eligible events (>=2 markets, exactly one YES winner)")
    if max_events and len(eligible) > max_events:
        eligible = eligible.sample(n=max_events, random_state=42)
        print(f"  sampled {len(eligible)} events")
    return eligible.to_dict("records")


def stream_trades_for_markets(market_id_set: set, max_row_groups: int):
    """Stream quant.parquet, keep only rows whose market_id ∈ set.
    Returns dict[market_id] → DataFrame[ts, price]."""
    fs = HfFileSystem()
    path = f"datasets/{DATASET}/quant.parquet"
    out = defaultdict(list)
    t0 = time.time()
    print(f"[stream_trades] target {len(market_id_set):,} market_ids; max RG={max_row_groups}")
    with fs.open(path, "rb") as f:
        pfile = pq.ParquetFile(f)
        cols = ["timestamp", "market_id", "price", "usd_amount"]
        existing = [c for c in cols if c in pfile.schema_arrow.names]
        for rg_idx in range(min(pfile.metadata.num_row_groups, max_row_groups)):
            rg = pfile.read_row_group(rg_idx, columns=existing).to_pandas()
            rg["market_id"] = rg["market_id"].astype(str)
            keep = rg[rg["market_id"].isin(market_id_set)]
            if len(keep) > 0:
                for mid, sub in keep.groupby("market_id"):
                    out[mid].append(sub[["timestamp", "price", "usd_amount"]])
            if rg_idx % 20 == 0:
                total_kept = sum(len(p) for parts in out.values() for p in parts)
                print(f"  RG {rg_idx+1}/{pfile.metadata.num_row_groups}: kept={total_kept:,} "
                      f"markets_seen={len(out)} ({time.time()-t0:.0f}s)")
    final = {}
    for mid, parts in out.items():
        df = pd.concat(parts, ignore_index=True).sort_values("timestamp")
        # Convert ts → seconds if in ms
        df["ts"] = df["timestamp"].apply(lambda v: v / 1000 if v > 1e12 else v)
        final[mid] = df
    print(f"  collected trades for {len(final)}/{len(market_id_set)} markets")
    return final


def find_arb_windows(event: dict, trades: dict, stale_tol_min: int = 10) -> list[dict]:
    """For one event, time-bucket trades and find arb windows."""
    market_ids = list(event["market_ids"])
    market_trades = {mid: trades.get(mid) for mid in market_ids if mid in trades}
    if len(market_trades) < 2:
        return []
    # Build a unified timestamp set (1-min buckets across union of all trades)
    all_ts = sorted({int(ts // 60 * 60) for df in market_trades.values() for ts in df["ts"].values})
    if len(all_ts) < 5:
        return []
    # For each market, build a (sorted) list of (bucket, price) so we can carry-forward
    market_series = {}
    for mid, df in market_trades.items():
        df = df.copy()
        df["bucket"] = (df["ts"] // 60 * 60).astype(int)
        # Last trade price per bucket
        s = df.groupby("bucket")["price"].last().sort_index()
        market_series[mid] = s
    # For each bucket, compute the latest known price per market within stale_tol_min
    sums = []
    for bucket in all_ts:
        prices = []
        all_fresh = True
        for mid, s in market_series.items():
            # Find most-recent bucket ≤ this bucket
            idx = s.index.searchsorted(bucket, side="right") - 1
            if idx < 0:
                all_fresh = False; break
            last_bucket = s.index[idx]
            age_min = (bucket - last_bucket) / 60
            if age_min > stale_tol_min:
                all_fresh = False; break
            prices.append(float(s.iloc[idx]))
        if not all_fresh or len(prices) < len(market_series):
            sums.append(None)
            continue
        sums.append(sum(prices))
    # Find runs where sum < 1
    windows = []
    i = 0
    while i < len(sums):
        if sums[i] is None or sums[i] >= 1.0:
            i += 1; continue
        # Start of an arb window
        start_idx = i
        min_sum = sums[i]
        while i < len(sums) and sums[i] is not None and sums[i] < 1.0:
            min_sum = min(min_sum, sums[i])
            i += 1
        end_idx = i  # exclusive
        duration_min = (all_ts[end_idx-1] - all_ts[start_idx]) / 60 + 1  # +1 for inclusive count
        windows.append({
            "start_ts": all_ts[start_idx],
            "end_ts": all_ts[end_idx-1],
            "duration_min": duration_min,
            "start_sum": sums[start_idx],
            "end_sum": sums[end_idx-1],
            "min_sum": min_sum,
            "max_edge_pct": (1 - min_sum) * 100,
        })
    return windows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-events", type=int, default=30,
                    help="how many resolved events to sample")
    ap.add_argument("--max-row-groups", type=int, default=120,
                    help="max quant.parquet row groups to scan (each ~1M rows)")
    args = ap.parse_args()

    DATA_DIR.mkdir(exist_ok=True)
    if not E13_PROBE.exists():
        print(f"ABORT: e13 probe missing at {E13_PROBE}")
        return 2
    probe = json.loads(E13_PROBE.read_text())
    markets_path = probe["markets"]["path"]

    events = load_events(markets_path, max_events=args.max_events)
    if not events:
        print("no events found")
        return 1
    target_market_ids = set()
    for e in events:
        target_market_ids.update(e["market_ids"])
    trades = stream_trades_for_markets(target_market_ids, args.max_row_groups)

    all_windows: list[dict] = []
    per_event: list[dict] = []
    for e in events:
        ws = find_arb_windows(e, trades)
        ws_for_event = [{**w, "event_id": e["event_id"], "event_slug": e["event_slug"]} for w in ws]
        all_windows.extend(ws_for_event)
        per_event.append({
            "event_id": e["event_id"], "event_slug": e["event_slug"],
            "n_markets": e["n_markets"], "n_arb_windows": len(ws),
            "max_edge_pct": max((w["max_edge_pct"] for w in ws), default=0),
            "total_arb_minutes": sum(w["duration_min"] for w in ws),
        })

    # Aggregate stats
    if all_windows:
        durations = np.array([w["duration_min"] for w in all_windows])
        edges = np.array([w["max_edge_pct"] for w in all_windows])
        decay_pct = np.array([
            (w["start_sum"] - w["end_sum"]) * 100 for w in all_windows
        ])
        summary = {
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "n_events_sampled": len(events),
            "n_events_with_at_least_one_arb_window": sum(1 for p in per_event if p["n_arb_windows"] > 0),
            "n_total_arb_windows": len(all_windows),
            "window_duration_min": {
                "p25": round(float(np.percentile(durations, 25)), 1),
                "median": round(float(np.median(durations)), 1),
                "p75": round(float(np.percentile(durations, 75)), 1),
                "p95": round(float(np.percentile(durations, 95)), 1),
                "max": round(float(durations.max()), 1),
            },
            "max_edge_pct_per_window": {
                "p25": round(float(np.percentile(edges, 25)), 2),
                "median": round(float(np.median(edges)), 2),
                "p75": round(float(np.percentile(edges, 75)), 2),
                "p95": round(float(np.percentile(edges, 95)), 2),
            },
            "edge_decay_pct_within_window": {
                "p25": round(float(np.percentile(decay_pct, 25)), 2),
                "median": round(float(np.median(decay_pct)), 2),
                "p75": round(float(np.percentile(decay_pct, 75)), 2),
                "p95": round(float(np.percentile(decay_pct, 95)), 2),
                "interpretation": ("positive = sum rose during window (edge being closed by market); "
                                   "negative = sum fell further (edge widening)"),
            },
        }
    else:
        summary = {"n_events_sampled": len(events), "n_total_arb_windows": 0,
                   "note": "no arb windows detected — sample may be too small or trade tape too sparse"}

    out = {"summary": summary, "per_event": per_event,
           "windows_sample": all_windows[:50]}
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str))
    print()
    print("=" * 60)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    sys.exit(main() or 0)
