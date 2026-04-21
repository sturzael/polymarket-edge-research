"""Cross-venue live spread measurement.

Approach:
1. Pick high-volume Polymarket "head-to-head" sports markets resolving soon
   (NBA/NHL/MLB game winners).
2. For each, extract (team_a, team_b, resolution_date).
3. Search Kalshi and Smarkets inventories for markets matching those teams
   (token-based match on sorted team names) with a nearby resolution date.
4. For each found match, fetch live orderbook on Kalshi/Smarkets to get real
   live price (mid or best-bid) — fetch_markets on those venues returns 0.
5. Compute (Polymarket_yes_price − other_yes_price) for matched team outcome.

Outputs:
- data/03_live_spreads.parquet
- data/03_live_spreads_summary.json
"""
from __future__ import annotations

import json
import re
import time
import traceback
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pmxt

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

STOPWORDS = {
    "vs", "v", "x", "at", "the", "will", "win", "beat", "game", "match", "won",
    "be", "to", "in", "and", "of", "a", "an", "for", "on", "or", "over",
    "under", "who", "wins", "next", "first", "last", "score", "goals",
    "goal", "total", "spread", "moneyline", "ml", "-", "vs.", "set", "round",
    "fight", "tour", "tournament", "champion", "cup",
    "league", "series", "final", "finals", "playoff", "playoffs",
    "nba", "nfl", "mlb", "nhl", "soccer", "football", "basketball",
    "baseball", "hockey", "ice", "new", "st", "ft", "pl", "la",
    # Smarkets suffixes
    "ou", "h2h", "correct", "winner",
}
# Polymarket often uses "City" or short team name; Kalshi/Smarkets use full
# team names. Strip common region/state suffixes to normalize.
STRIP_SUFFIXES = {
    "blazers", "trail",  # Trail Blazers = Portland
    # leave team mascots untouched so they can be matched
}


def tokens(title: str) -> set[str]:
    if not title:
        return set()
    s = title.lower()
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return {t for t in s.split() if t not in STOPWORDS and len(t) >= 3}


def is_head_to_head(title: str) -> bool:
    """Heuristic: 'X vs Y' or 'X at Y' without spread/O-U/prop qualifiers."""
    if not title:
        return False
    t = title.lower()
    # Must contain vs or at
    if " vs" not in t and " at " not in t and " v " not in t:
        return False
    # Reject props/spread/OU
    for bad in ["spread", "o/u", "over/under", "first to", "race to",
                "total", "moneyline", "-1.5", "-2.5", "+1.5", "+0.5",
                "will score", "how many", "player", "mvp"]:
        if bad in t:
            return False
    return True


def yes_price_for_team(market, team_tokens: set[str]) -> float | None:
    """Return the YES-equivalent probability for the outcome whose label
    tokens overlap with team_tokens. Fallback: first outcome."""
    outs = market.outcomes or []
    for o in outs:
        olab_tokens = tokens(o.label or "")
        if olab_tokens & team_tokens:
            if o.price is not None:
                return float(o.price)
    if outs and outs[0].price is not None:
        return float(outs[0].price)
    return None


def ob_mid(ob) -> float | None:
    """Orderbook midpoint from best bid & best ask."""
    if not ob:
        return None
    bid = ob.bids[0].price if ob.bids else None
    ask = ob.asks[0].price if ob.asks else None
    if bid is None and ask is None:
        return None
    if bid is None:
        return ask
    if ask is None:
        return bid
    return (bid + ask) / 2


