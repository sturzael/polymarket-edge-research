"""
Step 1: Enumerate HL asset universe.
Pulls metaAndAssetCtxs (perps) + spotMetaAndAssetCtxs (spots).
Produces data/asset_universe.json ranked by 24h volume.
"""
import json, sys, time, urllib.request

API = "https://api.hyperliquid.xyz/info"
OUT = "/Users/elliotsturzaker/dev/event-impact-mvp/experiments/e27_hl_synthetics_recon/data/asset_universe.json"


def post(body):
    req = urllib.request.Request(
        API,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def main():
    print("Fetching perps metaAndAssetCtxs...", file=sys.stderr)
    perps = post({"type": "metaAndAssetCtxs"})
    # perps is [meta, ctxs]. meta.universe is list of {name, szDecimals, maxLeverage, ...}
    perp_meta = perps[0]
    perp_ctxs = perps[1]
    perps_out = []
    for i, asset in enumerate(perp_meta["universe"]):
        ctx = perp_ctxs[i] if i < len(perp_ctxs) else {}
        perps_out.append({
            "kind": "perp",
            "name": asset.get("name"),
            "sz_decimals": asset.get("szDecimals"),
            "max_leverage": asset.get("maxLeverage"),
            "only_isolated": asset.get("onlyIsolated", False),
            "mark_px": float(ctx.get("markPx", 0) or 0),
            "prev_day_px": float(ctx.get("prevDayPx", 0) or 0),
            "day_ntl_vlm": float(ctx.get("dayNtlVlm", 0) or 0),
            "open_interest": float(ctx.get("openInterest", 0) or 0),
            "funding": float(ctx.get("funding", 0) or 0),
            "oracle_px": float(ctx.get("oraclePx", 0) or 0),
            "premium": float(ctx.get("premium", 0) or 0) if ctx.get("premium") is not None else None,
        })
    time.sleep(0.5)

    print("Fetching spot spotMetaAndAssetCtxs...", file=sys.stderr)
    spots = post({"type": "spotMetaAndAssetCtxs"})
    spot_meta = spots[0]
    spot_ctxs = spots[1]
    tokens = {t["index"]: t for t in spot_meta["tokens"]}
    spots_out = []
    for i, pair in enumerate(spot_meta["universe"]):
        ctx = spot_ctxs[i] if i < len(spot_ctxs) else {}
        base_idx, quote_idx = pair["tokens"]
        base = tokens.get(base_idx, {}).get("name", f"tok{base_idx}")
        quote = tokens.get(quote_idx, {}).get("name", f"tok{quote_idx}")
        spots_out.append({
            "kind": "spot",
            "name": pair.get("name"),
            "base": base,
            "quote": quote,
            "mark_px": float(ctx.get("markPx", 0) or 0),
            "prev_day_px": float(ctx.get("prevDayPx", 0) or 0),
            "day_ntl_vlm": float(ctx.get("dayNtlVlm", 0) or 0),
            "circulating_supply": float(ctx.get("circulatingSupply", 0) or 0),
            "mid_px": float(ctx.get("midPx", 0) or 0) if ctx.get("midPx") else None,
        })

    # Rank
    perps_out.sort(key=lambda x: -x["day_ntl_vlm"])
    spots_out.sort(key=lambda x: -x["day_ntl_vlm"])

    # Tag synthetics: xyz: prefix, or look like ticker/pair markers
    for a in perps_out:
        name = a["name"] or ""
        a["is_synthetic_prefix"] = name.startswith("xyz:") or name.startswith("@")
        a["is_major"] = name in ("BTC", "ETH", "SOL")

    bundle = {
        "timestamp_ms": int(time.time() * 1000),
        "n_perps": len(perps_out),
        "n_spots": len(spots_out),
        "perps_by_volume": perps_out,
        "spots_by_volume": spots_out,
    }
    with open(OUT, "w") as f:
        json.dump(bundle, f, indent=2)
    # Print head
    print(f"Perps: {len(perps_out)}  Spots: {len(spots_out)}")
    print("\nTop 25 perps by 24h ntl vol:")
    for a in perps_out[:25]:
        syn = "[SYN]" if a["is_synthetic_prefix"] else ("[MAJ]" if a["is_major"] else "")
        print(f"  {a['name']:<15} vol=${a['day_ntl_vlm']:>14,.0f}  mark={a['mark_px']:>10}  OI=${a['open_interest']*a['mark_px']:>12,.0f} {syn}")
    print("\nTop 10 spots by 24h ntl vol:")
    for a in spots_out[:10]:
        print(f"  {a['name']:<15} ({a['base']}/{a['quote']}) vol=${a['day_ntl_vlm']:>14,.0f}  mark={a['mark_px']:>10}")
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
