"""Try Kalshi orderbook endpoint without auth."""
import sys
print("starting probe", flush=True)
import httpx
base = "https://api.elections.kalshi.com/trade-api/v2"

with httpx.Client(timeout=30) as c:
    # Get an active NBA ticker
    print("requesting markets list...", flush=True)
    r = c.get(f"{base}/markets", params={"series_ticker":"KXNBAGAME","status":"open","limit":5})
    print("status:", r.status_code, flush=True)
    ms = r.json().get("markets", [])
    print(f"got {len(ms)} markets", flush=True)
    for m in ms:
        ticker = m.get("ticker")
        title = m.get("title","")[:60]
        print(f"\nticker={ticker}  title={title}")
        # All top-level fields
        print(f"  yes_bid={m.get('yes_bid')} yes_ask={m.get('yes_ask')}  "
              f"last={m.get('last_price')} status={m.get('status')} "
              f"vol={m.get('volume')} vol24h={m.get('volume_24h')} open_interest={m.get('open_interest')}")
        # Try orderbook endpoint
        r2 = c.get(f"{base}/markets/{ticker}/orderbook")
        print(f"  orderbook status {r2.status_code}")
        if r2.status_code == 200:
            d = r2.json()
            print(f"    keys: {list(d.keys())}")
            if "orderbook" in d:
                ob = d["orderbook"]
                print(f"    yes: {ob.get('yes', [])[:3]}")
                print(f"    no: {ob.get('no', [])[:3]}")
        else:
            print(f"    body: {r2.text[:300]}")

    # Also try single market endpoint
    if ms:
        t = ms[0]["ticker"]
        print(f"\n--- GET /markets/{t} ---")
        r3 = c.get(f"{base}/markets/{t}")
        if r3.status_code == 200:
            d = r3.json().get("market", {})
            print("  fields:", {k: v for k, v in d.items() if k in
                                 ("yes_bid","yes_ask","last_price","volume",
                                  "volume_24h","open_interest","status","close_time")})