def ob_price_for_team(client, market, team_tokens: set[str]) -> dict | None:
    """For each outcome matching team_tokens, fetch orderbook.

    Smarkets: orderbook is fetched by market_id + outcome_id (contract).
    Kalshi:   orderbook is fetched by market_id (which IS the outcome).
    Polymarket: orderbook is fetched by clobTokenId (in outcome metadata).

    Strategy: try fetch_order_book(market_id) first; some venues return the
    whole market's book that way.
    """
    # Pick target outcome
    target = None
    for o in market.outcomes or []:
        olab_tokens = tokens(o.label or "")
        if olab_tokens & team_tokens:
            target = o
            break
    if target is None:
        return None
    # Try several argument forms
    attempts = []
    for arg_label, arg in [("market_id", market.market_id),
                            ("outcome_id", target.outcome_id)]:
        try:
            ob = client.fetch_order_book(arg)
            mid = ob_mid(ob)
            return {"outcome_label": target.label,
                    "ob_key": arg_label,
                    "mid": mid,
                    "best_bid": ob.bids[0].price if ob.bids else None,
                    "best_ask": ob.asks[0].price if ob.asks else None,
                    "bid_size": ob.bids[0].size if ob.bids else None,
                    "ask_size": ob.asks[0].size if ob.asks else None}
        except Exception as e:
            attempts.append(f"{arg_label}={arg}: {e}")
    return {"outcome_label": target.label, "error": "; ".join(attempts)}


