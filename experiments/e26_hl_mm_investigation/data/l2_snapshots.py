#!/usr/bin/env python3
"""Snapshot L2 book for BTC a few times."""
import json, time, urllib.request, datetime

URL = "https://api.hyperliquid.xyz/info"
OUT = "/tmp/hl_study/e26_mm_research/l2_snapshots.json"

snaps = []
for i in range(5):
    body = {"type":"l2Book","coin":"BTC"}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        book = json.loads(r.read())
    ts = int(time.time()*1000)
    dt = datetime.datetime.fromtimestamp(ts/1000, datetime.UTC)
    bid = float(book["levels"][0][0]["px"])
    ask = float(book["levels"][1][0]["px"])
    mid = (bid+ask)/2
    spread_bps = (ask-bid)/mid * 1e4
    top_bid_sz = float(book["levels"][0][0]["sz"])
    top_ask_sz = float(book["levels"][1][0]["sz"])
    # depth 5 levels
    bid_depth = sum(float(lv["sz"]) for lv in book["levels"][0][:5])
    ask_depth = sum(float(lv["sz"]) for lv in book["levels"][1][:5])
    rec = {
        "ts_ms": ts, "iso": dt.isoformat(), "utc_hour": dt.hour,
        "bid": bid, "ask": ask, "mid": mid, "spread_bps": round(spread_bps,3),
        "top_bid_sz": top_bid_sz, "top_ask_sz": top_ask_sz,
        "5lvl_bid_depth_btc": round(bid_depth,4), "5lvl_ask_depth_btc": round(ask_depth,4),
    }
    print(f"snap {i}: {dt.isoformat()} h={dt.hour} bid={bid} ask={ask} spread={spread_bps:.2f}bps depth5 B={bid_depth:.3f}/A={ask_depth:.3f}")
    snaps.append(rec)
    time.sleep(5)

with open(OUT,"w") as f: json.dump(snaps,f,indent=2)
