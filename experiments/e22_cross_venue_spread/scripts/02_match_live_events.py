"""Match live sports events across Polymarket, Kalshi, Smarkets.

Strategy:
- Fetch all active sports markets on each venue via pmxt (one call each).
- Normalize titles to a canonical "team token set + resolution date" key.
- Match markets that have the same token set AND resolution_date within 24h.
- For each match, record YES-equivalent price on each venue + spread.

Why tokens-plus-date (not fuzzy string match): team names are stable, dates
are stable, everything else (market prefix, format) is venue-specific noise.

Outputs:
- data/02_pm_sports.parquet   (raw Polymarket sports markets)
- data/02_ks_sports.parquet   (raw Kalshi sports markets)
- data/02_sm_sports.parquet   (raw Smarkets sports markets)
- data/02_matches.parquet     (matched triples/pairs with prices)
- data/02_matches_summary.json
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
import pmxt

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Noise tokens to strip from titles before tokenizing team names
STOPWORDS = {
    "vs", "v", "x", "at", "the", "will", "win", "beat", "game", "match", "won",
    "be", "to", "in", "and", "of", "a", "an", "for", "on", "or", "over",
    "under", "who", "wins", "next", "first", "last", "score", "goals",
    "goal", "total", "spread", "moneyline", "ml", "-", "vs.", "set", "round",
    "fight", "round-robin", "tour", "tournament", "champion", "cup",
    "league", "series", "final", "finals", "playoff", "playoffs",
}

SPORTS_KEYWORDS = [
    "nba", "nfl", "mlb", "nhl", "ufc", "premier", "laliga", "la-liga",
    "bundesliga", "serie", "ligue", "champions", "europa", "mls", "cricket",
    "boxing", "tennis", "atp", "wta",
]


def tokenize(title: str) -> set[str]:
    """Split a market title into a canonical set of 'team tokens'."""
    if not title:
        return set()
    s = title.lower()
    # Remove common venue-prefix junk
    s = re.sub(r"\(.*?\)", " ", s)  # drop parentheticals
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    tokens = [t for t in s.split() if t not in STOPWORDS and len(t) >= 3]
    return set(tokens)


def yes_price(market) -> float | None:
    """Extract YES-equivalent price from a UnifiedMarket."""
    if getattr(market, "yes", None) is not None:
        p = market.yes.price
        if p is not None and 0 < p < 1:
            return float(p)
    outs = getattr(market, "outcomes", None) or []
    if outs:
        # Use first outcome as YES-equivalent (best-effort for 2-outcome markets)
        for o in outs:
            lab = (getattr(o, "label", None) or "").lower()
            if lab in ("yes", "y"):
                if o.price is not None:
                    return float(o.price)
        # First outcome fallback
        if outs[0].price is not None:
            return float(outs[0].price)
    return None


def is_sports(market) -> bool:
    cat = (market.category or "").lower()
    tags_lower = [t.lower() for t in (market.tags or [])]
    if "sport" in cat:
        return True
    if any("sport" in t for t in tags_lower):
        return True
    title = (market.title or "").lower()
    for kw in SPORTS_KEYWORDS:
        if kw in title:
            return True
    # Smarkets uses football/basketball/etc. as the category itself
    if cat in ("football", "basketball", "baseball", "ice_hockey",
               "cricket", "tennis", "rugby_union", "rugby_league",
               "american_football", "golf", "ufc", "boxing"):
        return True
    return False


def extract_markets(venue_name: str, client) -> pd.DataFrame:
    """Fetch & flatten a venue's market list into a DataFrame."""
    print(f"  {venue_name}: fetch_markets...", flush=True)
    markets = client.fetch_markets()
    print(f"  {venue_name}: got {len(markets)}", flush=True)
    rows = []
    for m in markets:
        if not is_sports(m):
            continue
        rd = getattr(m, "resolution_date", None)
        rows.append({
            "venue": venue_name,
            "market_id": m.market_id,
            "title": m.title,
            "slug": getattr(m, "slug", None),
            "url": getattr(m, "url", None),
            "category": m.category,
            "tags": list(m.tags or []),
            "yes_price": yes_price(m),
            "volume_24h": float(getattr(m, "volume_24h", 0) or 0),
            "liquidity": float(getattr(m, "liquidity", 0) or 0),
            "status": getattr(m, "status", None),
            "resolution_date": rd,
            "tokens": tokenize(m.title),
        })
    df = pd.DataFrame(rows)
    print(f"  {venue_name}: {len(df)} sports-filtered markets", flush=True)
    return df


