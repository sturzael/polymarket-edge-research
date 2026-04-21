#!/usr/bin/env python3
"""Fetch HL BTC-PERP 5m candles for last 60 days (1m capped by API)."""
import json, time, urllib.request

URL = "https://api.hyperliquid.xyz/info"
OUT = "/tmp/hl_study/e26_mm_research/btc_5m_candles.json"

now_ms = int(time.time() * 1000)
start = now_ms - 60 * 24 * 60 * 60 * 1000

# 5m: 5000 candles = ~17.3 days. Chunk at 15 days.
chunk_ms = 15 * 24 * 60 * 60 * 1000

all_candles = []
seen = set()
cur = start
i = 0
while cur < now_ms:
    end = min(cur + chunk_ms, now_ms)
    body = {"type":"candleSnapshot","req":{"coin":"BTC","interval":"5m","startTime":cur,"endTime":end}}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        arr = json.loads(r.read())
    new_ct = 0
    for c in arr:
        if c["t"] not in seen:
            seen.add(c["t"]); all_candles.append(c); new_ct += 1
    print(f"chunk {i}: returned {len(arr)} new {new_ct} total {len(all_candles)}")
    cur = end; i += 1; time.sleep(0.2)

all_candles.sort(key=lambda c: c["t"])
import datetime
print(f"total: {len(all_candles)}; first: {datetime.datetime.utcfromtimestamp(all_candles[0]['t']/1000).isoformat()}; last: {datetime.datetime.utcfromtimestamp(all_candles[-1]['t']/1000).isoformat()}")
with open(OUT,"w") as f: json.dump(all_candles,f)
