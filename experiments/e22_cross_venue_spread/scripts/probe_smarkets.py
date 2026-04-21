"""Probe Smarkets fetch_market for real prices."""
import pmxt

c = pmxt.Smarkets()
ms = c.fetch_markets()
# Find a near-term football, try fetch_market to see if prices populate
near_term_fb = [m for m in ms if m.category == 'football'
                and m.resolution_date is not None][:5]
for m in near_term_fb:
    try:
        full = c.fetch_market(m.market_id)
        print("=" * 70)
        print("title:", full.title)
        print("outcomes:", [(o.label, o.price) for o in full.outcomes])
        print("yes:", full.yes)
        print("status:", full.status)
        print("rdate:", full.resolution_date)
        print("vol24h:", full.volume_24h, "liq:", full.liquidity)
    except Exception as e:
        print("err on", m.market_id, ":", e)

# Also try order book
print("\n--- order book test ---")
for m in near_term_fb[:2]:
    try:
        ob = c.fetch_order_book(m.market_id)
        print("market:", m.title)
        print("ob type:", type(ob), "attrs:", [a for a in dir(ob) if not a.startswith("_")])
        print("  best bids:", ob.bids[:3] if hasattr(ob, "bids") else "no bids")
        print("  best asks:", ob.asks[:3] if hasattr(ob, "asks") else "no asks")
    except Exception as e:
        print("ob err:", e)
