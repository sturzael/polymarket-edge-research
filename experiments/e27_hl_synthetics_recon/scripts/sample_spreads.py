"""
Step 3: L2 book snapshots for top synthetics + majors baseline.
Takes 5 snapshots ~90s apart for each asset.
Computes top-of-book spread bps, depth within 25/50 bps of mid, update frequency proxy.
"""
import json, sys, time, urllib.request
from datetime import datetime, timezone

API = "https://api.hyperliquid.xyz/info"
OUT = "/Users/elliotsturzaker/dev/event-impact-mvp/experiments/e27_hl_synthetics_recon/data/spread_snapshots.json"

# Target: 10 most-traded non-BTC/ETH/SOL + majors for comparison
ASSETS = [
    # name, dex
    ("BTC", None),            # major baseline (e26 comparison)
    ("ETH", None),            # major baseline
    ("SOL", None),            # major baseline
    ("xyz:CL", "xyz"),        # top synthetic by vol
    ("xyz:SP500", "xyz"),
    ("xyz:BRENTOIL", "xyz"),
    ("xyz:XYZ100", "xyz"),
    ("xyz:SILVER", "xyz"),
    ("xyz:GOLD", "xyz"),
    ("xyz:MSTR", "xyz"),
    ("xyz:TSLA", "xyz"),
    ("HYPE", None),
    ("TAO", None),
    ("MON", None),
    ("LIT", None),
    ("AAVE", None),
    ("ZEC", None),
    ("FARTCOIN", None),
    ("XMR", None),
    ("PAXG", None),
]


def post(body):
    req = urllib.request.Request(API, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def snap(coin):
    # l2Book accepts coin as either core name or "xyz:CL" — let's try
    return post({"type": "l2Book", "coin": coin})


def analyze(book):
    levels = book.get("levels", [])
    if len(levels) != 2:
        return None
    bids = levels[0]
    asks = levels[1]
    if not bids or not asks:
        return None
    best_bid = float(bids[0]["px"])
    best_ask = float(asks[0]["px"])
    best_bid_sz = float(bids[0]["sz"])
    best_ask_sz = float(asks[0]["sz"])
    mid = (best_bid + best_ask) / 2
    spread_bps = (best_ask - best_bid) / mid * 10000 if mid > 0 else None
    # Depth within 25bps and 50bps of mid
    def depth_within(side_levels, lo, hi):
        ntl = 0.0
        for lvl in side_levels:
            px = float(lvl["px"])
            sz = float(lvl["sz"])
            if lo <= px <= hi:
                ntl += px * sz
        return ntl
    d25 = {
        "bid_usd": depth_within(bids, mid * (1 - 0.0025), mid),
        "ask_usd": depth_within(asks, mid, mid * (1 + 0.0025)),
    }
    d50 = {
        "bid_usd": depth_within(bids, mid * (1 - 0.005), mid),
        "ask_usd": depth_within(asks, mid, mid * (1 + 0.005)),
    }
    return {
        "best_bid": best_bid,
        "best_ask": best_ask,
        "mid": mid,
        "best_bid_sz": best_bid_sz,
        "best_ask_sz": best_ask_sz,
        "best_bid_ntl_usd": round(best_bid * best_bid_sz, 2),
        "best_ask_ntl_usd": round(best_ask * best_ask_sz, 2),
        "spread_bps": round(spread_bps, 3) if spread_bps is not None else None,
        "n_bid_levels": len(bids),
        "n_ask_levels": len(asks),
        "depth_25bps_usd": {k: round(v, 2) for k, v in d25.items()},
        "depth_50bps_usd": {k: round(v, 2) for k, v in d50.items()},
    }


def main():
    n_snaps = 5
    interval_s = 45  # 45s between snapshots
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_snapshots_per_asset": n_snaps,
        "interval_seconds": interval_s,
        "assets": {},
    }
    for round_idx in range(n_snaps):
        print(f"\n=== Round {round_idx+1}/{n_snaps} ===")
        for coin, dex in ASSETS:
            try:
                b = snap(coin)
                a = analyze(b)
                if a is None:
                    print(f"  {coin}: EMPTY book", file=sys.stderr)
                    continue
                a["ts_ms"] = int(time.time() * 1000)
                out["assets"].setdefault(coin, {"dex": dex, "snapshots": []})["snapshots"].append(a)
                print(f"  {coin:<18} bid={a['best_bid']:<10} ask={a['best_ask']:<10} spread={a['spread_bps']:>8.3f}bps  d50_bid=${a['depth_50bps_usd']['bid_usd']:>10,.0f} d50_ask=${a['depth_50bps_usd']['ask_usd']:>10,.0f}")
                time.sleep(0.15)
            except Exception as e:
                print(f"  {coin}: ERROR {e}", file=sys.stderr)
        if round_idx < n_snaps - 1:
            print(f"  ... sleeping {interval_s}s")
            time.sleep(interval_s)
    # Summarize per asset
    summary = []
    for coin, v in out["assets"].items():
        spreads = [s["spread_bps"] for s in v["snapshots"] if s.get("spread_bps") is not None]
        bid_d50 = [s["depth_50bps_usd"]["bid_usd"] for s in v["snapshots"]]
        ask_d50 = [s["depth_50bps_usd"]["ask_usd"] for s in v["snapshots"]]
        # update freq proxy: how often does top-of-book change between snapshots?
        tob_changes = 0
        prev = None
        for s in v["snapshots"]:
            tob = (s["best_bid"], s["best_ask"])
            if prev is not None and tob != prev:
                tob_changes += 1
            prev = tob
        summary.append({
            "coin": coin,
            "dex": v["dex"],
            "mean_spread_bps": round(sum(spreads)/len(spreads), 3) if spreads else None,
            "min_spread_bps": round(min(spreads), 3) if spreads else None,
            "max_spread_bps": round(max(spreads), 3) if spreads else None,
            "mean_depth_50bps_bid_usd": round(sum(bid_d50)/len(bid_d50), 2) if bid_d50 else None,
            "mean_depth_50bps_ask_usd": round(sum(ask_d50)/len(ask_d50), 2) if ask_d50 else None,
            "tob_changes_across_snapshots": tob_changes,
            "n_snapshots": len(v["snapshots"]),
        })
    summary.sort(key=lambda r: (r["mean_spread_bps"] if r["mean_spread_bps"] is not None else 0))
    out["summary"] = summary
    with open(OUT, "w") as f:
        json.dump(out, f, indent=2)
    print("\n\n=== SUMMARY (sorted by spread) ===")
    for r in summary:
        print(f"  {r['coin']:<18} spread_bps mean={r['mean_spread_bps']}  min={r['min_spread_bps']}  max={r['max_spread_bps']}   d50_bid=${r['mean_depth_50bps_bid_usd']:>10,.0f} d50_ask=${r['mean_depth_50bps_ask_usd']:>10,.0f}  tob_chg={r['tob_changes_across_snapshots']}/{r['n_snapshots']-1}")
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
