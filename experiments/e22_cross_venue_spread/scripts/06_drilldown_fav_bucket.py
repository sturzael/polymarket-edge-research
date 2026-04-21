"""Drill down on the 0.55-0.60 Polymarket YES bucket by widening the match
window and including all Smarkets sport types — the single most
important bucket for the FLB finding."""
from __future__ import annotations
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

def fetch_sm_events(type_domain, hours_ahead=336):  # 14 days
    with httpx.Client(timeout=30) as c:
        r = c.get(f"{SM_BASE}/events/", params={
            "type_domain": type_domain, "state": "upcoming",
            "limit": 500, "sort": "start_datetime,id"})
        if r.status_code != 200:
            return []
        events = r.json().get("events", [])
    now = datetime.now(timezone.utc)
    near = []
    for e in events:
        try:
            st = datetime.fromisoformat(e["start_datetime"].replace("Z","+00:00"))
            dh = (st - now).total_seconds() / 3600
            if 0 <= dh <= hours_ahead:
                e["_start_ts"] = st
                near.append(e)
        except Exception:
            pass
    return near

def sm_match_winner(event_id, client):
    try:
        r = client.get(f"{SM_BASE}/events/{event_id}/markets/")
        if r.status_code != 200: return None
        for m in r.json().get("markets", []):
            nm = (m.get("name") or "").lower()
            if "full-time" in nm or nm == "winner" or "match odds" in nm or "moneyline" in nm:
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
                    out.append({"contract_id":cid, "name":ct["name"],
                                "best_bid":bb, "best_offer":bo, "mid":mid})
                return {"market_id": m["id"], "contracts": out}
    except Exception as e:
        return None
    return None

def pm_fetch_h2h(days_ahead=14):
    now = datetime.now(timezone.utc)
    end = now + pd.Timedelta(days=days_ahead)
    out = []
    with httpx.Client(timeout=30) as c:
        off = 0
        while off < 30000:
            r = c.get(f"{PM_BASE}/markets", params={
                "active":"true","closed":"false","archived":"false",
                "end_date_min": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end_date_max": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "order":"volume", "ascending":"false",
                "limit":500,"offset":off})
            if r.status_code != 200: break
            b = r.json()
            if not b: break
            out.extend(b)
            if len(b) < 500: break
            off += 500
    return out

def pm_yes(market):
    import json as _json
    try:
        labels = _json.loads(market.get("outcomes") or "[]")
        prices = _json.loads(market.get("outcomePrices") or "[]")
        for lab, pr in zip(labels, prices):
            if str(lab).lower() == "yes": return float(pr)
    except Exception:
        return None
    return None

def pm_team_from_q(q):
    m = re.match(r"^will\s+(.+?)\s+win(\s+on\s+\d{4}-\d{2}-\d{2})?\??$",
                 (q or "").strip(), re.IGNORECASE)
    return m.group(1).strip() if m else None

def pm_teams(t):
    parts = re.split(r"\s+vs\.?\s+|\s+v\s+", t or "", 1, re.IGNORECASE)
    return (parts[0].strip(), parts[1].strip()) if len(parts) == 2 else None


