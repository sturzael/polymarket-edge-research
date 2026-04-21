"""Full sweep: Polymarket × Smarkets × Kalshi overlap.

Expands on 04 by:
- Drawing Smarkets events from ALL sport types (not just football).
- Paginating to get all near-term events on each venue.
- Kalshi ticker-based overlap: count how many Polymarket sports markets
  have a matching Kalshi ticker (we can see tickers without auth even
  though we can't see prices).
- Filtering out mismatches where |spread| > 0.15 (likely wrong pairing).
- Calibration by Polymarket yes bucket, stratified by sport.

Output: data/05_full_sweep.parquet + data/05_summary.json
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pandas as pd
import pmxt

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

SM_BASE = "https://api.smarkets.com/v3"
PM_BASE = "https://gamma-api.polymarket.com"

STOP = set("vs v x at the will win beat game match won of a an on or new fc cf ca cd the cup de sc sf la en 1 2 u21 u23".split())

# Smarkets event-type domains (mapping sport → Smarkets "type" values)
SM_TYPES = {
    "football": "football_match",
    "basketball": "basketball_match",
    "baseball": "baseball_match",
    "ice_hockey": "ice_hockey_match",
    "tennis": "tennis_match",
    "american_football": "american_football_match",
    "cricket": "cricket_match",
    "mma": "boxing_match",  # Smarkets labels MMA under boxing in some cases
}


def toks(s):
    if not s: return set()
    s = re.sub(r"\(.*?\)", " ", s.lower())
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return {t for t in s.split() if t not in STOP and len(t) >= 3}


def fetch_smarkets_events(type_: str, hours_ahead: int = 168) -> list:
    all_events = []
    with httpx.Client(timeout=30) as c:
        # Page through using ?last_seen_id... or cursor if available
        url = f"{SM_BASE}/events/"
        params = {"type_domain": type_.replace("_match",""),
                   "state": "upcoming", "limit": 200,
                   "sort": "start_datetime,id"}
        try:
            r = c.get(url, params=params)
            if r.status_code == 400:
                # Retry with type= instead of type_domain
                params = {"type": type_, "state": "upcoming",
                           "limit": 200, "sort": "start_datetime,id"}
                r = c.get(url, params=params)
            if r.status_code != 200:
                return []
            data = r.json()
            all_events = data.get("events", [])
        except Exception as e:
            print(f"  sm err ({type_}): {e}")
            return []
    now = datetime.now(timezone.utc)
    near = []
    for e in all_events:
        try:
            st = datetime.fromisoformat(e["start_datetime"].replace("Z","+00:00"))
            delta_h = (st - now).total_seconds() / 3600
            if 0 <= delta_h <= hours_ahead:
                e["_start_ts"] = st
                e["_delta_h"] = delta_h
                near.append(e)
        except Exception:
            continue
    return near


def sm_match_winner(event_id, client):
    r = client.get(f"{SM_BASE}/events/{event_id}/markets/")
    if r.status_code != 200:
        return None
    ms = r.json().get("markets", [])
    for m in ms:
        nm = (m.get("name") or "").lower()
        if "full-time result" in nm or nm == "winner" or "match odds" in nm or "moneyline" in nm:
            mid = m["id"]
            cts = client.get(f"{SM_BASE}/markets/{mid}/contracts/").json().get("contracts", [])
            q = client.get(f"{SM_BASE}/markets/{mid}/quotes/").json()
            out_contracts = []
            for ct in cts:
                cid = str(ct["id"])
                qv = q.get(cid, {})
                bids = qv.get("bids", [])
                offers = qv.get("offers", [])
                best_bid = bids[0]["price"] / 10000 if bids else None
                best_offer = offers[0]["price"] / 10000 if offers else None
                mid_px = None
                if best_bid and best_offer:
                    mid_px = (best_bid + best_offer) / 2
                elif best_bid:
                    mid_px = best_bid
                elif best_offer:
                    mid_px = best_offer
                out_contracts.append({
                    "contract_id": cid, "name": ct["name"],
                    "best_bid": best_bid, "best_offer": best_offer,
                    "mid": mid_px,
                })
            return {"market_id": mid, "market_name": m.get("name"),
                    "contracts": out_contracts}
    return None


def fetch_polymarket_h2h(days_ahead=7):
    now = datetime.now(timezone.utc)
    end = now + pd.Timedelta(days=days_ahead)
    out = []
    with httpx.Client(timeout=30) as c:
        offset = 0
        while offset < 20000:
            r = c.get(f"{PM_BASE}/markets", params={
                "active": "true", "closed": "false", "archived": "false",
                "end_date_min": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end_date_max": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "order": "volume",
                "ascending": "false",
                "limit": 500, "offset": offset,
            })
            if r.status_code != 200:
                break
            batch = r.json()
            if not batch:
                break
            out.extend(batch)
            if len(batch) < 500:
                break
            offset += 500
    return out


def pm_filter_h2h(markets):
    out = []
    for m in markets:
        q = (m.get("question") or "").lower()
        if not q.startswith("will "): continue
        if " win" not in q: continue
        if "draw" in q: continue
        evs = m.get("events") or []
        if not evs: continue
        etitle = evs[0].get("title") or ""
        if " vs." not in etitle and " vs " not in etitle: continue
        out.append(m)
    return out


def pm_team_from_q(q):
    m = re.match(r"^will\s+(.+?)\s+win(\s+on\s+\d{4}-\d{2}-\d{2})?\??$",
                 (q or "").strip(), re.IGNORECASE)
    return m.group(1).strip() if m else None


def pm_teams_from_etitle(t):
    parts = re.split(r"\s+vs\.?\s+|\s+v\s+", t or "",
                      maxsplit=1, flags=re.IGNORECASE)
    return (parts[0].strip(), parts[1].strip()) if len(parts) == 2 else None


def pm_yes(market):
    import json as _json
    try:
        labels = _json.loads(market.get("outcomes") or "[]")
        prices = _json.loads(market.get("outcomePrices") or "[]")
        for lab, pr in zip(labels, prices):
            if str(lab).lower() == "yes":
                return float(pr)
    except Exception:
        return None
    return None


def fetch_kalshi_tickers():
    """Pull Kalshi's active sports market tickers via public API (no prices
    available, but we can count inventory overlap by deriving teams from
    ticker naming)."""
    base = "https://api.elections.kalshi.com/trade-api/v2"
    out = []
    with httpx.Client(timeout=30) as c:
        # Iterate sports series tickers
        series_tickers = ["KXNBAGAME", "KXNFLGAME", "KXMLBGAME", "KXNHLGAME",
                           "KXUFCFIGHT", "KXMLSGAME", "KXEPLGAME",
                           "KXLALIGAGAME", "KXSERIEAGAME", "KXBUNDESLIGAGAME",
                           "KXLIGUE1GAME", "KXCHAMPLGAME"]
        for st in series_tickers:
            offset = None
            n_for_series = 0
            while True:
                p = {"series_ticker": st, "status": "open", "limit": 200}
                if offset:
                    p["cursor"] = offset
                r = c.get(f"{base}/markets", params=p)
                if r.status_code != 200:
                    break
                data = r.json()
                ms = data.get("markets", [])
                if not ms:
                    break
                for m in ms:
                    m["_series"] = st
                    out.append(m)
                n_for_series += len(ms)
                cursor = data.get("cursor") or ""
                if not cursor or len(ms) < 200:
                    break
                offset = cursor
            print(f"    kalshi {st}: {n_for_series} markets")
    return out


def kalshi_parse_ticker(ticker, title):
    """Extract date + team codes from Kalshi sports tickers like
    KXNBAGAME-26APR25OKCPHX-PHX → (date=2026-04-25, teams={OKC,PHX}, winning=PHX)
    KXMLBGAME-26APR222145LADSF-SF → (date=2026-04-22, teams={LAD,SF}, winning=SF)
    """
    parts = ticker.split("-")
    if len(parts) < 3:
        return None
    series, date_code, winner_code = parts[0], parts[1], parts[2]
    # date_code: 26APR25OKCPHX or 26APR222145LADSF (time embedded)
    m = re.match(r"(\d{2})([A-Z]{3})(\d{2})(\d{0,4})(.+)", date_code)
    if not m:
        return None
    yy, mon, dd, hhmm, team_codes = m.groups()
    month_map = {"JAN":"01","FEB":"02","MAR":"03","APR":"04","MAY":"05","JUN":"06",
                  "JUL":"07","AUG":"08","SEP":"09","OCT":"10","NOV":"11","DEC":"12"}
    if mon not in month_map:
        return None
    date_iso = f"20{yy}-{month_map[mon]}-{dd}"
    # team_codes is like "OKCPHX" or "LADSF" (3+3 or 3+2 chars, ambiguous).
    # Use the winner_code to split: if team_codes ends with winner_code, the
    # loser is the prefix.
    loser_code = None
    if team_codes.endswith(winner_code):
        loser_code = team_codes[:-len(winner_code)]
    else:
        # Fallback: split in half
        mid = len(team_codes) // 2
        loser_code = team_codes[:mid]
    return {
        "date": date_iso,
        "winning_team": winner_code,
        "losing_team": loser_code,
        "title": title,
    }


def main():
    print("=== fetching Smarkets events for multiple sports ===", flush=True)
    sm_events = []
    sports_of_interest = ["football", "basketball", "baseball",
                           "ice_hockey", "tennis", "american_football"]
    for sp in sports_of_interest:
        evs = fetch_smarkets_events(SM_TYPES.get(sp, sp + "_match"))
        print(f"  {sp}: {len(evs)} events")
        sm_events.extend(evs)
    print(f"  total Smarkets near-term events: {len(sm_events)}")

    print("\n=== fetching Polymarket H2H sports markets ===", flush=True)
    pm_all = fetch_polymarket_h2h(7)
    pm_h2h = pm_filter_h2h(pm_all)
    print(f"  {len(pm_all)} pm markets, {len(pm_h2h)} H2H-shaped")

    print("\n=== fetching Kalshi public sports ticker inventory ===", flush=True)
    ks_tickers = fetch_kalshi_tickers()
    print(f"  {len(ks_tickers)} Kalshi sports markets")
    # Parse
    ks_parsed = []
    for m in ks_tickers:
        p = kalshi_parse_ticker(m["ticker"], m.get("title",""))
        if p:
            p["ticker"] = m["ticker"]
            p["_series"] = m["_series"]
            ks_parsed.append(p)
    # Index by date -> list of parsed
    ks_by_date = defaultdict(list)
    for p in ks_parsed:
        ks_by_date[p["date"]].append(p)
    print(f"  {len(ks_parsed)} kalshi tickers parsed")

    # === Build SM index ===
    sm_by_date = defaultdict(list)
    for e in sm_events:
        ename = e.get("name","")
        parts = re.split(r"\s+vs\s+", ename, maxsplit=1)
        if len(parts) != 2: continue
        a_toks, b_toks = toks(parts[0]), toks(parts[1])
        if not a_toks or not b_toks: continue
        e["_a_toks"], e["_b_toks"] = a_toks, b_toks
        dk = e["_start_ts"].strftime("%Y-%m-%d")
        sm_by_date[dk].append(e)

    # === Match loop ===
    records = []
    sm_mw_cache = {}
    with httpx.Client(timeout=30) as sc:
        for i, m in enumerate(pm_h2h):
            q = m.get("question","")
            evs = m.get("events") or []
            if not evs: continue
            etitle = evs[0].get("title","")
            pm_teams = pm_teams_from_etitle(etitle)
            if not pm_teams: continue
            pm_a_toks, pm_b_toks = toks(pm_teams[0]), toks(pm_teams[1])
            if not pm_a_toks or not pm_b_toks: continue
            pm_yes_team = pm_team_from_q(q)
            if not pm_yes_team: continue
            pm_y = pm_yes(m)
            if pm_y is None: continue
            pm_end = m.get("endDate") or ""
            try:
                pm_dt = datetime.fromisoformat(pm_end.replace("Z","+00:00"))
            except Exception:
                continue
            dk = pm_dt.strftime("%Y-%m-%d")

            # --- Smarkets ---
            sm_match = None
            for dkey in [dk,
                          (pm_dt - pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                          (pm_dt + pd.Timedelta(days=1)).strftime("%Y-%m-%d")]:
                for e in sm_by_date.get(dkey, []):
                    if ((pm_a_toks & e["_a_toks"] and pm_b_toks & e["_b_toks"]) or
                            (pm_a_toks & e["_b_toks"] and pm_b_toks & e["_a_toks"])):
                        sm_match = e
                        break
                if sm_match: break

            sm_mid = sm_bid = sm_offer = None
            sm_contract_name = None
            if sm_match:
                mw = sm_mw_cache.get(sm_match["id"])
                if mw is None:
                    mw = sm_match_winner(str(sm_match["id"]), sc)
                    sm_mw_cache[sm_match["id"]] = mw
                if mw:
                    pm_yes_toks = toks(pm_yes_team)
                    for ct in mw["contracts"]:
                        ct_toks = toks(ct["name"])
                        if pm_yes_toks & ct_toks and pm_yes_toks != {"draw"}:
                            sm_mid = ct["mid"]
                            sm_bid = ct["best_bid"]
                            sm_offer = ct["best_offer"]
                            sm_contract_name = ct["name"]
                            break

            # --- Kalshi ticker match ---
            ks_match = None
            for ks in ks_by_date.get(dk, []) + ks_by_date.get(
                    (pm_dt - pd.Timedelta(days=1)).strftime("%Y-%m-%d"), []) + ks_by_date.get(
                    (pm_dt + pd.Timedelta(days=1)).strftime("%Y-%m-%d"), []):
                # Check if either team's first 3 letters is in the ticker
                pm_yes_3 = (pm_yes_team[:3].upper() if pm_yes_team else "")
                win_code = ks.get("winning_team","")
                if pm_yes_3 and pm_yes_3 in win_code:
                    ks_match = ks
                    break
                # Alternative: any token in either team matches ticker
                for tok in (pm_a_toks | pm_b_toks):
                    if tok[:3].upper() in (ks.get("winning_team","")
                                            + ks.get("losing_team","")):
                        ks_match = ks
                        break
                if ks_match: break

            rec = {
                "pm_question": q,
                "pm_event_title": etitle,
                "pm_end": pm_end,
                "pm_volume": float(m.get("volume") or 0),
                "pm_volume24h": float(m.get("volume24hr") or 0),
                "pm_yes": pm_y,
                "pm_yes_team": pm_yes_team,
                "sm_event": sm_match["name"] if sm_match else None,
                "sm_contract": sm_contract_name,
                "sm_bid": sm_bid,
                "sm_offer": sm_offer,
                "sm_mid": sm_mid,
                "spread_pm_sm": (pm_y - sm_mid) if sm_mid else None,
                "ks_ticker": ks_match["ticker"] if ks_match else None,
            }
            records.append(rec)

            if (i + 1) % 100 == 0:
                print(f"  progress {i+1}/{len(pm_h2h)}  "
                      f"n_records={len(records)}", flush=True)

    df = pd.DataFrame(records)
    df.to_parquet(DATA_DIR / "05_full_sweep.parquet", index=False)

    # Summary
    n_sm_matched = df["sm_mid"].notna().sum()
    n_ks_matched = df["ks_ticker"].notna().sum()
    n_triple = ((df["sm_mid"].notna()) & (df["ks_ticker"].notna())).sum()

    print(f"\n=== OVERALL ===")
    print(f"  PM H2H markets considered: {len(pm_h2h)}")
    print(f"  PM markets included (yes team parseable): {len(df)}")
    print(f"  SM matched with live mid: {n_sm_matched}")
    print(f"  KS ticker matched: {n_ks_matched}")
    print(f"  Both SM mid + KS ticker: {n_triple}")

    sub_sm = df[df["spread_pm_sm"].notna()].copy()
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_sm_events_near_term": len(sm_events),
        "n_pm_h2h": len(pm_h2h),
        "n_records": int(len(df)),
        "n_sm_matched_with_price": int(n_sm_matched),
        "n_ks_matched_ticker": int(n_ks_matched),
        "n_both": int(n_triple),
    }

    if len(sub_sm):
        # Exclude extreme mismatches (likely wrong pairings)
        clean = sub_sm[sub_sm["spread_pm_sm"].abs() <= 0.15].copy()
        summary["n_clean_spread_pairs"] = int(len(clean))
        if len(clean):
            summary["spread_stats_clean"] = {
                "n": int(len(clean)),
                "mean": round(float(clean["spread_pm_sm"].mean()), 4),
                "median": round(float(clean["spread_pm_sm"].median()), 4),
                "stdev": round(float(clean["spread_pm_sm"].std()), 4),
                "abs_mean": round(float(clean["spread_pm_sm"].abs().mean()), 4),
                "min": round(float(clean["spread_pm_sm"].min()), 4),
                "max": round(float(clean["spread_pm_sm"].max()), 4),
                "pct_gt_1pp": round(
                    float((clean["spread_pm_sm"].abs() > 0.01).mean()), 4),
                "pct_gt_2pp": round(
                    float((clean["spread_pm_sm"].abs() > 0.02).mean()), 4),
                "pct_gt_5pp": round(
                    float((clean["spread_pm_sm"].abs() > 0.05).mean()), 4),
            }
            print(f"\n=== Polymarket - Smarkets (clean; |sp|<=15pp, n={len(clean)}) ===")
            s = summary["spread_stats_clean"]
            print(f"  mean={s['mean']:+.4f}  median={s['median']:+.4f}  "
                  f"|mean|={s['abs_mean']:.4f}  stdev={s['stdev']:.4f}")
            print(f"  range=[{s['min']:+.4f}, {s['max']:+.4f}]")
            print(f"  pct |spread|>1pp: {s['pct_gt_1pp']:.1%}")
            print(f"  pct |spread|>2pp: {s['pct_gt_2pp']:.1%}")
            print(f"  pct |spread|>5pp: {s['pct_gt_5pp']:.1%}")

            # By PM bucket
            clean["bucket"] = (clean["pm_yes"] * 20).astype(int) / 20
            bucket_rows = []
            for b, g in clean.groupby("bucket"):
                if len(g) >= 3:
                    bucket_rows.append({
                        "bucket_lo": float(b),
                        "bucket_hi": float(b) + 0.05,
                        "n": int(len(g)),
                        "pm_mean": round(float(g["pm_yes"].mean()), 4),
                        "sm_mean": round(float(g["sm_mid"].mean()), 4),
                        "spread_mean": round(float(g["spread_pm_sm"].mean()), 4),
                        "spread_median": round(float(g["spread_pm_sm"].median()), 4),
                        "abs_spread_mean": round(float(g["spread_pm_sm"].abs().mean()), 4),
                    })
            summary["by_pm_bucket_clean"] = bucket_rows
            print("\n=== BY PM PRICE BUCKET (clean) ===")
            for r in bucket_rows:
                print(f"  [{r['bucket_lo']:.2f}, {r['bucket_hi']:.2f}): "
                      f"n={r['n']:>3}  pm={r['pm_mean']:.3f}  sm={r['sm_mean']:.3f}  "
                      f"spread_mean={r['spread_mean']:+.4f}")

    (DATA_DIR / "05_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(f"\nwrote 05_summary.json")


if __name__ == "__main__":
    main()
