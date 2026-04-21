"""Probe Polymarket gamma /markets structure."""
import httpx, json

PM_BASE = "https://gamma-api.polymarket.com"

with httpx.Client(timeout=30) as c:
    r = c.get(f"{PM_BASE}/markets", params={
        "active": "true", "closed": "false", "archived": "false",
        "end_date_min": "2026-04-20T00:00:00Z",
        "end_date_max": "2026-04-27T00:00:00Z",
        "order": "volume",
        "ascending": "false",
        "limit": 5,
    })
    data = r.json()
    print(f"n markets returned: {len(data)}")
    for m in data[:3]:
        print(f"\n--- market ---")
        print(f"  question: {m.get('question', '')[:80]}")
        print(f"  slug: {m.get('slug')}")
        print(f"  endDate: {m.get('endDate')}")
        print(f"  outcomes: {m.get('outcomes')}")
        print(f"  outcomePrices: {m.get('outcomePrices')}")
        print(f"  volume: {m.get('volume')}  volume24hr: {m.get('volume24hr')}")
        print(f"  category: {m.get('category')}")
        tags = m.get("tags")
        print(f"  tags type: {type(tags)}")
        if isinstance(tags, list):
            print(f"  tags: {tags[:5]}")
        # Events?
        evs = m.get("events")
        if evs:
            print(f"  events[0]: title={evs[0].get('title')}  slug={evs[0].get('slug')}")
            print(f"    event tags: {[t.get('label') for t in (evs[0].get('tags') or [])]}")
