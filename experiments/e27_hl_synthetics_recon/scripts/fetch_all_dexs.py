"""
Fetch meta+ctxs for ALL perpDexs (core + xyz + km) and spot,
then merge into a single asset universe ranked by 24h volume.
"""
import json, sys, time, urllib.request

API = "https://api.hyperliquid.xyz/info"
OUT = "/Users/elliotsturzaker/dev/event-impact-mvp/experiments/e27_hl_synthetics_recon/data/asset_universe.json"


def post(body):
    req = urllib.request.Request(API, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def fetch_perp_dex(dex_name):
    body = {"type": "metaAndAssetCtxs"}
    if dex_name:
        body["dex"] = dex_name
    d = post(body)
    meta, ctxs = d
    rows = []
    for i, a in enumerate(meta["universe"]):
        c = ctxs[i] if i < len(ctxs) else {}
        rows.append({
            "kind": "perp",
            "dex": dex_name or "core",
            "name": a.get("name"),
            "sz_decimals": a.get("szDecimals"),
            "max_leverage": a.get("maxLeverage"),
            "mark_px": float(c.get("markPx", 0) or 0),
            "prev_day_px": float(c.get("prevDayPx", 0) or 0),
            "day_ntl_vlm": float(c.get("dayNtlVlm", 0) or 0),
            "open_interest_units": float(c.get("openInterest", 0) or 0),
            "funding": float(c.get("funding", 0) or 0),
            "oracle_px": float(c.get("oraclePx", 0) or 0),
        })
    return rows


def main():
    dexs = post({"type": "perpDexs"})
    # first entry is null (core), others are named
    dex_names = [None]
    for d in dexs[1:]:
        if d and isinstance(d, dict):
            dex_names.append(d["name"])
    print(f"Detected perp dexs: {dex_names}", file=sys.stderr)

    all_perps = []
    for name in dex_names:
        try:
            rows = fetch_perp_dex(name)
            all_perps.extend(rows)
            print(f"  {name or 'core'}: {len(rows)} assets", file=sys.stderr)
            time.sleep(0.5)
        except Exception as e:
            print(f"  {name}: ERROR {e}", file=sys.stderr)

    # spot
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
            "ticker": f"{base}/{quote}",
            "mark_px": float(ctx.get("markPx", 0) or 0),
            "prev_day_px": float(ctx.get("prevDayPx", 0) or 0),
            "day_ntl_vlm": float(ctx.get("dayNtlVlm", 0) or 0),
            "mid_px": float(ctx.get("midPx", 0) or 0) if ctx.get("midPx") else None,
        })

    all_perps.sort(key=lambda x: -x["day_ntl_vlm"])
    spots_out.sort(key=lambda x: -x["day_ntl_vlm"])

    # categorize
    for a in all_perps:
        n = a["name"] or ""
        a["category"] = (
            "major" if n in ("BTAG","BTC","ETH","SOL") else
            "synthetic_xyz" if n.startswith("xyz:") else
            "synthetic_km" if n.startswith("km:") else
            "hl_native_alt"
        )

    bundle = {
        "timestamp_ms": int(time.time() * 1000),
        "n_perp_dexs": len(dex_names),
        "dex_names": [d or "core" for d in dex_names],
        "n_perps": len(all_perps),
        "n_spots": len(spots_out),
        "perps_by_volume": all_perps,
        "spots_by_volume": spots_out,
    }
    with open(OUT, "w") as f:
        json.dump(bundle, f, indent=2)

    print(f"\nTotal perps across all dexs: {len(all_perps)}")
    print("\nTop 30 perps (all dexs) by 24h ntl vol:")
    for a in all_perps[:30]:
        tag = f"[{a['category']}]"
        oi_usd = a["open_interest_units"] * a["mark_px"]
        print(f"  {a['name']:<20} dex={a['dex']:<5} vol=${a['day_ntl_vlm']:>14,.0f}  mark={a['mark_px']:<10}  OI=${oi_usd:>12,.0f} {tag}")

    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