def main():
    print("=== fetching Polymarket sports markets ===", flush=True)
    pm = pmxt.Polymarket()
    pm_markets = pm.fetch_markets()

    now = datetime.now(timezone.utc)

    # Filter: head-to-head sports, resolving within 7 days, high vol24h
    def resolves_near(rd):
        if rd is None:
            return False
        try:
            r = pd.Timestamp(rd)
            if r.tz is None:
                r = r.tz_localize("UTC")
            delta = (r - pd.Timestamp(now)).total_seconds() / 86400
            return -1 <= delta <= 7  # includes very-recent past (resolution pending)
        except Exception:
            return False

    pm_h2h = [m for m in pm_markets
              if (m.category or "").lower() == "sports"
              and is_head_to_head(m.title or "")
              and resolves_near(m.resolution_date)
              and (m.volume_24h or 0) >= 1000]
    pm_h2h.sort(key=lambda m: -(m.volume_24h or 0))
    print(f"  {len(pm_h2h)} Polymarket head-to-head sports markets "
          f"(vol24h>=1000, resolves within 7d)")
    for m in pm_h2h[:10]:
        print(f"    vol={m.volume_24h:>9.0f}  {m.title[:60]!r}  "
              f"outs={[(o.label, round(o.price, 3)) for o in m.outcomes[:2]]}")

    # Build team-token index per market
    pm_index = []
    for m in pm_h2h:
        # Use ALL market outcome labels as team tokens - each one is a team
        team_labels = [o.label for o in m.outcomes if o.label]
        # For a 2-outcome market: team_a (outcomes[0]) vs team_b (outcomes[1])
        if len(team_labels) < 2:
            continue
        team_a_tokens = tokens(team_labels[0])
        team_b_tokens = tokens(team_labels[1])
        if not team_a_tokens or not team_b_tokens:
            continue
        # The match key is the union of both teams' tokens
        all_tokens = team_a_tokens | team_b_tokens
        pm_index.append({
            "market": m,
            "title": m.title,
            "vol24h": m.volume_24h or 0,
            "rdate": m.resolution_date,
            "team_a": team_labels[0],
            "team_b": team_labels[1],
            "team_a_tokens": team_a_tokens,
            "team_b_tokens": team_b_tokens,
            "all_tokens": all_tokens,
            "yes_a": m.outcomes[0].price,
            "yes_b": m.outcomes[1].price if len(m.outcomes) > 1 else None,
        })

    # === fetch Kalshi + Smarkets inventories ===
    print("\n=== fetching Kalshi sports inventory ===", flush=True)
    ks = pmxt.Kalshi()
    ks_markets = ks.fetch_markets()
    ks_sports = [m for m in ks_markets
                  if (m.category or "").lower() == "sports"
                  and resolves_near(m.resolution_date)]
    # Also include by tags because Kalshi category tagging seems shallow
    ks_sports_ids = {m.market_id for m in ks_sports}
    for m in ks_markets:
        if m.market_id in ks_sports_ids:
            continue
        tagset = [t.lower() for t in (m.tags or [])]
        if any(t in ("sports","basketball","football","baseball","hockey",
                     "soccer","mma","nhl","nba","mlb","nfl") for t in tagset):
            if resolves_near(m.resolution_date):
                ks_sports.append(m)
    # Deduplicate
    seen = set()
    ks_sports_u = []
    for m in ks_sports:
        if m.market_id in seen:
            continue
        seen.add(m.market_id)
        ks_sports_u.append(m)
    ks_sports = ks_sports_u
    print(f"  Kalshi sports near-term: {len(ks_sports)} markets")

    print("\n=== fetching Smarkets sports inventory ===", flush=True)
    sm = pmxt.Smarkets()
    sm_markets = sm.fetch_markets()
    sm_sports = [m for m in sm_markets
                  if (m.category or "").lower() in (
                      "football","basketball","baseball","ice_hockey",
                      "cricket","tennis","american_football","rugby_union",
                      "rugby_league","mma","boxing")
                  and resolves_near(m.resolution_date)
                  and " vs " in (m.title or "").lower()
                  # H2H match winner style market (3 outcomes: home/draw/away
                  # or 2 outcomes: team vs team)
                  and len(m.outcomes) in (2, 3)
                  # Exclude specialty markets by title keyword
                  and not any(bad in (m.title or "").lower() for bad in
                              ["corners", "cards", "shots", "goalscorer",
                               "half time", "correct score", "booking",
                               "first goal", "last goal", "throw",
                               "penalty", "free kick"])]
    print(f"  Smarkets sports near-term H2H: {len(sm_sports)} markets")

    # Build token index for Kalshi and Smarkets
    ks_tok_index = defaultdict(list)
    for m in ks_sports:
        ks_tok_index[frozenset(tokens(m.title))].append(m)
    sm_tok_index = defaultdict(list)
    for m in sm_sports:
        sm_tok_index[frozenset(tokens(m.title))].append(m)

    def find_matches(target_tokens, index):
        """Return markets in index whose token set overlaps target by >=2."""
        out = []
        for tks, ms in index.items():
            overlap = len(tks & target_tokens)
            if overlap >= 2:  # at least 2 team-tokens match
                for m in ms:
                    out.append((overlap, m))
        return sorted(out, key=lambda x: -x[0])

    print("\n=== matching Polymarket h2h to Kalshi/Smarkets ===", flush=True)
    records = []
    t0 = time.time()
    for i, pm_row in enumerate(pm_index):
        pm_m = pm_row["market"]
        key_tokens = pm_row["all_tokens"]
        ks_hits = find_matches(key_tokens, ks_tok_index)
        sm_hits = find_matches(key_tokens, sm_tok_index)
        if not ks_hits and not sm_hits:
            continue
        rec = {
            "pm_title": pm_row["title"],
            "pm_team_a": pm_row["team_a"],
            "pm_team_b": pm_row["team_b"],
            "pm_yes_a": pm_row["yes_a"],
            "pm_yes_b": pm_row["yes_b"],
            "pm_vol24h": pm_row["vol24h"],
            "pm_rdate": str(pm_row["rdate"]),
            "pm_url": pm_m.url,
            "pm_market_id": pm_m.market_id,
        }
        # Best kalshi hit
        if ks_hits:
            _, km = ks_hits[0]
            rec["ks_title"] = km.title
            rec["ks_outcomes"] = str(
                [(o.label, round(o.price, 3)) for o in km.outcomes])
            # Try to fetch live orderbook for team_a outcome
            ks_price = ob_price_for_team(ks, km.outcomes, pm_row["team_a_tokens"])
            rec["ks_price_a"] = ks_price
            rec["ks_url"] = km.url
            rec["ks_market_id"] = km.market_id
        if sm_hits:
            _, sm_mkt = sm_hits[0]
            rec["sm_title"] = sm_mkt.title
            rec["sm_outcomes"] = str(
                [(o.label, round(o.price, 3)) for o in sm_mkt.outcomes])
            sm_price = ob_price_for_team(sm, sm_mkt.outcomes, pm_row["team_a_tokens"])
            rec["sm_price_a"] = sm_price
            rec["sm_url"] = sm_mkt.url
            rec["sm_market_id"] = sm_mkt.market_id
        records.append(rec)
        if (i + 1) % 20 == 0:
            print(f"  progress {i+1}/{len(pm_index)}  matched={len(records)}  "
                  f"({(i+1)/(time.time()-t0):.1f}/s)", flush=True)

    df = pd.DataFrame(records)
    df.to_parquet(DATA_DIR / "03_live_spreads.parquet", index=False)
    print(f"\n{len(df)} matched rows -> 03_live_spreads.parquet")

    if len(df) == 0:
        return

    # Compute spreads
    def get_mid(x):
        if isinstance(x, dict) and "mid" in x:
            return x["mid"]
        return None

    df["ks_mid_a"] = df.get("ks_price_a", pd.Series([None] * len(df))).apply(get_mid)
    df["sm_mid_a"] = df.get("sm_price_a", pd.Series([None] * len(df))).apply(get_mid)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_pm_h2h_candidates": len(pm_index),
        "n_matched_any": int(len(df)),
        "n_matched_kalshi": int(df.get("ks_market_id", pd.Series()).notna().sum()),
        "n_matched_smarkets": int(df.get("sm_market_id", pd.Series()).notna().sum()),
    }

    # Spreads: Polymarket vs Kalshi (team_a price)
    for other, other_mid in [("kalshi", "ks_mid_a"), ("smarkets", "sm_mid_a")]:
        if other_mid not in df.columns:
            continue
        sub = df[df[other_mid].notna() & df["pm_yes_a"].notna()].copy()
        if len(sub) == 0:
            summary[f"pm_vs_{other}"] = {"n": 0}
            continue
        sub["spread"] = sub["pm_yes_a"] - sub[other_mid]
        summary[f"pm_vs_{other}"] = {
            "n": int(len(sub)),
            "mean_spread": round(float(sub["spread"].mean()), 4),
            "median_spread": round(float(sub["spread"].median()), 4),
            "stdev_spread": round(float(sub["spread"].std()), 4),
            "abs_mean_spread": round(float(sub["spread"].abs().mean()), 4),
            "pct_spread_gt_2pp": round(
                float((sub["spread"].abs() > 0.02).mean()), 4),
            "pct_spread_gt_5pp": round(
                float((sub["spread"].abs() > 0.05).mean()), 4),
        }
        print(f"\n=== Polymarket vs {other.capitalize()} ===")
        print(f"  n={len(sub)}  mean={sub['spread'].mean():+.4f}  "
              f"median={sub['spread'].median():+.4f}  "
              f"|mean|={sub['spread'].abs().mean():.4f}  "
              f"%|spread|>2pp={summary[f'pm_vs_{other}']['pct_spread_gt_2pp']:.1%}")
        # Favorite-bucket subset
        fav = sub[(sub["pm_yes_a"] >= 0.55) & (sub["pm_yes_a"] < 0.60)]
        if len(fav):
            summary[f"pm_vs_{other}_fav_0.55_0.60"] = {
                "n": int(len(fav)),
                "pm_mean": round(float(fav["pm_yes_a"].mean()), 4),
                "other_mean": round(float(fav[other_mid].mean()), 4),
                "mean_spread": round(float(fav["spread"].mean()), 4),
            }
            print(f"  favorite bucket (pm 0.55-0.60): n={len(fav)}  "
                  f"pm_mean={fav['pm_yes_a'].mean():.3f}  "
                  f"{other}_mean={fav[other_mid].mean():.3f}  "
                  f"spread={fav['spread'].mean():+.4f}")

    (DATA_DIR / "03_live_spreads_summary.json").write_text(
        json.dumps(summary, indent=2, default=str))
    print(f"\nwrote 03_live_spreads_summary.json")


if __name__ == "__main__":
    main()
