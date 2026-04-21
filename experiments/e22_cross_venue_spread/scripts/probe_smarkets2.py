"""Probe Smarkets market structure: are H2H 3-outcome markets really a
single market, or three binary markets?"""
import pmxt

c = pmxt.Smarkets()
ms = c.fetch_markets()
# Find a "vs" match with H2H-looking outcomes
for m in ms:
    if (m.category == 'football' and ' vs ' in m.title.lower()
            and len(m.outcomes) == 3
            and 'Draw' in [o.label for o in m.outcomes]):
        print(f"Market: {m.title!r}")
        print(f"  market_id: {m.market_id}")
        print(f"  outcomes: {[(o.label, o.outcome_id, o.market_id, o.price) for o in m.outcomes]}")
        # Try fetching order book by market_id
        try:
            ob = c.fetch_order_book(m.market_id)
            print(f"  ob by market_id: bids={ob.bids[:2]} asks={ob.asks[:2]}")
        except Exception as e:
            print(f"  ob by market_id ERR: {e}")
        # Try by outcome_id of first outcome
        o = m.outcomes[0]
        try:
            ob = c.fetch_order_book(o.outcome_id)
            print(f"  ob by outcome_id {o.outcome_id}: bids={ob.bids[:2]} asks={ob.asks[:2]}")
        except Exception as e:
            print(f"  ob by outcome_id ERR: {e}")
        # Try using the contract/sub-market id
        if o.metadata:
            print(f"  outcome metadata: {o.metadata}")
        break

print("\n--- Now check a 2-outcome Smarkets market ---")
for m in ms:
    if (m.category == 'football' and ' vs ' in m.title.lower()
            and len(m.outcomes) == 2):
        print(f"Market: {m.title!r}")
        print(f"  market_id: {m.market_id}")
        print(f"  outcomes: {[(o.label, o.outcome_id, o.price) for o in m.outcomes]}")
        try:
            ob = c.fetch_order_book(m.market_id)
            print(f"  ob by market_id: bids={ob.bids[:2]} asks={ob.asks[:2]}")
        except Exception as e:
            print(f"  ob by market_id ERR: {e}")
        break
