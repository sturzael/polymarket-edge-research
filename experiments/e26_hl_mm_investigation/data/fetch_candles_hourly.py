#!/usr/bin/env python3
"""Fetch HL BTC 15m + 1h candles for last 60 days."""
import json, time, urllib.request, datetime

URL = "https://api.hyperliquid.xyz/info"

now_ms = int(time.time() * 1000)
start_60d = now_ms - 60 * 24 * 60 * 60 * 1000

def fetch(interval, chunk_days):
    chunk_ms = chunk_days * 24 * 60 * 60 * 1000
    all_c = []; seen=set(); cur=start_60d; i=0
    while cur < now_ms:
        end = min(cur + chunk_ms, now_ms)
        body = {"type":"candleSnapshot","req":{"coin":"BTC","interval":interval,"startTime":cur,"endTime":end}}
        req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            arr = json.loads(r.read())
        for c in arr:
            if c["t"] not in seen: seen.add(c["t"]); all_c.append(c)
        print(f"{interval} chunk {i}: {len(arr)} new total {len(all_c)}")
        cur = end; i += 1; time.sleep(0.2)
    all_c.sort(key=lambda c:c["t"])
    return all_c

for intv, days in [("15m", 50), ("1h", 200), ("4h", 400)]:
    c = fetch(intv, days)
    if c:
        print(f"{intv}: {len(c)} candles {datetime.datetime.utcfromtimestamp(c[0]['t']/1000).isoformat()} -> {datetime.datetime.utcfromtimestamp(c[-1]['t']/1000).isoformat()}")
    with open(f"/tmp/hl_study/e26_mm_research/btc_{intv}_candles.json","w") as f:
        json.dump(c,f)
