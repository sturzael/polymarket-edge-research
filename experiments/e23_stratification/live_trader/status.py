"""Inspect flagged markets — show flag history + current/resolved state.

Usage:
    uv run python experiments/e23_stratification/live_trader/inspect.py
    uv run python experiments/e23_stratification/live_trader/inspect.py --since 7d
    uv run python experiments/e23_stratification/live_trader/inspect.py --phase observe
    uv run python experiments/e23_stratification/live_trader/inspect.py --resolve
        (the --resolve flag also fetches current status from gamma for unresolved flags)
"""
from __future__ import annotations

import argparse
import ast
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx

HERE = Path(__file__).parent
FLAGS_JSONL = HERE / "data" / "flagged_markets.jsonl"
GAMMA = "https://gamma-api.polymarket.com"

def load_flags() -> list[dict]:
    if not FLAGS_JSONL.exists(): return []
    return [json.loads(line) for line in FLAGS_JSONL.read_text().splitlines() if line.strip()]

def parse_since(s: str | None) -> datetime | None:
    if not s: return None
    n = int(s.rstrip("dh"))
    unit = s[-1]
    delta = timedelta(days=n) if unit == "d" else timedelta(hours=n)
    return datetime.now(timezone.utc) - delta

def fetch_market_state(client: httpx.Client, cid: str) -> dict | None:
    try:
        r = client.get(f"{GAMMA}/markets", params={"condition_ids": cid, "limit": 1}, timeout=15)
        if r.status_code != 200: return None
        batch = r.json()
        if not batch: return None
        return batch[0]
    except Exception:
        return None

def current_yes_price(m: dict) -> float | None:
    try:
        prices = ast.literal_eval(m.get("outcomePrices", "")) if isinstance(m.get("outcomePrices"), str) else None
        outs = ast.literal_eval(m.get("outcomes", "")) if isinstance(m.get("outcomes"), str) else None
        if not prices or not outs: return None
        if str(outs[0]).lower().startswith("y"): return float(prices[0])
        if str(outs[1]).lower().startswith("y"): return float(prices[1])
        return float(prices[0])
    except Exception:
        return None

def resolution_outcome(m: dict) -> str | None:
    if not m.get("closed"): return None
    try:
        prices = ast.literal_eval(m.get("outcomePrices", "")) if isinstance(m.get("outcomePrices"), str) else None
        outs = ast.literal_eval(m.get("outcomes", "")) if isinstance(m.get("outcomes"), str) else None
        if not prices or not outs: return None
        # outcome with price 1.0 is the winner
        for o, p in zip(outs, prices):
            if float(p) > 0.9:
                return str(o).upper()
    except Exception:
        return None
    return "CLOSED"

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None, help="e.g. 7d or 24h (default: all)")
    ap.add_argument("--phase", choices=["observe", "live", "all"], default="all")
    ap.add_argument("--resolve", action="store_true",
                    help="fetch live status + resolution from gamma")
    args = ap.parse_args()

    flags = load_flags()
    if not flags:
        print("no flags yet — scanner hasn't emitted anything")
        return 0

    since = parse_since(args.since)
    if since:
        flags = [f for f in flags if datetime.fromisoformat(f["flagged_at"]) >= since]
    if args.phase != "all":
        flags = [f for f in flags if f.get("phase") == args.phase]

    print(f"flags: {len(flags)}  "
          f"(filter: since={args.since or 'all'} phase={args.phase})")

    status_by_cid: dict[str, dict] = {}
    if args.resolve and flags:
        with httpx.Client() as client:
            for f in flags:
                cid = f["condition_id"]
                if cid in status_by_cid: continue
                m = fetch_market_state(client, cid)
                if not m: continue
                outcome = resolution_outcome(m)
                status_by_cid[cid] = {
                    "closed": bool(m.get("closed")),
                    "outcome": outcome,
                    "current_yes": current_yes_price(m),
                }

    # Print table
    print()
    print(f"{'flagged_at':<20}  {'phase':<8}  {'sport':<8}  {'price':>5}  "
           f"{'vol$':>8}  {'T-':>5}  {'life':>4}  slug")
    print("-" * 120)
    for f in flags:
        ts = f["flagged_at"][:19]
        sport = f["sport"].replace("sports_", "")
        # backward-compat: old flags had days_to_close, new flags have days_to_event
        d = f.get("days_to_event", f.get("days_to_close", 0))
        row = (f"{ts:<20}  {f['phase']:<8}  {sport:<8}  "
               f"{f['yes_price']:>5.3f}  ${f['window_volume_usd']/1000:>6.1f}k  "
               f"{d:>4.1f}d  {f['lifespan_days']:>3.1f}d  {f['slug']}")
        print(row)
        if args.resolve and f["condition_id"] in status_by_cid:
            s = status_by_cid[f["condition_id"]]
            if s["closed"]:
                print(f"  -> RESOLVED: {s['outcome']}")
            elif s["current_yes"] is not None:
                delta_pp = (s["current_yes"] - f["yes_price"]) * 100
                print(f"  -> now: {s['current_yes']:.3f}  "
                      f"({delta_pp:+.1f}pp vs flag)")

    # Rough stats if resolved
    if args.resolve and status_by_cid:
        resolved = [f for f in flags
                    if status_by_cid.get(f["condition_id"], {}).get("closed")]
        if resolved:
            yes_rate = sum(1 for f in resolved
                           if status_by_cid[f["condition_id"]]["outcome"] == "YES") / len(resolved)
            print(f"\nresolved: {len(resolved)}  yes_rate: {yes_rate:.3f}  "
                  f"(bucket midpoint 0.575 → deviation {(yes_rate - 0.575)*100:+.1f}pp)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
