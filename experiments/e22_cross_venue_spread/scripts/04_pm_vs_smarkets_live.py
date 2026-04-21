"""Definitive Polymarket vs Smarkets live cross-venue spread.

Data sources:
- Polymarket: gamma API /markets (already-queryable, live prices in field)
- Smarkets:   v3 REST API — events → markets → contracts → quotes

Matching:
1. Pull Smarkets upcoming football_match events (next 7 days).
2. Pull Polymarket sports-category markets resolving same window.
3. Match by (team_a_tokens, team_b_tokens) symmetric — requires BOTH teams'
   tokens overlap >= 1 token each with the corresponding Smarkets outcome.
4. For each match, use Smarkets /markets/{id}/quotes/ to get bid/offer.
5. Compare Polymarket yes_price_team_a to Smarkets mid-price_team_a.

Output: data/04_pm_smarkets_live.parquet + 04_summary.json
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pandas as pd

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

SM_BASE = "https://api.smarkets.com/v3"
PM_BASE = "https://gamma-api.polymarket.com"

STOP = set("vs v x at the will win beat game match won of a an on or new fc cf ca cd the cup de sc sf la en 1 2".split())


def toks(s: str) -> set[str]:
    if not s: return set()
    s = re.sub(r"\(.*?\)", " ", s.lower())
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return {t for t in s.split() if t not in STOP and len(t) >= 3}


def fetch_smarkets_events_football(hours_ahead: int = 168) -> list:
    """Return Smarkets football matches in the next hours_ahead hours."""
    all_events = []
    with httpx.Client(timeout=30) as c:
        # Smarkets paginates; use limit+pagination
        offset = 0
        while True:
            r = c.get(f"{SM_BASE}/events/", params={
                "type_domain": "football",
                "state": "upcoming", "limit": 200,
                "sort": "start_datetime,id",
            })
            if r.status_code != 200:
                print("smarkets events err:", r.status_code, r.text[:200])
                break
            data = r.json()
            batch = data.get("events", [])
            if not batch:
                break
            all_events.extend(batch)
            pag = data.get("pagination", {})
            next_page = pag.get("next_page")
            if not next_page:
                break
            # next_page is a full path; break to avoid extra calls for now
            break
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


def fetch_smarkets_match_winner(event_id: str, client: httpx.Client) -> dict | None:
    """For a given Smarkets event, find the 'Full-time result' / match winner
    market and return contracts + live quotes."""
    r = client.get(f"{SM_BASE}/events/{event_id}/markets/")
    if r.status_code != 200:
        return None
    ms = r.json().get("markets", [])
    # Heuristic for match-winner market
    mw = None
    for m in ms:
        nm = (m.get("name") or "").lower()
        if "full-time result" in nm or "match odds" == nm or nm == "winner":
            mw = m
            break
    if mw is None:
        return None
    mid = mw["id"]
    cts_resp = client.get(f"{SM_BASE}/markets/{mid}/contracts/").json()
    contracts = cts_resp.get("contracts", [])
    qresp = client.get(f"{SM_BASE}/markets/{mid}/quotes/").json()
    quotes = qresp  # keys = contract_ids
    out = {"market_id": mid, "market_name": mw.get("name"), "contracts": []}
    for ct in contracts:
        cid = str(ct["id"])
        q = quotes.get(cid, {})
        bids = q.get("bids", [])
        offers = q.get("offers", [])
        best_bid = bids[0]["price"] / 10000 if bids else None  # bp -> probability
        best_offer = offers[0]["price"] / 10000 if offers else None
        mid_px = None
        if best_bid and best_offer:
            mid_px = (best_bid + best_offer) / 2
        elif best_bid:
            mid_px = best_bid
        elif best_offer:
            mid_px = best_offer
        out["contracts"].append({
            "contract_id": cid,
            "name": ct["name"],
            "best_bid": best_bid,
            "best_offer": best_offer,
            "mid": mid_px,
        })
    return out


def fetch_polymarket_sports_markets(days_ahead: int = 7) -> list[dict]:
    """Gamma /markets: active, sports category, resolving within days_ahead."""
    now = datetime.now(timezone.utc)
    end = now + pd.Timedelta(days=days_ahead)
    out = []
    with httpx.Client(timeout=30) as c:
        # Gamma has /markets endpoint with filters; sports via tag slug
        offset = 0
        while True:
            r = c.get(f"{PM_BASE}/markets", params={
                "active": "true", "closed": "false", "archived": "false",
                "end_date_min": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end_date_max": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "order": "volume",
                "ascending": "false",
                "limit": 500, "offset": offset,
            })
            if r.status_code != 200:
                print("pm err:", r.status_code, r.text[:200])
                break
            batch = r.json()
            if not batch:
                break
            out.extend(batch)
            if len(batch) < 500:
                break
            offset += 500
            if offset >= 10000:
                break
    return out


def pm_sports_filter(markets: list[dict]) -> list[dict]:
    """Keep markets that are 'Will TEAM win on YYYY-MM-DD' style from a
    'Team A vs. Team B' event."""
    out = []
    for m in markets:
        q = (m.get("question") or "").lower()
        if not q.startswith("will "):
            continue
        # require "win on YYYY-MM-DD" or "win "  pattern
        if " win" not in q:
            continue
        if "draw" in q or "vs." in q[:20]:  # exclude draw markets
            continue
        # Event must be "X vs. Y"
        evs = m.get("events") or []
        if not evs:
            continue
        etitle = evs[0].get("title") or ""
        if " vs." not in etitle and " vs " not in etitle:
            continue
        out.append(m)
    return out


def pm_team_from_question(question: str) -> str | None:
    """Extract the 'team that must win' from question like
    'Will Paris FC win on 2026-04-26?'"""
    if not question:
        return None
    m = re.match(r"^will\s+(.+?)\s+win(\s+on\s+\d{4}-\d{2}-\d{2})?\??$",
                 question.strip(), re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # Alt pattern 'Will X beat Y'
    m = re.match(r"^will\s+(.+?)\s+beat\s+", question.strip(), re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None


def pm_teams_from_event_title(title: str) -> tuple[str, str] | None:
    """Parse 'Team A vs. Team B' event title into (A, B)."""
    if not title:
        return None
    parts = re.split(r"\s+vs\.?\s+|\s+v\s+", title, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) != 2:
        return None
    return parts[0].strip(), parts[1].strip()


def pm_yes_price(market: dict) -> float | None:
    """Polymarket binary: outcomes=["Yes","No"], outcomePrices=["0.3","0.7"]."""
    import json as _json
    try:
        labels = _json.loads(market.get("outcomes") or "[]")
        prices = _json.loads(market.get("outcomePrices") or "[]")
        for lab, pr in zip(labels, prices):
            if str(lab).lower() == "yes":
                return float(pr)
        if prices:
            return float(prices[0])
    except Exception:
        return None
    return None


def main():
    print("=== fetching Smarkets football events (next 168h) ===", flush=True)
    sm_events = fetch_smarkets_events_football(168)
    print(f"  {len(sm_events)} near-term football events")
    for e in sm_events[:5]:
        print(f"    {e['name']}  starts in {e['_delta_h']:.1f}h")

    print("\n=== fetching Polymarket sports markets (next 7d) ===", flush=True)
    pm_markets_raw = fetch_polymarket_sports_markets(7)
    print(f"  {len(pm_markets_raw)} markets from gamma /markets")
    pm_h2h = pm_sports_filter(pm_markets_raw)
    print(f"  {len(pm_h2h)} look like sports H2H")
    for m in pm_h2h[:5]:
        print(f"    {m.get('question', '')[:60]}  outcomes={m.get('outcomes')}  prices={m.get('outcomePrices')}")

    # Build Smarkets event lookup by sorted-team-tokens & date
    from collections import defaultdict
    sm_by_key = defaultdict(list)
    for e in sm_events:
        ename = e.get("name") or ""
        parts = re.split(r"\s+vs\s+", ename, maxsplit=1)
        if len(parts) != 2:
            continue
        a_toks, b_toks = toks(parts[0]), toks(parts[1])
        if not a_toks or not b_toks:
            continue
        e["_a_toks"] = a_toks
        e["_b_toks"] = b_toks
        e["_all_toks"] = a_toks | b_toks
        date_str = e["_start_ts"].strftime("%Y-%m-%d")
        sm_by_key[date_str].append(e)

    # For each Polymarket market, find matching Smarkets event then fetch live quotes.
    records = []
    sm_market_cache = {}  # event_id -> mw dict
    with httpx.Client(timeout=30) as sc:
        for m in pm_h2h:
            q = m.get("question") or ""
            evs = m.get("events") or []
            if not evs:
                continue
            etitle = evs[0].get("title") or ""
            pm_teams = pm_teams_from_event_title(etitle)
            if not pm_teams:
                continue
            pm_a_str, pm_b_str = pm_teams
            pm_a_toks, pm_b_toks = toks(pm_a_str), toks(pm_b_str)
            if not pm_a_toks or not pm_b_toks:
                continue
            pm_all = pm_a_toks | pm_b_toks

            # Which PM team is "Yes" = the team named in the question?
            pm_yes_team = pm_team_from_question(q)
            if not pm_yes_team:
                continue
            pm_yes_toks = toks(pm_yes_team)

            # PM end_date → date key
            pm_end = m.get("endDate") or ""
            try:
                pm_end_dt = datetime.fromisoformat(pm_end.replace("Z","+00:00"))
            except Exception:
                continue
            date_key = pm_end_dt.strftime("%Y-%m-%d")
            # Try also date +- 1 day
            candidates = []
            for dk in [date_key,
                        (pm_end_dt - pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                        (pm_end_dt + pd.Timedelta(days=1)).strftime("%Y-%m-%d")]:
                candidates.extend(sm_by_key.get(dk, []))

            match_ev = None
            for e in candidates:
                # Both pm teams must each intersect one of the sm teams
                if ((pm_a_toks & e["_a_toks"] and pm_b_toks & e["_b_toks"]) or
                        (pm_a_toks & e["_b_toks"] and pm_b_toks & e["_a_toks"])):
                    match_ev = e
                    break
            if match_ev is None:
                continue

            # Fetch Smarkets match-winner
            mw = sm_market_cache.get(match_ev["id"])
            if mw is None:
                mw = fetch_smarkets_match_winner(str(match_ev["id"]), sc)
                sm_market_cache[match_ev["id"]] = mw
            if mw is None:
                continue

            # Find Smarkets contract whose name matches the PM "yes team"
            sm_yes_contract = None
            for ct in mw["contracts"]:
                ct_toks = toks(ct["name"])
                if pm_yes_toks & ct_toks and not (pm_yes_toks == {"draw"}):
                    sm_yes_contract = ct
                    break
            if sm_yes_contract is None:
                continue

            pm_y = pm_yes_price(m)
            if pm_y is None:
                continue

            rec = {
                "pm_question": q,
                "pm_slug": m.get("slug"),
                "pm_event_title": etitle,
                "pm_end_date": pm_end,
                "pm_volume": float(m.get("volume") or 0),
                "pm_volume24h": float(m.get("volume24hr") or 0),
                "pm_yes": pm_y,
                "pm_yes_team": pm_yes_team,
                "sm_event_id": match_ev["id"],
                "sm_event_name": match_ev["name"],
                "sm_start": match_ev["start_datetime"],
                "sm_market_id": mw["market_id"],
                "sm_contract_id": sm_yes_contract["contract_id"],
                "sm_contract_name": sm_yes_contract["name"],
                "sm_bid": sm_yes_contract["best_bid"],
                "sm_offer": sm_yes_contract["best_offer"],
                "sm_mid": sm_yes_contract["mid"],
                "spread": (pm_y - sm_yes_contract["mid"]
                           if sm_yes_contract["mid"] else None),
            }
            records.append(rec)
            sm_mid_str = f"{sm_yes_contract['mid']:.3f}" if sm_yes_contract['mid'] is not None else "n/a"
            sp_str = f"{rec['spread']:+.3f}" if rec['spread'] is not None else "n/a"
            print(f"  matched: {pm_yes_team} win  pm={pm_y:.3f}  sm={sm_mid_str}  sp={sp_str}")

    df = pd.DataFrame(records)
    df.to_parquet(DATA_DIR / "04_pm_smarkets_live.parquet", index=False)
    print(f"\n{len(df)} matched rows -> 04_pm_smarkets_live.parquet")

    if len(df) == 0:
        return

    # Summary stats on 'spread' (PM yes - Smarkets mid for the same team)
    sub = df[df["spread"].notna()].copy()
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_sm_events_near_term": len(sm_events),
        "n_pm_h2h_candidates": len(pm_h2h),
        "n_matched_events": int(len(df)),
        "n_with_spread": int(len(sub)),
    }
    if len(sub):
        summary["spread_stats"] = {
            "n": int(len(sub)),
            "mean": round(float(sub["spread"].mean()), 4),
            "median": round(float(sub["spread"].median()), 4),
            "stdev": round(float(sub["spread"].std()), 4),
            "abs_mean": round(float(sub["spread"].abs().mean()), 4),
            "min": round(float(sub["spread"].min()), 4),
            "max": round(float(sub["spread"].max()), 4),
            "pct_gt_2pp": round(float((sub["spread"].abs() > 0.02).mean()), 4),
            "pct_gt_5pp": round(float((sub["spread"].abs() > 0.05).mean()), 4),
        }
        # Favorite bucket
        fav = sub[(sub["pm_yes"] >= 0.55) & (sub["pm_yes"] < 0.60)]
        if len(fav):
            summary["favorite_bucket_0.55_0.60"] = {
                "n": int(len(fav)),
                "pm_mean": round(float(fav["pm_yes"].mean()), 4),
                "sm_mean": round(float(fav["sm_mid"].mean()), 4),
                "mean_spread": round(float(fav["spread"].mean()), 4),
            }
        print(f"\n=== SPREAD STATS (Polymarket yes - Smarkets mid, same-team) ===")
        print(f"  n={len(sub)}  mean={sub['spread'].mean():+.4f}  "
              f"median={sub['spread'].median():+.4f}  "
              f"|mean|={sub['spread'].abs().mean():.4f}")
        print(f"  stdev={sub['spread'].std():.4f}  "
              f"range=[{sub['spread'].min():+.3f}, {sub['spread'].max():+.3f}]")
        print(f"  pct |spread|>2pp: {summary['spread_stats']['pct_gt_2pp']:.1%}")
        print(f"  pct |spread|>5pp: {summary['spread_stats']['pct_gt_5pp']:.1%}")
        # By Polymarket price bucket
        print("\n=== by polymarket price bucket ===")
        sub = sub.copy()
        sub["bucket"] = (sub["pm_yes"] * 20).astype(int) / 20
        bucket_stats = []
        for b, g in sub.groupby("bucket"):
            if len(g) >= 3:
                row = {
                    "bucket_lo": float(b),
                    "bucket_hi": float(b) + 0.05,
                    "n": int(len(g)),
                    "pm_mean": round(float(g["pm_yes"].mean()), 4),
                    "sm_mean": round(float(g["sm_mid"].mean()), 4),
                    "spread_mean": round(float(g["spread"].mean()), 4),
                    "spread_median": round(float(g["spread"].median()), 4),
                    "abs_spread_mean": round(float(g["spread"].abs().mean()), 4),
                }
                bucket_stats.append(row)
                print(f"  pm_yes in [{b:.2f}, {b+0.05:.2f}): "
                      f"n={len(g):>3}  pm_mean={g['pm_yes'].mean():.3f}  "
                      f"sm_mean={g['sm_mid'].mean():.3f}  "
                      f"spread_mean={g['spread'].mean():+.4f}")
        summary["by_pm_price_bucket"] = bucket_stats

    (DATA_DIR / "04_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(f"\nwrote 04_summary.json")


if __name__ == "__main__":
    main()
