"""US sports sweep: NBA, MLB, NHL, NFL — match PM game-winner markets
(outcomes are team names) to Smarkets moneyline markets."""
from __future__ import annotations
import json, re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import httpx, pandas as pd

DATA_DIR = Path(__file__).parent.parent / "data"
SM_BASE = "https://api.smarkets.com/v3"
PM_BASE = "https://gamma-api.polymarket.com"
STOP = set("vs v x at the will win beat game match won of a an on or new fc cf ca cd cup de sc sf la en 1 2 1st 2nd 3rd".split())

def toks(s):
    if not s: return set()
    s = re.sub(r"\(.*?\)", " ", s.lower())
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return {t for t in s.split() if t not in STOP and len(t) >= 3}

def fetch_sm_by_type(type_d, hours=336):
    with httpx.Client(timeout=30) as c:
        r = c.get(f"{SM_BASE}/events/", params={
            "type_domain":type_d,"state":"upcoming","limit":500,
            "sort":"start_datetime,id"})
        if r.status_code != 200: return []
        evs = r.json().get("events", [])
    now = datetime.now(timezone.utc)
    out = []
    for e in evs:
        try:
            st = datetime.fromisoformat(e["start_datetime"].replace("Z","+00:00"))
            dh = (st-now).total_seconds()/3600
            if 0 <= dh <= hours:
                e["_ts"] = st
                out.append(e)
        except Exception: pass
    return out

def sm_mw(event_id, client):
    """Find the primary 'match winner' market for an event (2-way or 3-way).
    Prefer exact names like 'Winner', 'Winner (including overtime)',
    'Full-time result', 'Moneyline', 'Match odds'. Reject parlay markets
    that combine winner with another condition (e.g. 'winner and over/under')."""
    try:
        r = client.get(f"{SM_BASE}/events/{event_id}/markets/")
        if r.status_code != 200: return None
        ms = r.json().get("markets", [])
        preferred = [
            "winner (including overtime)",
            "winner",
            "match odds",
            "moneyline",
            "full-time result",
            "result",
            "game winner",
        ]
        picked = None
        for p in preferred:
            for m in ms:
                nm = (m.get("name") or "").strip().lower()
                if nm == p:
                    picked = m; break
            if picked: break
        # Fallback: a name starting with "winner " or "match odds"
        if picked is None:
            for m in ms:
                nm = (m.get("name") or "").strip().lower()
                if (nm.startswith("winner (") and "over/under" not in nm and
                        "handicap" not in nm and "spread" not in nm and
                        "points" not in nm and "no. goals" not in nm):
                    picked = m; break
        if picked is None:
            return None
        m = picked
        cts = client.get(f"{SM_BASE}/markets/{m['id']}/contracts/").json().get("contracts", [])
        q = client.get(f"{SM_BASE}/markets/{m['id']}/quotes/").json()
        out = []
        for ct in cts:
            cid = str(ct["id"])
            qv = q.get(cid, {})
            bids = qv.get("bids", [])
            offers = qv.get("offers", [])
            bb = bids[0]["price"]/10000 if bids else None
            bo = offers[0]["price"]/10000 if offers else None
            mid = (bb+bo)/2 if bb and bo else (bb or bo)
            out.append({"contract_id":cid,"name":ct["name"],
                        "best_bid":bb,"best_offer":bo,"mid":mid})
        return {"market_id":m["id"],"market_name":m.get("name"),"contracts":out}
    except Exception:
        return None
    return None