def match_across(dfs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Given {venue_name: df}, match by (sorted-token-tuple, resolution_date_bucket).

    We bucket resolution_date by the UTC date (day-granularity) because small
    time offsets between venues are common even for the exact same event.
    """
    # Build index: venue -> {(tokens_tuple, date_str) -> list of rows}
    indexed = defaultdict(lambda: defaultdict(list))
    for venue, df in dfs.items():
        for _, r in df.iterrows():
            toks = r["tokens"]
            if len(toks) < 2:
                continue
            rd = r["resolution_date"]
            if rd is None or pd.isna(rd):
                continue
            try:
                rd = pd.Timestamp(rd)
                if rd.tz is None:
                    rd = rd.tz_localize("UTC")
                date_key = rd.strftime("%Y-%m-%d")
            except Exception:
                continue
            key = (tuple(sorted(toks)), date_key)
            indexed[venue][key].append(r)

    # Union of keys across all venues
    all_keys = set()
    for v in indexed.values():
        all_keys.update(v.keys())

    matched = []
    for key in all_keys:
        present = {v: rows for v, rows in
                   [(v, indexed[v].get(key, [])) for v in dfs.keys()] if rows}
        if len(present) < 2:
            continue
        # Pick the highest-volume row per venue
        row_per_venue = {}
        for v, rows in present.items():
            rows_sorted = sorted(rows, key=lambda r: -(r.get("volume_24h") or 0))
            row_per_venue[v] = rows_sorted[0]
        rec = {
            "tokens": " ".join(key[0]),
            "date": key[1],
            "n_venues": len(present),
            "venues": ",".join(sorted(present.keys())),
        }
        for v, r in row_per_venue.items():
            rec[f"{v}_title"] = r["title"]
            rec[f"{v}_yes"] = r["yes_price"]
            rec[f"{v}_vol24h"] = r["volume_24h"]
            rec[f"{v}_url"] = r["url"]
            rec[f"{v}_market_id"] = r["market_id"]
        matched.append(rec)
    return pd.DataFrame(matched)


def main():
    print("fetching venue inventories...")
    dfs = {}

    for name, cls in [("polymarket", pmxt.Polymarket),
                       ("kalshi", pmxt.Kalshi),
                       ("smarkets", pmxt.Smarkets)]:
        try:
            client = cls()
            df = extract_markets(name, client)
            df_save = df.drop(columns=["tokens"]).copy()
            df_save["tags"] = df_save["tags"].apply(
                lambda xs: ",".join(xs) if isinstance(xs, list) else "")
            df_save.to_parquet(DATA_DIR / f"02_{name[:2]}_sports.parquet", index=False)
            dfs[name] = df
        except Exception as e:
            print(f"  ERROR fetching {name}: {e}")

    matches = match_across(dfs)
    # For parquet, tokens column is a string (space-joined), which is fine
    matches.to_parquet(DATA_DIR / "02_matches.parquet", index=False)

    print(f"\n{len(matches)} matched event rows across {len(dfs)} venues")
    if len(matches):
        # Distribution of how many venues each match covers
        by_n = matches["n_venues"].value_counts().sort_index().to_dict()
        print(f"  n_venues histogram: {by_n}")

        # Pairwise spreads
        summary = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "n_matches_total": int(len(matches)),
            "by_n_venues": {int(k): int(v) for k, v in by_n.items()},
        }
        pairs = [("polymarket", "kalshi"),
                  ("polymarket", "smarkets"),
                  ("kalshi", "smarkets")]
        for a, b in pairs:
            ya, yb = f"{a}_yes", f"{b}_yes"
            if ya not in matches.columns or yb not in matches.columns:
                continue
            sub = matches[matches[ya].notna() & matches[yb].notna()].copy()
            if len(sub) == 0:
                summary[f"spread_{a}_vs_{b}"] = {"n": 0}
                continue
            sub["spread"] = sub[ya] - sub[yb]
            summary[f"spread_{a}_vs_{b}"] = {
                "n": int(len(sub)),
                "mean_spread": round(float(sub["spread"].mean()), 4),
                "median_spread": round(float(sub["spread"].median()), 4),
                "stdev_spread": round(float(sub["spread"].std()), 4),
                "abs_mean_spread": round(float(sub["spread"].abs().mean()), 4),
                "pct_spread_gt_5pp": round(
                    float((sub["spread"].abs() > 0.05).mean()), 4),
            }
            print(f"\n  {a} vs {b}: n={len(sub)}  "
                  f"mean_spread={sub['spread'].mean():+.4f}  "
                  f"median={sub['spread'].median():+.4f}  "
                  f"|mean|={sub['spread'].abs().mean():.4f}")
            # Subset where polymarket price is in favorite bucket (0.55-0.60)
            if a == "polymarket":
                fav = sub[(sub[ya] >= 0.55) & (sub[ya] < 0.60)]
                if len(fav):
                    print(f"    favorite bucket (0.55-0.60 on pm): n={len(fav)}  "
                          f"other-venue mean price={fav[yb].mean():.3f}  "
                          f"mean spread={fav['spread'].mean():+.4f}")
                    summary[f"spread_{a}_vs_{b}_fav_0.55_0.60"] = {
                        "n": int(len(fav)),
                        "pm_mean_price": round(float(fav[ya].mean()), 4),
                        "other_mean_price": round(float(fav[yb].mean()), 4),
                        "mean_spread": round(float(fav["spread"].mean()), 4),
                    }

        (DATA_DIR / "02_matches_summary.json").write_text(
            json.dumps(summary, indent=2, default=str))
        print(f"\nwrote {DATA_DIR}/02_matches.parquet "
              f"and 02_matches_summary.json")


if __name__ == "__main__":
    main()
