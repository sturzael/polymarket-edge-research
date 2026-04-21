"""Try the main Kalshi API (not elections-specific)."""
import sys
print("starting", flush=True)
import httpx

# Main Kalshi trading API (as distinct from elections subdomain)
for base in [
    "https://trading-api.kalshi.com/trade-api/v2",
    "https://api.kalshi.com/trade-api/v2",
]:
    print(f"\n=== {base} ===", flush=True)
    try:
        with httpx.Client(timeout=15) as c:
            r = c.get(f"{base}/markets", params={"series_ticker":"KXNBAGAME",
                                                   "status":"open","limit":3})
            print(f"  /markets status: {r.status_code}", flush=True)
            if r.status_code == 200:
                ms = r.json().get("markets", [])
                for m in ms[:2]:
                    print(f"  ticker={m.get('ticker')} "
                          f"yes_bid={m.get('yes_bid')} yes_ask={m.get('yes_ask')} "
                          f"last={m.get('last_price')}")
                    # Try orderbook
                    t = m["ticker"]
                    r2 = c.get(f"{base}/markets/{t}/orderbook", params={"depth": 3})
                    print(f"  orderbook status: {r2.status_code}")
                    if r2.status_code == 200:
                        ob = r2.json().get("orderbook", {})
                        print(f"    yes: {ob.get('yes')}")
                        print(f"    no: {ob.get('no')}")
                    else:
                        print(f"    body: {r2.text[:200]}")
    except Exception as e:
        print(f"  ERR: {e}")

# Also try archived price endpoint on elections
print("\n=== try candlestick endpoint ===", flush=True)
base = "https://api.elections.kalshi.com/trade-api/v2"
ticker = "KXNBAGAME-26APR25OKCPHX-PHX"
with httpx.Client(timeout=15) as c:
    # Candlesticks
    r = c.get(f"{base}/markets/{ticker}/candlesticks", params={
        "start_ts": 1745027400 - 3600,
        "end_ts":   1745027400,
        "period_interval": 60,
    })
    print(f"  candlesticks status: {r.status_code}")
    if r.status_code == 200:
        d = r.json()
        print(f"  keys: {list(d.keys())}")
        print(f"  n candlesticks: {len(d.get('candlesticks', []))}")
        if d.get("candlesticks"):
            print(f"  first: {d['candlesticks'][0]}")
    else:
        print(f"  body: {r.text[:200]}")