def pm_pull(days=14):
    now = datetime.now(timezone.utc)
    end = now + pd.Timedelta(days=days)
    out = []
    with httpx.Client(timeout=30) as c:
        off = 0
        while off < 30000:
            r = c.get(f"{PM_BASE}/markets", params={
                "active":"true","closed":"false","archived":"false",
                "end_date_min": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end_date_max": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "order":"volume","ascending":"false","limit":500,"offset":off})
            if r.status_code != 200: break
            b = r.json()
            if not b: break
            out.extend(b)
            if len(b) < 500: break
            off += 500
    return out


def pm_extract_teams_and_prices(m):
    """For US sports game-winner markets, outcomes are ["TeamA","TeamB"].
    For football binary markets, outcomes are ["Yes","No"]."""
    import json as _json
    try:
        labels = _json.loads(m.get("outcomes") or "[]")
        prices = _json.loads(m.get("outcomePrices") or "[]")
    except Exception:
        return None
    q = (m.get("question") or "").lower()
    ev = (m.get("events") or [{}])[0]
    et = ev.get("title","")

    # Reject clear non-winner markets
    if any(b in q for b in ["o/u", "over/under", "spread", "total", "points",
                              "rebounds", "assists", "goals scored", "draw"]):
        return None

    if labels == ["Yes", "No"]:
        # binary "Will X win" - use q
        m_r = re.match(r"^will\s+(.+?)\s+win", q, re.IGNORECASE)
        if not m_r: return None
        team = m_r.group(1).strip()
        yes_price = float(prices[0]) if prices else None
        return [(team, yes_price)]
    elif len(labels) == 2:
        # Team A / Team B format
        team_a, team_b = labels[0], labels[1]
        pa, pb = float(prices[0]), float(prices[1])
        return [(team_a, pa), (team_b, pb)]
    return None


def pm_teams_from_et(t):
    parts = re.split(r"\s+vs\.?\s+|\s+v\s+|\s+at\s+", t or "", 1, re.IGNORECASE)
    return (parts[0].strip(), parts[1].strip()) if len(parts) == 2 else None


def main():
    # SM events for US sports (basketball incl Euro + NBA; baseball; ice_hockey; american_football)
    print("fetching Smarkets events (US sports)", flush=True)
    sm_all = []
    for td in ["basketball","baseball","ice_hockey","american_football"]:
        evs = fetch_sm_by_type(td)
        print(f"  {td}: {len(evs)}")
        for e in evs:
            e["_sport"] = td
            sm_all.append(e)

    sm_by_date = defaultdict(list)
    for e in sm_all:
        name = e.get("name","")
        parts = re.split(r"\s+vs\s+|\s+at\s+", name, 1)
        if len(parts) != 2: continue
        a, b = toks(parts[0]), toks(parts[1])
        if not a or not b: continue
        e["_a"], e["_b"] = a, b
        sm_by_date[e["_ts"].strftime("%Y-%m-%d")].append(e)

    # PM markets
    print("\nfetching Polymarket (14d)", flush=True)
    pm_all = pm_pull(14)
    print(f"  {len(pm_all)} markets")

    # Keep those whose event title has a US-sports team name
    us_teams_any = {"Lakers","Celtics","Knicks","Nuggets","Spurs","Heat","Rockets",
                     "Suns","Thunder","Pacers","Cavaliers","Warriors","Timberwolves",
                     "Hawks","76ers","Bucks","Bulls","Clippers","Pistons","Raptors",
                     "Jazz","Magic","Grizzlies","Pelicans","Nets","Mavericks",
                     "Trail Blazers","Wizards","Hornets","Kings",
                     "Yankees","Astros","Dodgers","Cubs","Braves","Phillies","Mets",
                     "Red Sox","Cardinals","Rays","Tigers","Royals","Pirates",
                     "Orioles","Twins","Marlins","Padres","Giants","Guardians",
                     "Reds","White Sox","Nationals","Angels","Rockies","Brewers",
                     "Blue Jays","Diamondbacks","Mariners",
                     "Oilers","Rangers","Canadiens","Blackhawks","Islanders","Sabres",
                     "Penguins","Flyers","Capitals","Red Wings","Stars","Flames",
                     "Devils","Avalanche","Golden Knights",
                     "Steelers","Eagles","Patriots","Cowboys","Bills","Chiefs","Bengals"}
    pm_us = []
    for m in pm_all:
        ev = (m.get("events") or [{}])[0]
        et = ev.get("title","")
        if any(t in et for t in us_teams_any):
            pm_us.append(m)
    print(f"  {len(pm_us)} PM markets with US-sport teams in event title")

    # Match
    records = []
    cache = {}
    with httpx.Client(timeout=30) as sc:
        for m in pm_us:
            ev = (m.get("events") or [{}])[0]
            et = ev.get("title","")
            pm_teams = pm_teams_from_et(et)
            if not pm_teams: continue
            pa_t, pb_t = toks(pm_teams[0]), toks(pm_teams[1])
            if not pa_t or not pb_t: continue
            team_prices = pm_extract_teams_and_prices(m)
            if not team_prices: continue
            try:
                dt = datetime.fromisoformat(m.get("endDate","").replace("Z","+00:00"))
            except: continue
            dk = dt.strftime("%Y-%m-%d")

            match_ev = None
            for d in [dk, (dt-pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                       (dt+pd.Timedelta(days=1)).strftime("%Y-%m-%d")]:
                for e in sm_by_date.get(d, []):
                    if ((pa_t & e["_a"] and pb_t & e["_b"]) or
                            (pa_t & e["_b"] and pb_t & e["_a"])):
                        match_ev = e; break
                if match_ev: break
            if not match_ev: continue

            mw = cache.get(match_ev["id"])
            if mw is None:
                mw = sm_mw(str(match_ev["id"]), sc)
                cache[match_ev["id"]] = mw
            if not mw: continue

            # For each PM team outcome, find matching Smarkets contract
            for team_name, pm_y in team_prices:
                if pm_y is None: continue
                tt = toks(team_name)
                if not tt or tt == {"draw"}: continue
                sm_ct = None
                for c in mw["contracts"]:
                    if toks(c["name"]) & tt:
                        sm_ct = c; break
                if not sm_ct or sm_ct["mid"] is None: continue
                records.append({
                    "pm_event": et,
                    "sport": match_ev["_sport"],
                    "team": team_name,
                    "pm_yes": pm_y,
                    "sm_mid": sm_ct["mid"],
                    "sm_bid": sm_ct["best_bid"],
                    "sm_offer": sm_ct["best_offer"],
                    "spread": pm_y - sm_ct["mid"],
                    "sm_contract": sm_ct["name"],
                    "pm_vol24h": float(m.get("volume24hr") or 0),
                })

    df = pd.DataFrame(records)
    df.to_parquet(DATA_DIR / "08_us_sports.parquet", index=False)
    print(f"\n{len(df)} matched team-contract pairs")
    if len(df):
        print(df[["team","sport","pm_yes","sm_mid","spread","pm_vol24h"]].to_string())
        print(f"\nmean: {df['spread'].mean():+.4f}  median: {df['spread'].median():+.4f}  "
              f"stdev: {df['spread'].std():.4f}  abs_mean: {df['spread'].abs().mean():.4f}")
        print("\nby sport:")
        for sp, g in df.groupby("sport"):
            print(f"  {sp}: n={len(g)}  mean={g['spread'].mean():+.4f}  "
                  f"|mean|={g['spread'].abs().mean():.4f}")
        print("\nby PM bucket:")
        df["bucket"] = (df["pm_yes"] * 20).astype(int) / 20
        for b, g in df.groupby("bucket"):
            if len(g) >= 1:
                print(f"  [{b:.2f},{b+0.05:.2f}): n={len(g)}  "
                      f"pm={g['pm_yes'].mean():.3f}  sm={g['sm_mid'].mean():.3f}  "
                      f"sp={g['spread'].mean():+.4f}")

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_matched": int(len(df)),
    }
    if len(df):
        summary.update({
            "by_sport": {sp: {"n": int(len(g)),
                               "mean_spread": round(float(g["spread"].mean()), 4),
                               "abs_mean_spread": round(float(g["spread"].abs().mean()), 4)}
                          for sp, g in df.groupby("sport")},
            "overall": {
                "mean": round(float(df["spread"].mean()), 4),
                "median": round(float(df["spread"].median()), 4),
                "stdev": round(float(df["spread"].std()), 4),
                "abs_mean": round(float(df["spread"].abs().mean()), 4),
            },
        })
    (DATA_DIR / "08_summary.json").write_text(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
