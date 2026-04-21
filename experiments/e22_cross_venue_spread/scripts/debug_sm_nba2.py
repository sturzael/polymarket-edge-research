"""Which market's contracts did my script actually pick for NBA Raptors?"""
import httpx
SM_BASE = "https://api.smarkets.com/v3"
with httpx.Client(timeout=30) as c:
    r = c.get(f"{SM_BASE}/events/", params={
        "type_domain":"basketball","state":"upcoming","limit":500,
        "sort":"start_datetime,id"})
    for e in r.json().get("events", []):
        if "Raptors" in e["name"]:
            ms = c.get(f"{SM_BASE}/events/{e['id']}/markets/").json().get("markets",[])
            for m in ms:
                nm = (m.get("name") or "").lower()
                if ("moneyline" in nm or "match odds" in nm or nm=="winner"
                        or "full-time" in nm or "game winner" in nm or nm=="result"):
                    print(f"matched by my filter: {m['name']!r} (id={m['id']})")
            # and the actual winner-including-ot market I found
            for m in ms:
                if "winner" in (m.get("name","") or "").lower():
                    print(f"contains 'winner': {m['name']!r}")
            break
