"""
Step 2: Profile the 9 top-wallet synthetics traders.
Reads existing e25 fill files (already on disk).
For each wallet:
- Fill count, USD notional
- Asset concentration: top-3 assets, % fills + % notional
- Open/Close/Liquidation composition
- Hour-of-day distribution (UTC)
- MM vs directional heuristic
"""
import json, os, sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

WALLETS = [
    ("rank14", "0xa312114b5795dff9b8db50474dd57701aa78ad1e", 96_400_000),
    ("rank16", "0x2e3d94f0562703b25c83308a05046ddaf9a8dd14", 84_600_000),
    ("rank19", "0xbdfa4f4492dd7b7cf211209c4791af8d52bf5c50", 76_000_000),
    ("rank23", "0x5d2f4460ac3514ada79f5d9838916e508ab39bb7", 63_100_000),
    ("rank24", "0x8af700ba841f30e0a3fcb0ee4c4a9d223e1efa05", 62_900_000),
    ("rank28", "0x8e096995c3e4a3f0bc5b3ea1cba94de2aa4d70c9", 58_900_000),
    ("rank32", "0x939f95036d2e7b6d7419ec072bf9d967352204d2", 52_200_000),
    ("rank35", "0x7dacca323e44f168494c779bb5e7483c468ef410", 47_300_000),
    ("rank50", "0x82d8dc80190e6bc1d92b048f9fc7e85e5e1e32ff", 33_100_000),
]

FILLS_DIR = "/Users/elliotsturzaker/dev/event-impact-mvp/experiments/e25_hyperliquid_forensics/data/fills"
OUT = "/Users/elliotsturzaker/dev/event-impact-mvp/experiments/e27_hl_synthetics_recon/data/wallet_profiles.json"


def profile(fills):
    n = len(fills)
    if n == 0:
        return None
    total_ntl = 0.0
    by_coin_n = Counter()
    by_coin_ntl = Counter()
    dir_counter = Counter()
    hour_counter = Counter()
    times = []
    cross_count = 0  # taker
    maker_count = 0
    fees = 0.0
    closed_pnl = 0.0
    liquidation_count = 0
    for f in fills:
        try:
            px = float(f["px"])
            sz = float(f["sz"])
        except Exception:
            continue
        ntl = px * sz
        total_ntl += ntl
        coin = f["coin"]
        by_coin_n[coin] += 1
        by_coin_ntl[coin] += ntl
        d = f.get("dir", "")
        dir_counter[d] += 1
        t = f.get("time", 0)
        if t:
            times.append(t)
            hour_counter[datetime.fromtimestamp(t / 1000, tz=timezone.utc).hour] += 1
        if f.get("crossed"):
            cross_count += 1
        else:
            maker_count += 1
        try:
            fees += float(f.get("fee", 0) or 0)
        except Exception:
            pass
        try:
            closed_pnl += float(f.get("closedPnl", 0) or 0)
        except Exception:
            pass
        if f.get("liquidation"):
            liquidation_count += 1
    time_range_days = None
    if times:
        time_range_days = (max(times) - min(times)) / (1000 * 86400)
    # Classification
    opens = sum(v for k, v in dir_counter.items() if k.startswith("Open"))
    closes = sum(v for k, v in dir_counter.items() if k.startswith("Close"))
    liquidation_fills = sum(v for k, v in dir_counter.items() if "Liquidat" in k)
    buys = sum(v for k, v in dir_counter.items() if k == "Buy")
    sells = sum(v for k, v in dir_counter.items() if k == "Sell")
    # Maker vs taker share
    maker_share = maker_count / n if n else 0
    # MM heuristic: very high maker share, ~balanced open/close flip, consistent 24h activity
    hour_coverage = len({h for h, c in hour_counter.items() if c >= n * 0.02})
    # role classification
    if liquidation_fills > n * 0.5:
        role = "liquidator/backstop"
    elif maker_share > 0.7 and hour_coverage >= 18:
        role = "market_maker_candidate"
    elif maker_share < 0.3:
        role = "aggressive_taker"
    else:
        role = "mixed"
    # Top assets
    top_assets = []
    for coin, cnt in by_coin_n.most_common(5):
        top_assets.append({
            "coin": coin,
            "fill_count": cnt,
            "fill_pct": round(100 * cnt / n, 2),
            "ntl_usd": round(by_coin_ntl[coin], 2),
            "ntl_pct": round(100 * by_coin_ntl[coin] / total_ntl, 2) if total_ntl else 0,
        })
    return {
        "n_fills": n,
        "total_ntl_usd": round(total_ntl, 2),
        "distinct_coins": len(by_coin_n),
        "top_assets": top_assets,
        "dir_composition": dict(dir_counter.most_common()),
        "maker_share": round(maker_share, 3),
        "taker_share": round(1 - maker_share, 3),
        "liquidation_fills": liquidation_fills,
        "fees_usd": round(fees, 2),
        "closed_pnl_usd": round(closed_pnl, 2),
        "time_range_days": round(time_range_days, 2) if time_range_days else None,
        "earliest_fill_utc": datetime.fromtimestamp(min(times) / 1000, tz=timezone.utc).isoformat() if times else None,
        "latest_fill_utc": datetime.fromtimestamp(max(times) / 1000, tz=timezone.utc).isoformat() if times else None,
        "hour_distribution_utc": dict(sorted(hour_counter.items())),
        "hours_active_ge_2pct": hour_coverage,
        "role_heuristic": role,
    }


