"""Smarkets 3-way orderbook — understand what fetch_order_book returns for
an H2H match with home/draw/away outcomes, and find the per-outcome book."""
import sys
print("starting", flush=True)
import httpx

# Smarkets public API docs: https://smarkets.com/api-docs/
# Endpoints are at api.smarkets.com/v3/

base = "https://api.smarkets.com/v3"

# Find live events (football)
with httpx.Client(timeout=30) as c:
    print("listing events...", flush=True)
    r = c.get(f"{base}/events/",
              params={"type": "football_match", "state": "upcoming", "limit": 5})
    print("status:", r.status_code, flush=True)
    if r.status_code != 200:
        print(r.text[:300]); sys.exit()
    data = r.json()
    events = data.get("events", [])
    print(f"n events: {len(events)}")
    if not events:
        print("no events")
        sys.exit()
    ev = events[0]
    print(f"\nevent: id={ev['id']}  name={ev['name']}  start={ev['start_datetime']}")
    # Get markets for this event
    ev_id = ev['id']
    r2 = c.get(f"{base}/events/{ev_id}/markets/", params={"limit":50})
    print(f"  markets status: {r2.status_code}")
    if r2.status_code == 200:
        ms = r2.json().get("markets", [])
        print(f"  n markets: {len(ms)}")
        for m in ms[:5]:
            print(f"    market_id={m['id']}  name={m.get('name','')[:50]}  "
                  f"type={m.get('type')}  n_contracts={m.get('contracts_count')}")
        # Drill into the h2h winner market
        for m in ms:
            if m.get("type") == "winner":
                # Get contracts (outcomes)
                r3 = c.get(f"{base}/markets/{m['id']}/contracts/")
                print(f"\n  market '{m['name']}' contracts:")
                if r3.status_code == 200:
                    contracts = r3.json().get("contracts", [])
                    for ct in contracts:
                        print(f"    contract_id={ct['id']}  name={ct['name']}")
                        # Quotes - this is the key question
                        r4 = c.get(f"{base}/markets/{m['id']}/quotes/")
                        if r4.status_code == 200:
                            q = r4.json()
                            # Per-contract quotes live here
                            contract_quotes = q.get("quotes", {}).get(str(m['id']), {}).get("contracts", {})
                            print(f"      quotes: {list(q.get('quotes', {}).keys())[:3]}")
                        break
                break

    # Also hit last-executed prices
    print("\n--- last executed prices ---")
    # Top-level: /prices/
    ids = ",".join([str(m['id']) for m in ms[:3]])
    r5 = c.get(f"{base}/markets/{ids}/last_executed_prices/")
    print(f"  /last_executed_prices status: {r5.status_code}")
    if r5.status_code == 200:
        print(f"  body[:500]: {r5.text[:500]}")
