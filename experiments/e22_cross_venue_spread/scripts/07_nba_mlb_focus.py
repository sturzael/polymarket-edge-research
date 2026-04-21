"""Focus on NBA + MLB matches specifically — those are the core sports in
e16's FLB sample."""
import json, re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import httpx, pandas as pd

DATA_DIR = Path(__file__).parent.parent / "data"
SM_BASE = "https://api.smarkets.com/v3"
PM_BASE = "https://gamma-api.polymarket.com"
STOP = set("vs v x at the will win beat game match won of a an on or new fc cf ca cd cup de sc sf la en 1 2".split())

def toks(s):
    if not s: return set()
    s = re.sub(r"\(.*?\)", " ", s.lower())
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return {t for t in s.split() if t not in STOP and len(t) >= 3}


def fetch_sm(type_d):
    with httpx.Client(timeout=30) as c:
        all_evs = []
        url = f"{SM_BASE}/events/"
        next_cursor = None
        for _ in range(10):
            params = {"type_domain":type_d,"state":"upcoming","limit":500,
                       "sort":"start_datetime,id"}
            if next_cursor:
                # Smarkets uses pagination via ?last_id or similar; try both
                params["last_id"] = next_cursor
            r = c.get(url, params=params)
            if r.status_code != 200: break
            data = r.json()
            batch = data.get("events", [])
            if not batch: break
            all_evs.extend(batch)
            # No reliable cursor; break after one page to avoid loop
            break
    now = datetime.now(timezone.utc)
    out = []
    for e in all_evs:
        try:
            st = datetime.fromisoformat(e["start_datetime"].replace("Z","+00:00"))
            out.append((e, st))
        except Exception:
            pass
    return out


def sm_mw(event_id, client):
    try:
        r = client.get(f"{SM_BASE}/events/{event_id}/markets/")
        if r.status_code != 200: return None
        for m in r.json().get("markets", []):
            nm = (m.get("name") or "").lower()
            if "moneyline" in nm or "match odds" in nm or nm == "winner" or "full-time" in nm or "game winner" in nm:
                cts = client.get(f"{SM_BASE}/markets/{m['id']}/contracts/").json().get("contracts", [])
                q = client.get(f"{SM_BASE}/markets/{m['id']}/quotes/").json()
                out = []
                for ct in cts:
                    cid = str(ct["id"])
                    qv = q.get(cid, {})
                    bb = qv.get("bids",[{}])[0].get("price") if qv.get("bids") else None
                    bo = qv.get("offers",[{}])[0].get("price") if qv.get("offers") else None
                    bb = bb/10000 if bb else None
                    bo = bo/10000 if bo else None
                    mid = (bb+bo)/2 if bb and bo else (bb or bo)
                    out.append({"contract_id":cid, "name":ct["name"],
                                "best_bid":bb, "best_offer":bo, "mid":mid})
                return {"market_id": m["id"], "market_name": m.get("name"),
                        "contracts": out}
    except Exception:
        return None
    return None


def pm_search(term, days_ahead=14):
    now = datetime.now(timezone.utc)
    end = now + pd.Timedelta(days=days_ahead)
    with httpx.Client(timeout=30) as c:
        out = []
        offset = 0
        while offset < 10000:
            r = c.get(f"{PM_BASE}/markets", params={
                "active":"true","closed":"false","archived":"false",
                "end_date_min": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end_date_max": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "order":"volume", "ascending":"false",
                "limit":500,"offset":offset})
            if r.status_code != 200 or not r.json(): break
            b = r.json()
            out.extend(b)
            if len(b) < 500: break
            offset += 500
        return out

def pm_yes(m):
    import json as _json
    try:
        labels = _json.loads(m.get("outcomes") or "[]")
        prices = _json.loads(m.get("outcomePrices") or "[]")
        for l, p in zip(labels, prices):
            if str(l).lower()=="yes": return float(p)
    except Exception:
        return None

def pm_team(q):
    m = re.match(r"^will\s+(.+?)\s+win", (q or "").lower(), re.IGNORECASE)
    return m.group(1).strip() if m else None

def pm_teams(t):
    parts = re.split(r"\s+vs\.?\s+|\s+v\s+", t or "", 1, re.IGNORECASE)
    return (parts[0].strip(), parts[1].strip()) if len(parts) == 2 else None


