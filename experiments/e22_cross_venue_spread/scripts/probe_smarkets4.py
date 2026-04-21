"""Smarkets: get a per-contract live quote (bid/offer) via v3 API."""
import httpx

base = "https://api.smarkets.com/v3"

with httpx.Client(timeout=30) as c:
    # Find active premier league football events
    r = c.get(f"{base}/events/",
              params={"type": "football_match", "state": "upcoming", "limit": 50})
    evs = r.json().get("events", [])
    # Find one with near-term start (~within 1 week)
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc)
    for ev in evs:
        try:
            start = datetime.datetime.fromisoformat(ev["start_datetime"].replace("Z","+00:00"))
            delta = (start - now).total_seconds() / 3600
        except Exception:
            continue
        if 0 < delta < 48:
            print(f"event {ev['id']}  {ev['name']}  starts in {delta:.1f}h")
            # Markets for this event
            ms = c.get(f"{base}/events/{ev['id']}/markets/").json().get("markets", [])
            # Find Full-time result
            for m in ms:
                if "Full-time" in m.get("name", "") or m.get("name", "").lower().startswith("match odds") or m.get("name","").lower() == "winner":
                    print(f"  market {m['id']}: {m['name']}")
                    # Contracts
                    cts = c.get(f"{base}/markets/{m['id']}/contracts/").json().get("contracts", [])
                    print(f"    contracts: {[(ct['id'], ct['name']) for ct in cts]}")
                    # Quotes endpoint
                    qr = c.get(f"{base}/markets/{m['id']}/quotes/")
                    print(f"    quotes status: {qr.status_code}")
                    if qr.status_code == 200:
                        qd = qr.json()
                        print(f"      top-level keys: {list(qd.keys())}")
                        # Typical structure: {"quotes": {"market_id": {"bids":[...], "offers":[...]}}}
                        print(f"      quotes body sample: {str(qd)[:800]}")
                    # Also last executed
                    lp = c.get(f"{base}/markets/{m['id']}/last_executed_prices/")
                    print(f"    last exec: {lp.text[:400]}")
                    break
            break
