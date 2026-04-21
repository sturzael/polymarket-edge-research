"""Inspect actual Smarkets NBA market structure - why does sum != 1.0?"""
import httpx
SM_BASE = "https://api.smarkets.com/v3"

with httpx.Client(timeout=30) as c:
    # Toronto Raptors at Cleveland Cavaliers
    r = c.get(f"{SM_BASE}/events/", params={
        "type_domain":"basketball","state":"upcoming","limit":500,
        "sort":"start_datetime,id"})
    for e in r.json().get("events", []):
        if "Raptors" in e["name"] or "Timberwolves" in e["name"] or "Hawks" in e["name"]:
            print(f"\nevent: {e['name']}  id={e['id']}")
            ms = c.get(f"{SM_BASE}/events/{e['id']}/markets/").json().get("markets",[])
            for m in ms[:5]:
                print(f"  market id={m['id']}  name={m.get('name')!r}")
            # Pick the moneyline / winner market
            for m in ms:
                nm = (m.get("name") or "").lower()
                if "moneyline" in nm or "winner" in nm or "match odds" in nm or nm == "result":
                    print(f"  >>> looking at: {m.get('name')} ({m['id']})")
                    cts = c.get(f"{SM_BASE}/markets/{m['id']}/contracts/").json().get("contracts",[])
                    q = c.get(f"{SM_BASE}/markets/{m['id']}/quotes/").json()
                    for ct in cts:
                        cid = str(ct["id"])
                        qv = q.get(cid, {})
                        bids = qv.get("bids", [])
                        offers = qv.get("offers", [])
                        bb = bids[0]["price"] if bids else None
                        bo = offers[0]["price"] if offers else None
                        print(f"     contract {ct['name']!r}: bid={bb} offer={bo}")
                        # convert to prob
                        bbp = bb/10000 if bb else None
                        bop = bo/10000 if bo else None
                        print(f"        as prob: bid={bbp} offer={bop}  mid={(bbp+bop)/2 if bbp and bop else (bbp or bop)}")
                    # Also show last executed
                    lp = c.get(f"{SM_BASE}/markets/{m['id']}/last_executed_prices/").json()
                    print(f"     last executed: {lp}")
                    break
            break
