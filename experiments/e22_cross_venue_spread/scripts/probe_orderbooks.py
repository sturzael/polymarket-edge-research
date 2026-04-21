"""Probe orderbook structures on each venue."""
import pmxt

print("=== Smarkets ===")
c = pmxt.Smarkets()
ms = c.fetch_markets()
shown = 0
for m in ms:
    if m.category == 'football' and 'premier' in (m.title or '').lower():
        print('title:', repr(m.title), 'cat:', m.category, 'id:', m.market_id)
        try:
            ob = c.fetch_order_book(m.market_id)
            print('  bids[:5]:', ob.bids[:5])
            print('  asks[:5]:', ob.asks[:5])
        except Exception as e:
            print('err:', e)
        shown += 1
        if shown >= 3:
            break

print("\n=== Polymarket ===")
p = pmxt.Polymarket()
for m in p.fetch_markets():
    if m.category == 'Sports' and 'nba' in (m.title or '').lower() and m.volume_24h and m.volume_24h > 10000:
        print('pm title:', m.title)
        print('  outcomes:', [(o.label, o.price) for o in m.outcomes])
        try:
            ob = p.fetch_order_book(m.market_id)
            print('  bids[:3]:', ob.bids[:3])
            print('  asks[:3]:', ob.asks[:3])
        except Exception as e:
            print('err:', e)
        break

print("\n=== Kalshi ===")
k = pmxt.Kalshi()
ms = k.fetch_markets()
for m in ms:
    if m.category == 'Sports' and m.volume_24h and m.volume_24h > 0 and 'nhl' in (m.title or '').lower():
        print('k title:', m.title, 'vol24h:', m.volume_24h)
        print('  outcomes:', [(o.label, o.price) for o in m.outcomes])
        try:
            ob = k.fetch_order_book(m.market_id)
            print('  bids[:3]:', ob.bids[:3])
            print('  asks[:3]:', ob.asks[:3])
        except Exception as e:
            print('err:', e)
        break
# Also peek at high-volume kalshi sports
print()
hi_vol = sorted([m for m in ms if m.category == 'Sports' and m.volume_24h],
                key=lambda x: -x.volume_24h)[:10]
print("top 10 kalshi sports by vol24h:")
for m in hi_vol:
    print(f"  vol24h={m.volume_24h:>10.0f}  title={m.title!r}")
