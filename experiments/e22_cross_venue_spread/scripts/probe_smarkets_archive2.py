"""Try Smarkets various state values + explicit date range for archive."""
import httpx

base = "https://api.smarkets.com/v3"

with httpx.Client(timeout=30) as c:
    # Recently resolved: state can be new, upcoming, live, completed, cancelled
    for state in ["live", "completed", "cancelled", "finished", "closed"]:
        r = c.get(f"{base}/events/",
                   params={"type":"football_match","state":state,"limit":3,
                            "sort":"start_datetime,id"})
        print(f"state={state}: {r.status_code}")
        if r.status_code == 200:
            d = r.json()
            print(f"  {len(d.get('events',[]))} events; sample: "
                  f"{[e['name'] for e in d.get('events',[])][:3]}")

    # Check docs-implied enumeration: all states w/ no filter
    print("\n--- no state filter, date range in the past ---")
    r = c.get(f"{base}/events/", params={
        "type": "football_match",
        "start_datetime_min": "2026-04-18T00:00:00Z",
        "start_datetime_max": "2026-04-19T23:59:59Z",
        "limit": 10, "sort": "start_datetime,id",
    })
    print(f"  status: {r.status_code}")
    if r.status_code == 200:
        for e in r.json().get("events", [])[:3]:
            print(f"    {e['name']}  start={e['start_datetime']} state={e.get('state')}")

    # Try using last_executed_prices — past events still have them
    # First, find a past event from the live upcoming list that may have played recently
    print("\n--- past-event probe via recent events ---")
    r = c.get(f"{base}/events/", params={
        "type": "football_match",
        "state": "upcoming",  # API may return state upcoming for anything not yet settled
        "start_datetime_min": "2026-04-17T00:00:00Z",
        "start_datetime_max": "2026-04-20T00:00:00Z",
        "limit": 10, "sort": "start_datetime,id",
    })
    print(f"  status: {r.status_code}")
    if r.status_code == 200:
        evs = r.json().get("events", [])
        print(f"  {len(evs)} events")
        for e in evs[:3]:
            print(f"    {e['name']}  start={e['start_datetime']}  state={e.get('state')}")

    # Historical trades: direct trades endpoint
    print("\n--- historical trades endpoint ---")
    r = c.get(f"{base}/trades/", params={
        "event_id": "44754796",  # any event
        "limit": 5,
    })
    print(f"  status: {r.status_code}  body: {r.text[:200]}")

    # Price history endpoint
    print("\n--- price history endpoint for a known market ---")
    for ep in ["/prices/", "/price_history/", "/history/"]:
        r = c.get(f"{base}/markets/119416335{ep}",
                  params={"limit": 5, "aggregation": "hour"})
        print(f"  {ep}: {r.status_code}: {r.text[:200]}")