def main():
    # NBA & MLB on Smarkets
    print("fetching Smarkets basketball + baseball + ice_hockey + american_football + tennis events", flush=True)
    sm_all = []
    for td in ["basketball","baseball","ice_hockey","american_football","tennis"]:
        pairs = fetch_sm(td)
        print(f"  {td}: {len(pairs)}")
        sm_all.extend([(e, st, td) for e, st in pairs])
    now = datetime.now(timezone.utc)
    sm_near = []
    for e, st, td in sm_all:
        dh = (st - now).total_seconds() / 3600
        if 0 <= dh <= 336:
            sm_near.append((e, st, td))
    print(f"  total near-term non-football: {len(sm_near)}")

    sm_by_date = defaultdict(list)
    for e, st, td in sm_near:
        name = e.get("name","")
        parts = re.split(r"\s+vs\s+", name, 1)
        if len(parts) != 2: continue
        a, b = toks(parts[0]), toks(parts[1])
        if not a or not b: continue
        e["_a"], e["_b"], e["_ts"], e["_sport"] = a, b, st, td
        sm_by_date[st.strftime("%Y-%m-%d")].append(e)

    # PM sports markets — bias selection to NBA/MLB/NHL/tennis by keyword
    pm_all = pm_search("sports", 14)
    print(f"  PM near-term markets: {len(pm_all)}")

    KEYWORDS = ["NBA","nba","Lakers","Celtics","Knicks","Nuggets",
                "Spurs","Heat","Rockets","Kings","Thunder","Pacers",
                "Cavaliers","Warriors","Timberwolves","Hawks","76ers",
                "Bucks","Bulls","Clippers","Pistons","Raptors","Jazz",
                "Magic","Grizzlies","Pelicans","Nets","Mavericks",
                "Blazers","Wizards","Hornets",
                "MLB","mlb","Yankees","Astros","Dodgers","Cubs",
                "Braves","Phillies","Mets","Red Sox","Cardinals",
                "Rays","Tigers","Royals","Pirates","Orioles","Twins",
                "Marlins","Padres","Giants","Guardians","Reds",
                "NHL","nhl","Oilers","Rangers","Canadiens","Blackhawks",
                "Islanders","Sabres","Penguins","Flyers",
                "NFL","nfl","Steelers","Eagles","Patriots","Cowboys",
                "Bills","Chiefs","Bengals"]

    pm_h2h_target = []
    for m in pm_all:
        q = m.get("question","")
        ev = (m.get("events") or [{}])[0]
        et = ev.get("title","")
        if not any(kw in et for kw in KEYWORDS):
            continue
        if not q.lower().startswith("will ") or " win" not in q.lower() or "draw" in q.lower():
            continue
        if " vs." not in et and " vs " not in et:
            continue
        pm_h2h_target.append(m)
    print(f"  PM NBA/MLB/NHL/NFL h2h matches: {len(pm_h2h_target)}")

    # Match
    records = []
    cache = {}
    with httpx.Client(timeout=30) as sc:
        for m in pm_h2h_target:
            q = m.get("question","")
            ev = (m.get("events") or [{}])[0]
            et = ev.get("title","")
            pt = pm_teams(et)
            if not pt: continue
            pa_t, pb_t = toks(pt[0]), toks(pt[1])
            if not pa_t or not pb_t: continue
            pteam = pm_team(q)
            if not pteam: continue
            py = pm_yes(m)
            if py is None: continue
            try:
                dt = datetime.fromisoformat(m.get("endDate","").replace("Z","+00:00"))
            except:
                continue
            dk = dt.strftime("%Y-%m-%d")
            match = None
            for d in [dk, (dt-pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                       (dt+pd.Timedelta(days=1)).strftime("%Y-%m-%d")]:
                for e in sm_by_date.get(d, []):
                    if ((pa_t & e["_a"] and pb_t & e["_b"]) or
                            (pa_t & e["_b"] and pb_t & e["_a"])):
                        match = e; break
                if match: break
            if not match:
                continue
            mw = cache.get(match["id"])
            if mw is None:
                mw = sm_mw(str(match["id"]), sc)
                cache[match["id"]] = mw
            if not mw: continue
            pt_t = toks(pteam)
            sm_ct = None
            for c in mw["contracts"]:
                if toks(c["name"]) & pt_t and pt_t != {"draw"}:
                    sm_ct = c; break
            if not sm_ct or sm_ct["mid"] is None: continue
            records.append({
                "pm_question": q, "pm_event": et, "pm_team": pteam,
                "sport": match.get("_sport"),
                "pm_yes": py, "sm_mid": sm_ct["mid"],
                "sm_bid": sm_ct["best_bid"], "sm_offer": sm_ct["best_offer"],
                "spread": py - sm_ct["mid"],
                "pm_vol": float(m.get("volume") or 0),
                "pm_vol24h": float(m.get("volume24hr") or 0),
            })

    df = pd.DataFrame(records)
    df.to_parquet(DATA_DIR / "07_nba_mlb.parquet", index=False)
    print(f"\n{len(df)} matched pairs (NBA/MLB/NHL/NFL)")
    if len(df):
        print(df[["pm_team","sport","pm_yes","sm_mid","spread","pm_vol"]].to_string())
        print(f"\nmean spread: {df['spread'].mean():+.4f}  "
              f"median: {df['spread'].median():+.4f}  "
              f"stdev: {df['spread'].std():.4f}")
        # Bucket
        df["bucket"] = (df["pm_yes"] * 20).astype(int) / 20
        print("\nby bucket:")
        for b, g in df.groupby("bucket"):
            print(f"  {b:.2f}-{b+0.05:.2f}: n={len(g)}  "
                  f"pm={g['pm_yes'].mean():.3f} sm={g['sm_mid'].mean():.3f} "
                  f"sp={g['spread'].mean():+.4f}")

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_matched": int(len(df)),
        "sports_in_sample": (df["sport"].value_counts().to_dict() if len(df) else {}),
    }
    if len(df):
        summary["spread_stats"] = {
            "mean": round(float(df["spread"].mean()), 4),
            "median": round(float(df["spread"].median()), 4),
            "stdev": round(float(df["spread"].std()), 4),
            "abs_mean": round(float(df["spread"].abs().mean()), 4),
        }
    (DATA_DIR / "07_summary.json").write_text(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
