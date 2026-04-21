"""Markets.parquet audit — derive category + resolution outcome per market.

Writes data/01_markets_audit.parquet with columns:
    condition_id, slug, event_slug, category, resolved, resolution,
    volume, created_at_ts, end_date_ts, token1, token2, neg_risk

Category derivation is heuristic from slug patterns. Confusions logged.

Inputs:
    ../e13_external_repo_audit/data/hf_cache/.../markets.parquet (734k rows)

Output:
    data/01_markets_audit.parquet
    data/01_audit_summary.json
"""
from __future__ import annotations

import ast
import json
import re
import sys
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq
import pandas as pd

E13_DATA = Path(__file__).resolve().parents[1] / "e13_external_repo_audit" / "data" / "hf_cache"
DATA_DIR = Path(__file__).parent / "data"
OUT_PARQUET = DATA_DIR / "01_markets_audit.parquet"
OUT_JSON = DATA_DIR / "01_audit_summary.json"


# Heuristic category rules. Order matters: first match wins.
CATEGORY_RULES = [
    ("sports_nfl",    re.compile(r"\b(nfl|super[-_ ]?bowl|afc|nfc|packers|49ers|cowboys|eagles|ravens|chiefs)\b", re.I)),
    ("sports_nba",    re.compile(r"\b(nba|warriors|celtics|lakers|bucks|nets|knicks|suns|heat|thunder|mavericks|raptors|sixers|pacers|bulls)\b|\bnba-\w+|-nba-", re.I)),
    ("sports_mlb",    re.compile(r"\b(mlb|world[-_ ]?series|yankees|dodgers|red[-_ ]?sox|astros|mets|phillies|braves|rays|cubs)\b", re.I)),
    ("sports_nhl",    re.compile(r"\b(nhl|stanley[-_ ]?cup|bruins|leafs|avalanche|oilers|canadiens)\b", re.I)),
    ("sports_soccer", re.compile(r"\b(epl|premier[-_ ]?league|la[-_ ]?liga|uefa|champions[-_ ]?league|europa|bundesliga|serie[-_ ]?a|mls|fifa|world[-_ ]?cup|man[-_ ]?(u|city)|liverpool|arsenal|real[-_ ]?madrid|barcelona|psg|bayern|juventus|chelsea|spurs)\b", re.I)),
    ("sports_ufc_boxing", re.compile(r"\b(ufc|mma|boxing|fighter|paul[-_ ]?vs|fury[-_ ]?vs)\b", re.I)),
    ("sports_tennis", re.compile(r"\b(tennis|atp|wta|djokovic|alcaraz|sinner|us[-_ ]?open|wimbledon|french[-_ ]?open|australian[-_ ]?open)\b", re.I)),
    ("sports_f1",     re.compile(r"\b(formula[-_ ]?1|f1[-_ ]?|verstappen|hamilton|leclerc|norris|piastri|grand[-_ ]?prix)\b", re.I)),
    ("crypto_btc",    re.compile(r"\b(bitcoin|btc)[-_ ]", re.I)),
    ("crypto_eth",    re.compile(r"\b(ethereum|eth)[-_ ]", re.I)),
    ("crypto_other",  re.compile(r"\b(sol|ada|xrp|doge|pepe|shib|bnb|avax|crypto|solana|cardano)\b", re.I)),
    ("politics_us",   re.compile(r"\b(trump|biden|harris|desantis|vance|pence|musk[-_ ](for|elected)|congress|senate|house|speaker|impeach|pardon|nominate|supreme[-_ ]court|scotus|election|president|governor|primary|democrat|republican|gop|dem[-_ ]?primary)\b", re.I)),
    ("politics_world", re.compile(r"\b(putin|zelenskyy?|xi[-_ ](jinping|to)|merkel|macron|trudeau|uk[-_ ](pm|election)|india|modi|netanyahu|erdogan|maduro|milei|ceasefire|nato|china[-_ ]|russia[-_ ]|ukraine|iran|israel|gaza|hezbollah|hamas)\b", re.I)),
    ("econ_fed_rates", re.compile(r"\b(fed[-_ ]?(rate|decision|chair)|fomc|jerome[-_ ]?powell|rate[-_ ]?cut|rate[-_ ]?hike|interest[-_ ]rate|cpi|inflation|gdp|unemployment)\b", re.I)),
    ("econ_stocks",   re.compile(r"\b(s&p|spx|sp500|nasdaq|dow|stock[-_ ]?market|aapl|googl|msft|tsla|nvda|meta|amzn|market[-_ ]close)\b", re.I)),
    ("weather",       re.compile(r"\b(temperature|rainfall|precipitation|snowfall|wildfire|heat[-_ ]?wave|hurricane[-_ ](season|category|make)|cold[-_ ]?snap|typhoon|cyclone|tornado|monsoon|blizzard|drought|celsius|fahrenheit|global[-_ ]temperature)\b", re.I)),
    ("awards_entertainment", re.compile(r"\b(oscar|emmy|grammy|nobel|mvp|rookie[-_ ]of[-_ ]the[-_ ]year|golden[-_ ]globe|palme|cannes|eurovision|taylor[-_ ]?swift|beyonce|next[-_ ]james[-_ ]bond)\b", re.I)),
    ("tech_ai",       re.compile(r"\b(openai|anthropic|gpt|claude|gemini|llama|ai[-_ ]model|llm|agi|sam[-_ ]?altman|apple[-_ ]ai)\b", re.I)),
    ("aviation_mil",  re.compile(r"\b(aircraft|plane[-_ ]?crash|missile|nuclear[-_ ]?weapon|drone[-_ ]?strike|space[-_ ]?x|starship|artemis|nasa)\b", re.I)),
]


