"""Understand PM NBA game-winner market structure."""
import httpx, json
from datetime import datetime, timezone
import pandas as pd
PM_BASE = "https://gamma-api.polymarket.com"

with httpx.Client(timeout=30) as c:
    now = datetime.now(timezone.utc)
    end = now + pd.Timedelta(days=14)
    r = c.get(f"{PM_BASE}/markets", params={
        "active":"true","closed":"false","archived":"false",
        "end_date_min": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end_date_max": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "order":"volume","ascending":"false","limit":500,"offset":0})
    pm = r.json()

    # Focus on "Timberwolves vs. Nuggets" event
    print("markets in the Timberwolves vs. Nuggets event:")
    for m in pm:
        ev = (m.get("events") or [{}])[0]
        if "Timberwolves vs. Nuggets" in ev.get("title",""):
            q = m.get("question","")
            print(f"  question: {q}")
            print(f"    slug: {m.get('slug')}")
            print(f"    outcomes: {m.get('outcomes')}")
            print(f"    outcomePrices: {m.get('outcomePrices')}")
            print(f"    groupItemTitle: {m.get('groupItemTitle')}")
            print()
