"""Can we pull historical (resolved) Smarkets markets for retrospective
calibration? pmxt's archive or Smarkets' own resolved endpoint?"""
import httpx

base = "https://api.smarkets.com/v3"

with httpx.Client(timeout=30) as c:
    # Try state=resolved
    r = c.get(f"{base}/events/",
              params={"type": "football_match", "state": "resolved",
                       "limit": 10, "sort": "start_datetime,id"})
    print(f"state=resolved: {r.status_code}")
    if r.status_code == 200:
        evs = r.json().get("events", [])
        print(f"  got {len(evs)} events")
        for e in evs[:3]:
            print(f"    {e['name']}  start={e['start_datetime']}  state={e.get('state')}")
            print(f"      id={e['id']}")

    # Try state=settled
    r = c.get(f"{base}/events/",
              params={"type": "football_match", "state": "settled",
                       "limit": 10, "sort": "start_datetime,id"})
    print(f"\nstate=settled: {r.status_code}")
    if r.status_code == 200:
        evs = r.json().get("events", [])
        print(f"  got {len(evs)} events")
        for e in evs[:3]:
            print(f"    {e['name']}  state={e.get('state')}")

    # Trade history for a market
    print("\n--- historical trades for past market ---")
    # Try known past market
    # First get a list of past events
    r = c.get(f"{base}/events/",
              params={"type": "football_match", "state": "settled",
                       "limit": 1, "sort": "start_datetime,id"})
    if r.status_code == 200 and r.json().get("events"):
        ev = r.json()["events"][0]
        print(f"  sample past event: {ev['name']}")
        ms = c.get(f"{base}/events/{ev['id']}/markets/").json().get("markets",[])
        for m in ms[:1]:
            mid = m["id"]
            print(f"  market {mid}: {m.get('name')}")
            # Try historical orderbook snapshots
            for ep in ["/last_executed_prices/", "/volume/",
                        "/trades/", "/historical_volumes/"]:
                try:
                    r2 = c.get(f"{base}/markets/{mid}{ep}", params={"limit":5})
                    print(f"    {ep} -> {r2.status_code}: {r2.text[:200]}")
                except Exception as e:
                    print(f"    {ep} ERR: {e}")