def find_markets_parquet() -> Path:
    for p in E13_DATA.rglob("markets.parquet"):
        return p
    raise FileNotFoundError("markets.parquet not cached in e13 hf_cache")


def categorize(slug: str, question: str, event_slug: str) -> str:
    text = f"{slug} {question} {event_slug}".lower()
    for label, pattern in CATEGORY_RULES:
        if pattern.search(text):
            return label
    return "other"


def parse_outcome_prices(raw) -> tuple[float, float] | None:
    if raw is None:
        return None
    s = raw if isinstance(raw, str) else (raw.decode() if isinstance(raw, bytes) else None)
    if not s:
        return None
    try:
        v = ast.literal_eval(s)
        if isinstance(v, (list, tuple)) and len(v) == 2:
            return (float(v[0]), float(v[1]))
    except Exception:
        return None
    return None


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    src = find_markets_parquet()
    print(f"reading {src}")

    # Read only columns we need
    cols = ["condition_id", "slug", "question", "event_slug",
            "closed", "active", "outcome_prices", "volume",
            "created_at", "end_date", "token1", "token2", "neg_risk"]
    df = pd.read_parquet(src, columns=cols)
    n0 = len(df)
    print(f"  {n0:,} markets")

    # Decode byte columns
    for c in ("condition_id", "slug", "question", "event_slug",
              "outcome_prices", "token1", "token2"):
        if df[c].dtype == object:
            df[c] = df[c].apply(lambda x: x.decode() if isinstance(x, bytes) else x)

    # Category
    print("categorizing...")
    df["category"] = [
        categorize(s or "", q or "", e or "")
        for s, q, e in zip(df["slug"], df["question"], df["event_slug"])
    ]

    # Resolution: 'resolved' if closed and outcome_prices is a clean [1,0] or [0,1]
    print("resolving...")
    resolutions = []
    resolved_flags = []
    for raw, closed in zip(df["outcome_prices"], df["closed"]):
        op = parse_outcome_prices(raw)
        if closed and op is not None:
            if op[0] == 1.0 and op[1] == 0.0:
                resolutions.append("YES")
                resolved_flags.append(True)
            elif op[0] == 0.0 and op[1] == 1.0:
                resolutions.append("NO")
                resolved_flags.append(True)
            else:
                resolutions.append(None)
                resolved_flags.append(False)
        else:
            resolutions.append(None)
            resolved_flags.append(False)
    df["resolved"] = resolved_flags
    df["resolution"] = resolutions

    cat_counts = Counter(df["category"])
    resolved = df[df["resolved"]]
    cat_res_counts = Counter(resolved["category"])

    # YES rate per category
    yes_rates = {}
    for cat in cat_counts:
        sub = resolved[resolved["category"] == cat]
        if len(sub) >= 30:
            yes_rates[cat] = {
                "n_resolved": len(sub),
                "yes_rate": float((sub["resolution"] == "YES").mean()),
            }

    # Volume distributions per category
    vol_stats = {}
    for cat in cat_counts:
        sub = df[df["category"] == cat]
        vols = sub["volume"].dropna().astype(float)
        if len(vols) > 0:
            vol_stats[cat] = {
                "n": int(len(vols)),
                "p50": float(vols.median()),
                "p90": float(vols.quantile(0.9)),
                "total": float(vols.sum()),
            }

    # Save filtered parquet (resolved + has-both-tokens only) for downstream price lookup
    ready = df[
        df["resolved"]
        & df["token1"].notna() & (df["token1"] != "")
        & df["token2"].notna() & (df["token2"] != "")
    ][["condition_id", "slug", "event_slug", "category", "resolution",
       "volume", "created_at", "end_date", "token1", "token2", "neg_risk"]].copy()
    print(f"  {len(ready):,} resolved markets with both tokens (→ ready for price lookup)")
    ready.to_parquet(OUT_PARQUET, index=False)

    summary = {
        "n_markets_total": n0,
        "n_resolved": int(df["resolved"].sum()),
        "n_ready_for_price_lookup": int(len(ready)),
        "by_category_count": dict(cat_counts),
        "by_category_resolved_count": dict(cat_res_counts),
        "by_category_yes_rate": yes_rates,
        "by_category_volume": vol_stats,
    }
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str))

    print(f"\n=== MARKETS AUDIT ===")
    print(f"  total markets:     {n0:,}")
    print(f"  resolved:          {int(df['resolved'].sum()):,}")
    print(f"  ready for price:   {len(ready):,}")
    print(f"\n  TOP 20 CATEGORIES (by count):")
    for cat, n in cat_counts.most_common(20):
        yes = yes_rates.get(cat, {}).get("yes_rate")
        yes_str = f"  yes={yes:.3f}" if yes is not None else ""
        v = vol_stats.get(cat, {})
        print(f"    {cat:<24} n={n:>7,}  resolved={cat_res_counts.get(cat,0):>6,}"
              f"{yes_str}  vol_p50=${v.get('p50',0):>10,.0f}")
    print(f"\n  wrote {OUT_PARQUET} and {OUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
