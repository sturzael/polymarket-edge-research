"""Try Kalshi's public REST API directly."""
import httpx, json

# Public endpoints (no auth needed) per Kalshi v2 API docs
base = "https://api.elections.kalshi.com/trade-api/v2"

# List markets - public
with httpx.Client(timeout=30) as client:
    # sports markets active
    print("--- GET /markets?series_ticker=KXNBA ---")
    r = client.get(f"{base}/markets", params={"series_ticker": "KXNBAGAME",
                                               "status": "open", "limit": 10})
    print("status:", r.status_code)
    if r.status_code == 200:
        data = r.json()
        print("keys:", list(data.keys()))
        ms = data.get("markets", [])
        print(f"n markets: {len(ms)}")
        for m in ms[:5]:
            print(f"  ticker={m.get('ticker')}  title={m.get('title','')[:50]}")
            print(f"    yes_bid={m.get('yes_bid')}  yes_ask={m.get('yes_ask')}  "
                  f"last_price={m.get('last_price')}  status={m.get('status')}")
    else:
        print(r.text[:300])

    # Try NHL
    print("\n--- GET /markets?series_ticker=KXNHLGAME ---")
    r = client.get(f"{base}/markets", params={"series_ticker": "KXNHLGAME",
                                               "status": "open", "limit": 10})
    print("status:", r.status_code)
    if r.status_code == 200:
        data = r.json()
        for m in data.get("markets", [])[:5]:
            print(f"  ticker={m.get('ticker')}  title={m.get('title','')[:60]}")
            print(f"    yes_bid={m.get('yes_bid')}  yes_ask={m.get('yes_ask')}  "
                  f"vol24h={m.get('volume_24h')}")

    # MLB
    print("\n--- GET /markets?series_ticker=KXMLBGAME ---")
    r = client.get(f"{base}/markets", params={"series_ticker": "KXMLBGAME",
                                               "status": "open", "limit": 10})
    print("status:", r.status_code)
    if r.status_code == 200:
        data = r.json()
        for m in data.get("markets", [])[:5]:
            print(f"  ticker={m.get('ticker')}  title={m.get('title','')[:60]}")
            print(f"    yes_bid={m.get('yes_bid')}  yes_ask={m.get('yes_ask')}  "
                  f"vol24h={m.get('volume_24h')}")

    # List all series tickers
    print("\n--- GET /series (list all) ---")
    r = client.get(f"{base}/series", params={"include_product_metadata": "false",
                                              "limit": 100})
    if r.status_code == 200:
        data = r.json()
        series = data.get("series", [])
        sports_ser = [s for s in series if "sport" in (s.get("category","") or "").lower()
                       or s.get("ticker","").startswith("KX") and any(x in s.get("ticker","") for x in ("NBA","NFL","MLB","NHL","UFC","GAME"))]
        print(f"n sports series: {len(sports_ser)}")
        for s in sports_ser[:20]:
            print(f"  ticker={s.get('ticker')}  cat={s.get('category')}  title={s.get('title','')[:50]}")
