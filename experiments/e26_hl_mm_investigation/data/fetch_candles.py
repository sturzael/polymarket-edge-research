#!/usr/bin/env python3
"""Fetch HL BTC-PERP 1m candles for last 60 days."""
import json
import time
import urllib.request
import os

URL = "https://api.hyperliquid.xyz/info"
OUT = "/tmp/hl_study/e26_mm_research/btc_1m_candles.json"

now_ms = int(time.time() * 1000)
sixty_d_ms = 60 * 24 * 60 * 60 * 1000
start = now_ms - sixty_d_ms

# HL returns up to 5000 per call. 1m over 60d = 86400 candles => ~18 chunks.
# Chunk windows by ~3 days (4320 minutes) to be safe.
chunk_ms = 3 * 24 * 60 * 60 * 1000

all_candles = []
seen_times = set()
cur = start
i = 0
while cur < now_ms:
    end = min(cur + chunk_ms, now_ms)
    body = {
        "type": "candleSnapshot",
        "req": {
            "coin": "BTC",
            "interval": "1m",
            "startTime": cur,
            "endTime": end,
        },
    }
    data = json.dumps(body).encode()
    req = urllib.request.Request(URL, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            arr = json.loads(r.read())
    except Exception as e:
        print(f"chunk {i} err: {e}; retrying")
        time.sleep(2)
        with urllib.request.urlopen(req, timeout=30) as r:
            arr = json.loads(r.read())
    new_ct = 0
    for c in arr:
        t = c.get("t")
        if t not in seen_times:
            seen_times.add(t)
            all_candles.append(c)
            new_ct += 1
    print(f"chunk {i}: {cur} -> {end}, returned {len(arr)}, new {new_ct}, total {len(all_candles)}")
    cur = end
    i += 1
    time.sleep(0.2)  # rate limit politeness

all_candles.sort(key=lambda c: c["t"])
print(f"total candles: {len(all_candles)}")
if all_candles:
    print(f"first t: {all_candles[0]['t']} last t: {all_candles[-1]['t']}")
with open(OUT, "w") as f:
    json.dump(all_candles, f)
print(f"saved -> {OUT}")