def main():
    # 1. Get ALL Smarkets upcoming events across sports, 14 days ahead
    print("=== Smarkets upcoming (14d) across all sports ===", flush=True)
    sm_all = []
    for td in ["football", "basketball", "baseball", "ice_hockey",
               "tennis", "american_football", "cricket"]:
        evs = fetch_sm_events(td, 336)
        print(f"  {td}: {len(evs)}")
        sm_all.extend(evs)
    print(f"  total: {len(sm_all)}")

    sm_by_date = defaultdict(list)
    for e in sm_all:
        name = e.get("name","")
        parts = re.split(r"\s+vs\s+", name, 1)
        if len(parts) != 2: continue
        a, b = toks(parts[0]), toks(parts[1])
        if not a or not b: continue
        e["_a"], e["_b"] = a, b
        sm_by_date[e["_start_ts"].strftime("%Y-%m-%d")].append(e)

    # 2. PM H2H markets
    print("\n=== Polymarket H2H (14d) ===", flush=True)
    pm_all = pm_fetch_h2h(14)
    print(f"  {len(pm_all)} markets")
    pm_h2h = []
    for m in pm_all:
        q = (m.get("question") or "").lower()
        if not q.startswith("will "): continue
        if " win" not in q or "draw" in q: continue
        evs = m.get("events") or []
        if not evs: continue
        et = evs[0].get("title","")
        if " vs." not in et and " vs " not in et: continue
        pm_h2h.append(m)
    print(f"  {len(pm_h2h)} H2H shape")

    # 3. Match + fetch SM price
    records = []
    cache = {}
    with httpx.Client(timeout=30) as sc:
        for i, m in enumerate(pm_h2h):
            q = m.get("question","")
            ev = (m.get("events") or [{}])[0]
            pmt = pm_teams(ev.get("title",""))
            if not pmt: continue
            pm_a_t, pm_b_t = toks(pmt[0]), toks(pmt[1])
            if not pm_a_t or not pm_b_t: continue
            pm_team = pm_team_from_q(q)
            if not pm_team: continue
            pm_y = pm_yes(m)
            if pm_y is None: continue
            try:
                dt = datetime.fromisoformat(m.get("endDate","").replace("Z","+00:00"))
            except Exception:
                continue
            dk = dt.strftime("%Y-%m-%d")
            sm_match = None
            for d in [dk,
                       (dt-pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                       (dt+pd.Timedelta(days=1)).strftime("%Y-%m-%d")]:
                for e in sm_by_date.get(d, []):
                    if ((pm_a_t & e["_a"] and pm_b_t & e["_b"]) or
                            (pm_a_t & e["_b"] and pm_b_t & e["_a"])):
                        sm_match = e; break
                if sm_match: break
            if not sm_match: continue
            mw = cache.get(sm_match["id"])
            if mw is None:
                mw = sm_match_winner(str(sm_match["id"]), sc)
                cache[sm_match["id"]] = mw
            if not mw: continue
            pm_team_t = toks(pm_team)
            sm_ct = None
            for c in mw["contracts"]:
                if toks(c["name"]) & pm_team_t and pm_team_t != {"draw"}:
                    sm_ct = c; break
            if not sm_ct or sm_ct["mid"] is None: continue
            records.append({
                "pm_question": q, "pm_team": pm_team, "pm_yes": pm_y,
                "pm_vol": float(m.get("volume") or 0),
                "pm_vol24h": float(m.get("volume24hr") or 0),
                "pm_end": m.get("endDate"),
                "sm_event": sm_match["name"],
                "sm_bid": sm_ct["best_bid"], "sm_offer": sm_ct["best_offer"],
                "sm_mid": sm_ct["mid"],
                "spread": pm_y - sm_ct["mid"],
                "pm_url": f"https://polymarket.com/event/{m.get('slug')}",
            })
            if (i+1) % 200 == 0:
                print(f"  progress {i+1}/{len(pm_h2h)}  records={len(records)}")

    df = pd.DataFrame(records)
    df.to_parquet(DATA_DIR / "06_drilldown.parquet", index=False)
    print(f"\n{len(df)} price pairs")

    # Filter clean pairs (exclude |spread|>0.15 mismatches)
    clean = df[df["spread"].abs() <= 0.15].copy()
    print(f"{len(clean)} clean pairs")

    # Global stats
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_records": int(len(df)),
        "n_clean": int(len(clean)),
        "all_stats": {
            "mean": round(float(clean["spread"].mean()), 4),
            "median": round(float(clean["spread"].median()), 4),
            "stdev": round(float(clean["spread"].std()), 4),
            "abs_mean": round(float(clean["spread"].abs().mean()), 4),
        },
    }

    # Bucket
    clean["bucket"] = (clean["pm_yes"] * 20).astype(int) / 20
    bk_rows = []
    for b, g in clean.groupby("bucket"):
        bk_rows.append({
            "bucket_lo": round(float(b), 4),
            "bucket_hi": round(float(b)+0.05, 4),
            "n": int(len(g)),
            "pm_mean": round(float(g["pm_yes"].mean()), 4),
            "sm_mean": round(float(g["sm_mid"].mean()), 4),
            "spread_mean": round(float(g["spread"].mean()), 4),
            "spread_median": round(float(g["spread"].median()), 4),
            "abs_spread_mean": round(float(g["spread"].abs().mean()), 4),
        })
    summary["by_bucket"] = bk_rows

    print("\n=== BY PM PRICE BUCKET (clean) ===")
    print(f"  {'bucket':<14} {'n':>4}  {'pm':>6}  {'sm':>6}  {'spread_mean':>11}  {'|sp|_mean':>9}")
    for r in bk_rows:
        if r["n"] >= 2:
            print(f"  [{r['bucket_lo']:.2f}, {r['bucket_hi']:.2f})  "
                  f"{r['n']:>4}  {r['pm_mean']:>.3f}  {r['sm_mean']:>.3f}  "
                  f"{r['spread_mean']:>+11.4f}  {r['abs_spread_mean']:>9.4f}")

    # Focus on 0.55-0.60 bucket
    fav = clean[(clean["pm_yes"] >= 0.55) & (clean["pm_yes"] < 0.60)]
    print(f"\n=== 0.55-0.60 BUCKET (n={len(fav)}) ===")
    if len(fav):
        for _, row in fav.iterrows():
            print(f"  {row['pm_team']:<28}  pm={row['pm_yes']:.3f}  "
                  f"sm={row['sm_mid']:.3f}  sp={row['spread']:+.4f}  "
                  f"vol={row['pm_vol']:.0f}")
        summary["fav_bucket_0.55_0.60"] = {
            "n": int(len(fav)),
            "pm_mean": round(float(fav["pm_yes"].mean()), 4),
            "sm_mean": round(float(fav["sm_mid"].mean()), 4),
            "spread_mean": round(float(fav["spread"].mean()), 4),
        }

    # Also 0.50-0.65 "favorite range"
    fav2 = clean[(clean["pm_yes"] >= 0.50) & (clean["pm_yes"] < 0.65)]
    print(f"\n=== 0.50-0.65 favorite range (n={len(fav2)}) ===")
    if len(fav2):
        print(f"  spread_mean={fav2['spread'].mean():+.4f}  "
              f"median={fav2['spread'].median():+.4f}  "
              f"stdev={fav2['spread'].std():.4f}")
        summary["fav_range_0.50_0.65"] = {
            "n": int(len(fav2)),
            "spread_mean": round(float(fav2["spread"].mean()), 4),
            "spread_median": round(float(fav2["spread"].median()), 4),
            "spread_stdev": round(float(fav2["spread"].std()), 4),
        }

    (DATA_DIR / "06_summary.json").write_text(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