def main():
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "wallets": {},
        "asset_aggregation": {},
    }
    cross_asset_fills = Counter()
    cross_asset_ntl = Counter()
    cross_asset_wallets = defaultdict(set)
    for rank, addr, pnl in WALLETS:
        path = os.path.join(FILLS_DIR, f"{addr}.json")
        if not os.path.exists(path):
            out["wallets"][rank] = {"addr": addr, "error": "missing_fill_file"}
            continue
        try:
            fills = json.load(open(path))
        except Exception as e:
            out["wallets"][rank] = {"addr": addr, "error": f"load_failed: {e}"}
            continue
        prof = profile(fills)
        if prof is None:
            out["wallets"][rank] = {"addr": addr, "allTime_pnl": pnl, "error": "no_fills"}
            continue
        prof["addr"] = addr
        prof["allTime_pnl_usd"] = pnl
        out["wallets"][rank] = prof
        # aggregate
        for asset in prof["top_assets"]:
            coin = asset["coin"]
            cross_asset_fills[coin] += asset["fill_count"]
            cross_asset_ntl[coin] += asset["ntl_usd"]
            cross_asset_wallets[coin].add(rank)

    # cross-wallet aggregation — top assets across top-PnL wallets
    agg = []
    for coin, fills in cross_asset_fills.most_common(30):
        agg.append({
            "coin": coin,
            "fill_count_across_wallets": fills,
            "ntl_usd_across_wallets": round(cross_asset_ntl[coin], 2),
            "wallets_using": sorted(list(cross_asset_wallets[coin])),
            "n_wallets": len(cross_asset_wallets[coin]),
        })
    out["asset_aggregation"] = agg

    with open(OUT, "w") as f:
        json.dump(out, f, indent=2)

    # Summary print
    print("Per-wallet summary:")
    for rank, addr, pnl in WALLETS:
        w = out["wallets"][rank]
        if "error" in w:
            print(f"  {rank} {addr}: ERROR {w['error']}")
            continue
        print(f"\n{rank} {addr} (allTime=${pnl/1e6:.1f}M)")
        print(f"  fills={w['n_fills']}, ntl=${w['total_ntl_usd']:,.0f}, distinct_coins={w['distinct_coins']}, range={w['time_range_days']}d")
        print(f"  maker={w['maker_share']} taker={w['taker_share']} role={w['role_heuristic']} hours_active={w['hours_active_ge_2pct']}/24")
        print(f"  earliest={w['earliest_fill_utc']}, latest={w['latest_fill_utc']}")
        print(f"  top-5 assets:")
        for a in w["top_assets"]:
            print(f"    {a['coin']:<14} fills={a['fill_count']:>5} ({a['fill_pct']}%)  ntl=${a['ntl_usd']:>14,.0f} ({a['ntl_pct']}%)")
        # show dir composition top 5
        di = list(w["dir_composition"].items())[:6]
        print(f"  dirs(top6): {di}")
    print("\n\nCross-wallet top assets (among 9):")
    for a in agg[:20]:
        print(f"  {a['coin']:<14} fills={a['fill_count_across_wallets']:>6}  wallets={a['n_wallets']}  ntl=${a['ntl_usd_across_wallets']:>14,.0f}")
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
