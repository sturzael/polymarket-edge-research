"""Q3 — long-duration standing arb retrospective.

Different question than Q2: instead of measuring the median window,
filter to the OUTLIER long-duration windows (≥24h, ≥7d, ≥30d) and ask:

  - **Frequency**: how often do these long arbs appear?
  - **Edge**: how big is the typical edge?
  - **Depth proxy**: how much trade volume passed through during the window?
    (proxy for "could you have plausibly extracted $X from this arb")
  - **Resolution**: do these outlier arbs still resolve cleanly to listed
    outcomes (Q1 on the outlier sub-population)?
  - **Category**: are they concentrated in certain market types?

This is the "is the outlier-persistence strategy real money?" test —
the Q2 median windows are unreachable at our infrastructure but the
outliers (multi-day standing arbs) might be exactly what we can capture.

Method:
  1. Sample stratified across categories from closed neg-risk events
  2. Stream quant.parquet for child markets' trades
  3. 1-min bucket; carry-forward latest price within 6h stale tolerance
  4. Find runs where sum < 1.00; filter to ≥24h
  5. Per long-duration window: duration, min sum, max edge, total volume
  6. Aggregate across events; cross-reference resolution from Q1

Caveats:
  - Survivorship bias: only events resolved before 2026-03-31 SII cutoff.
    Truly-persistent open arbs are NOT in the sample. Q3 frequency is
    a LOWER BOUND.
  - Depth proxy = trade volume = lower bound on standing depth.
  - Stale-tolerance 6h: if a child market had no trade for >6h, the
    aggregate is "unobservable" for that bucket. Low-volume markets
    will under-report arbs.

Sample default: 100 stratified events; 200 quant.parquet row groups.
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from huggingface_hub import HfFileSystem

DATASET = "SII-WANGZJ/Polymarket_data"
HERE = Path(__file__).parent
DATA_DIR = HERE / "data"
OUT_JSON = DATA_DIR / "q3_long_duration.json"
E13_PROBE = HERE / "../e13_external_repo_audit/data/01_probe.json"

STALE_TOL_HOURS = 72   # relaxed from 6 — for low-volume legs in N=18-44 events,
                       # 6h gaps in trade tape were marking minutes as "unobservable"
                       # even when the standing ask hadn't actually moved
BUCKET_MINUTES = 5         # 5-min buckets — fine enough for ≥24h windows, cheap enough for big sample
WINDOW_THRESHOLDS_H = (24, 24*7, 24*30)


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


def categorize(slug: str) -> str:
    s = (slug or "").lower()
    if any(x in s for x in ("temperature","weather","rain","hottest","coldest","snow")): return "weather"
    if any(x in s for x in ("mls-","epl-","la-liga","serie-a","bundesliga","uefa","soccer","-fc-","bra1","bra2","arg","jpn-","fl1-","fl2-","es2-","sea-","bun-","tur-","por-","cricipl","cricpsl")): return "soccer_other"
    if any(x in s for x in ("nba-","nfl-","mlb-","nhl-","ufc-","atp-","wta-","tennis","golf","cricket","wnba","f1-","formula","boxing")): return "sports_other"
    if any(x in s for x in ("president","senate","governor","election","nominee","primary","candidate","impeach","potus","congress")): return "politics_election"
    if any(x in s for x in ("btc","eth","bitcoin","ethereum","crypto","sol","xrp","fed-")): return "crypto_macro"
    if any(x in s for x in ("oscar","grammy","emmy","album","movie","box-office","chart","netflix","spotify","tiktok","musk","tweet","elon")): return "entertainment_pop"
    if any(x in s for x in ("nobel","prize","award","ceo","succession","appointment","named","fired","resign","next-")): return "open_ended_award"
    if any(x in s for x in ("iran","israel","ukraine","russia","war","ceasefire","strike","attack","treaty","sanctions")): return "geopolitics"
    return "other"


def load_stratified_events(markets_path: str, n_per_category: int):
    """Closed neg-risk events with clean LISTED-WIN resolution; stratified."""
    print(f"[load] reading markets.parquet...")
    df = pq.read_table(markets_path).to_pandas()
    closed_neg = df[(df["closed"] == 1) & (df["neg_risk"] == 1)].copy()
    print(f"  {len(closed_neg):,} closed neg-risk markets")
    closed_neg["_outcomes"] = closed_neg["outcome_prices"].apply(parse_outcome_prices)
    closed_neg["yes_payout"] = closed_neg["_outcomes"].apply(lambda t: t[0] if t else None)
    closed_neg["event_slug_lc"] = closed_neg["event_slug"].astype(str).str.lower()
    grouped = closed_neg.groupby("event_id").agg(
        n_markets=("id", "count"),
        market_ids=("id", lambda s: list(s.astype(str))),
        slugs=("slug", lambda s: list(s)),
        event_slug=("event_slug", "first"),
        yes_winners=("yes_payout", lambda s: int((s == 1.0).sum())),
        end_date=("end_date", "max"),
        start_date=("created_at", "min"),
    ).reset_index()
    eligible = grouped[(grouped["n_markets"] >= 2) & (grouped["yes_winners"] == 1)].copy()
    eligible["lifetime_days"] = (eligible["end_date"] - eligible["start_date"]).dt.total_seconds() / 86400
    # Only keep events that lived ≥7 days — anything shorter can't host a 24h arb meaningfully
    before = len(eligible)
    eligible = eligible[eligible["lifetime_days"] >= 7]
    print(f"  {before:,} eligible → {len(eligible):,} with lifetime ≥7d")
    eligible["category"] = eligible["event_slug"].astype(str).apply(categorize)
    print(f"  {len(eligible):,} eligible events; categories:")
    for cat, n in eligible["category"].value_counts().items():
        print(f"    {cat:<22} {n}")
    # Stratified sample
    sampled = []
    for cat, sub in eligible.groupby("category"):
        take = min(n_per_category, len(sub))
        sampled.append(sub.sample(n=take, random_state=42))
    out = pd.concat(sampled).to_dict("records")
    print(f"  stratified sample: {len(out)} events")
    return out


def stream_trades(market_id_set: set, max_rg: int):
    fs = HfFileSystem()
    path = f"datasets/{DATASET}/quant.parquet"
    out = defaultdict(list)
    t0 = time.time()
    print(f"[stream] target={len(market_id_set):,} markets, max_rg={max_rg}")
    with fs.open(path, "rb") as f:
        pfile = pq.ParquetFile(f)
        cols = ["timestamp", "market_id", "price", "usd_amount"]
        existing = [c for c in cols if c in pfile.schema_arrow.names]
        for rg_idx in range(min(pfile.metadata.num_row_groups, max_rg)):
            rg = pfile.read_row_group(rg_idx, columns=existing).to_pandas()
            rg["market_id"] = rg["market_id"].astype(str)
            keep = rg[rg["market_id"].isin(market_id_set)]
            if len(keep) > 0:
                for mid, sub in keep.groupby("market_id"):
                    out[mid].append(sub)
            if rg_idx % 25 == 0:
                tot = sum(len(p) for parts in out.values() for p in parts)
                print(f"  RG {rg_idx+1}: tot_rows={tot:,} markets_seen={len(out)} ({time.time()-t0:.0f}s)")
    final = {}
    for mid, parts in out.items():
        df = pd.concat(parts, ignore_index=True).sort_values("timestamp")
        df["ts"] = df["timestamp"].apply(lambda v: v / 1000 if v > 1e12 else v)
        final[mid] = df
    print(f"  collected trades for {len(final)}/{len(market_id_set)} markets ({time.time()-t0:.0f}s)")
    return final


def find_long_windows(event: dict, trades: dict) -> list[dict]:
    """Return list of arb windows ≥24h with depth proxy."""
    market_ids = list(event["market_ids"])
    market_trades = {mid: trades[mid] for mid in market_ids if mid in trades}
    if len(market_trades) < 2:
        return []
    bucket_secs = BUCKET_MINUTES * 60
    stale_buckets = (STALE_TOL_HOURS * 3600) // bucket_secs

    # Per-market: bucket→latest_price + bucket→volume
    series = {}
    for mid, df in market_trades.items():
        df = df.copy()
        df["bucket"] = (df["ts"] // bucket_secs).astype(int)
        last_price = df.groupby("bucket")["price"].last().sort_index()
        vol = df.groupby("bucket")["usd_amount"].sum().sort_index()
        series[mid] = {"price": last_price, "vol": vol}

    # Union of all buckets
    all_buckets = sorted({b for s in series.values() for b in s["price"].index})
    if len(all_buckets) < int(24 * 60 / BUCKET_MINUTES):  # need at least 24h of any data
        return []

    # For each bucket: implied sum + total volume
    sums = []
    vols = []
    for bk in all_buckets:
        prices = []
        vol_total = 0.0
        all_fresh = True
        for mid, s in series.items():
            idx = s["price"].index.searchsorted(bk, side="right") - 1
            if idx < 0:
                all_fresh = False; break
            last_bk = s["price"].index[idx]
            if (bk - last_bk) > stale_buckets:
                all_fresh = False; break
            prices.append(float(s["price"].iloc[idx]))
            # Add volume in this bucket if present
            vbk = s["vol"]
            v_idx = vbk.index.searchsorted(bk, side="left")
            if v_idx < len(vbk) and vbk.index[v_idx] == bk:
                vol_total += float(vbk.iloc[v_idx])
        if not all_fresh:
            sums.append(None); vols.append(0.0); continue
        sums.append(sum(prices)); vols.append(vol_total)

    # Find runs sum < 1
    windows = []
    i = 0
    min_buckets_24h = (24 * 60) // BUCKET_MINUTES
    while i < len(sums):
        if sums[i] is None or sums[i] >= 1.0:
            i += 1; continue
        start_idx = i
        min_sum = sums[i]
        sum_vol = 0.0
        while i < len(sums) and sums[i] is not None and sums[i] < 1.0:
            min_sum = min(min_sum, sums[i])
            sum_vol += vols[i]
            i += 1
        end_idx = i  # exclusive
        n_buckets = end_idx - start_idx
        if n_buckets < min_buckets_24h:
            continue  # only keep ≥24h windows
        duration_h = n_buckets * BUCKET_MINUTES / 60
        windows.append({
            "duration_h": round(duration_h, 1),
            "start_bucket": all_buckets[start_idx],
            "end_bucket": all_buckets[end_idx-1],
            "min_sum": round(min_sum, 4),
            "max_edge_pct": round((1 - min_sum) * 100, 2),
            "total_volume_usd_during_window": round(sum_vol, 2),
        })
    return windows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-category", type=int, default=15,
                    help="events to sample per category (stratified)")
    ap.add_argument("--max-rg", type=int, default=200,
                    help="max quant.parquet row groups")
    args = ap.parse_args()

    DATA_DIR.mkdir(exist_ok=True)
    if not E13_PROBE.exists():
        print(f"ABORT: e13 probe missing"); return 2
    probe = json.loads(E13_PROBE.read_text())
    markets_path = probe["markets"]["path"]

    events = load_stratified_events(markets_path, n_per_category=args.per_category)
    target_mids = {mid for e in events for mid in e["market_ids"]}
    trades = stream_trades(target_mids, max_rg=args.max_rg)

    per_event = []
    all_long = []
    for e in events:
        ws = find_long_windows(e, trades)
        per_event.append({
            "event_id": e["event_id"], "event_slug": e["event_slug"],
            "category": e["category"], "n_markets": e["n_markets"],
            "n_long_windows": len(ws),
            "longest_h": max((w["duration_h"] for w in ws), default=0),
            "max_edge_pct": max((w["max_edge_pct"] for w in ws), default=0),
            "total_vol_in_long_windows": sum(w["total_volume_usd_during_window"] for w in ws),
        })
        for w in ws:
            all_long.append({**w, "event_id": e["event_id"],
                             "event_slug": e["event_slug"], "category": e["category"]})

    # Aggregates
    n_total = len(events)
    n_with_24h = sum(1 for p in per_event if p["n_long_windows"] >= 1 and p["longest_h"] >= 24)
    n_with_7d = sum(1 for p in per_event if p["longest_h"] >= 24*7)
    n_with_30d = sum(1 for p in per_event if p["longest_h"] >= 24*30)

    cat_freq = {}
    for cat, sub in pd.DataFrame(per_event).groupby("category"):
        n = len(sub)
        n_with_arb = int((sub["n_long_windows"] >= 1).sum())
        cat_freq[cat] = {
            "n_events": n,
            "n_with_long_arb": n_with_arb,
            "frequency_pct": round(n_with_arb / max(n, 1) * 100, 1),
            "median_longest_h": round(float(sub.loc[sub["n_long_windows"] >= 1, "longest_h"].median()), 1) if n_with_arb else None,
            "median_max_edge_pct": round(float(sub.loc[sub["n_long_windows"] >= 1, "max_edge_pct"].median()), 2) if n_with_arb else None,
        }

    summary = {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "n_events_sampled": n_total,
        "n_total_long_windows": len(all_long),
        "freq_with_arb_24h": f"{n_with_24h}/{n_total} ({100*n_with_24h/max(n_total,1):.1f}%)",
        "freq_with_arb_7d": f"{n_with_7d}/{n_total} ({100*n_with_7d/max(n_total,1):.1f}%)",
        "freq_with_arb_30d": f"{n_with_30d}/{n_total} ({100*n_with_30d/max(n_total,1):.1f}%)",
        "by_category": cat_freq,
    }
    if all_long:
        durations = np.array([w["duration_h"] for w in all_long])
        edges = np.array([w["max_edge_pct"] for w in all_long])
        vols = np.array([w["total_volume_usd_during_window"] for w in all_long])
        summary["long_window_duration_hours"] = {
            "p25": round(float(np.percentile(durations, 25)), 1),
            "median": round(float(np.median(durations)), 1),
            "p75": round(float(np.percentile(durations, 75)), 1),
            "p95": round(float(np.percentile(durations, 95)), 1),
            "max": round(float(durations.max()), 1),
        }
        summary["long_window_max_edge_pct"] = {
            "p25": round(float(np.percentile(edges, 25)), 2),
            "median": round(float(np.median(edges)), 2),
            "p75": round(float(np.percentile(edges, 75)), 2),
            "p95": round(float(np.percentile(edges, 95)), 2),
        }
        summary["long_window_depth_proxy_usd"] = {
            "p25": round(float(np.percentile(vols, 25)), 0),
            "median": round(float(np.median(vols)), 0),
            "p75": round(float(np.percentile(vols, 75)), 0),
            "p95": round(float(np.percentile(vols, 95)), 0),
            "interpretation": "total trade volume during window (lower bound on capturable depth)",
        }

    out = {"summary": summary, "per_event": per_event,
           "long_windows_sample": all_long[:50]}
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str))
    print()
    print("=" * 60)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    sys.exit(main() or 0)
