"""Why don't NBA/MLB PM markets match Smarkets?"""
import re
from collections import defaultdict
from datetime import datetime, timezone
import httpx, pandas as pd

SM_BASE = "https://api.smarkets.com/v3"
PM_BASE = "https://gamma-api.polymarket.com"

with httpx.Client(timeout=30) as c:
    # Get Smarkets basketball events
    r = c.get(f"{SM_BASE}/events/", params={"type_domain":"basketball",
        "state":"upcoming","limit":500,"sort":"start_datetime,id"})
    bb = r.json().get("events", [])
    now = datetime.now(timezone.utc)
    bb_near = []
    for e in bb:
        try:
            st = datetime.fromisoformat(e["start_datetime"].replace("Z","+00:00"))
            if 0 <= (st-now).total_seconds()/3600 <= 336:
                bb_near.append((e, st))
        except Exception: pass
    print(f"Smarkets basketball events: {len(bb_near)}")
    for e, st in bb_near[:20]:
        print(f"  {e['name']!r}  start={st}")
    # Baseball
    r = c.get(f"{SM_BASE}/events/", params={"type_domain":"baseball",
        "state":"upcoming","limit":500,"sort":"start_datetime,id"})
    mlb = r.json().get("events", [])
    print(f"\nSmarkets baseball events: {len(mlb)}")
    for e in mlb[:10]:
        print(f"  {e['name']!r}  start={e['start_datetime']}")

    # PM NBA matches
    now = datetime.now(timezone.utc)
    end = now + pd.Timedelta(days=14)
    r = c.get(f"{PM_BASE}/markets", params={
        "active":"true","closed":"false","archived":"false",
        "end_date_min": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end_date_max": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "order":"volume","ascending":"false","limit":500,"offset":0})
    pm = r.json()
    nba_pm = []
    for m in pm:
        ev = (m.get("events") or [{}])[0]
        et = ev.get("title","")
        q = m.get("question","")
        # NBA teams
        if any(t in et for t in ["Lakers","Celtics","Knicks","Nuggets","Spurs",
                                   "Heat","Rockets","Suns","Thunder","Pacers",
                                   "Cavaliers","Warriors","Timberwolves","Hawks",
                                   "76ers","Bucks"]):
            nba_pm.append((q, et, m.get("endDate")))
    print(f"\nPM NBA markets: {len(nba_pm)}")
    for q, et, ed in nba_pm[:10]:
        print(f"  event: {et}  end: {ed}")
        print(f"    q: {q[:70]}")
