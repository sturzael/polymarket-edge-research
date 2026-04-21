"""Probe Kalshi: do individual fetch_market or fetch_order_book calls
populate live prices where fetch_markets() shows 0?"""
import pmxt

k = pmxt.Kalshi()
ms = k.fetch_markets()
print(f"total markets: {len(ms)}")

# Find sports markets resolving within 7 days
import pandas as pd
from datetime import datetime, timezone, timedelta
now = pd.Timestamp(datetime.now(timezone.utc))

def within_days(rd, days):
    if rd is None: return False
    try:
        r = pd.Timestamp(rd)
        if r.tz is None: r = r.tz_localize("UTC")
        return -2 <= (r - now).total_seconds() / 86400 <= days
    except Exception: return False

# Kalshi sports categories to check
cats_seen = {}
near_sports = []
for m in ms:
    cat = (m.category or "")
    tags = m.tags or []
    if "Sports" in cat or any("port" in t or "ball" in t or "NBA" in t or "NFL" in t for t in tags):
        cats_seen[cat] = cats_seen.get(cat, 0) + 1
        if within_days(m.resolution_date, 7):
            near_sports.append(m)
print(f"cats_seen: {cats_seen}")
print(f"near-term sports: {len(near_sports)}")

# Check a few
for m in near_sports[:10]:
    print(f"  title={m.title[:60]!r} rdate={m.resolution_date} vol24h={m.volume_24h} outs={[(o.label,o.price) for o in m.outcomes[:2]]}")

# Try fetch_market and fetch_order_book on one
if near_sports:
    m = near_sports[0]
    print(f"\n--- fetch_market({m.market_id}) ---")
    try:
        full = k.fetch_market(m.market_id)
        print(f"  vol24h={full.volume_24h}  outcomes={[(o.label,o.price) for o in full.outcomes]}")
    except Exception as e:
        print(f"  ERR: {e}")
    print(f"--- fetch_order_book({m.market_id}) ---")
    try:
        ob = k.fetch_order_book(m.market_id)
        print(f"  bids: {ob.bids[:3]}")
        print(f"  asks: {ob.asks[:3]}")
    except Exception as e:
        print(f"  ERR: {e}")

# Also try Kalshi's own events API to get NBA games
print("\n--- fetch_events ---")
try:
    events = k.fetch_events()
    print(f"n events: {len(events)}")
    # Show a few sports events
    ev_sports = [e for e in events if e.category and "Sports" in e.category]
    print(f"n sports events: {len(ev_sports)}")
    for e in ev_sports[:5]:
        print(f"  {e.title[:60]!r}  n_markets={len(e.markets)}")
except Exception as e:
    print(f"  ERR: {e}")
