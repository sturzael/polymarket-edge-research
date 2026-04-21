"""Inventory sports markets on each venue pmxt supports.

Goal: catalog how many sports-category markets each venue is currently exposing
so we know which venues have enough overlap with Polymarket to meaningfully
measure cross-venue spreads.

Venues inspected (via pmxt): Polymarket, Kalshi, Limitless, Baozi, Myriad,
Opinion, Probable, Smarkets, Metaculus.

Output: data/01_venue_inventory.json — per-venue counts, category breakdown,
sample market titles.
"""
from __future__ import annotations

import json
import traceback
from datetime import datetime, timezone
from pathlib import Path

import pmxt

OUT = Path(__file__).parent.parent / "data" / "01_venue_inventory.json"

VENUE_CLASSES = {
    "polymarket": pmxt.Polymarket,
    "kalshi": pmxt.Kalshi,
    "limitless": pmxt.Limitless,
    "baozi": pmxt.Baozi,
    "myriad": pmxt.Myriad,
    "opinion": pmxt.Opinion,
    "probable": pmxt.Probable,
    "smarkets": pmxt.Smarkets,
    "metaculus": pmxt.Metaculus,
}


def summarize(markets):
    cats = {}
    tags = {}
    for m in markets:
        cats[m.category or "None"] = cats.get(m.category or "None", 0) + 1
        if m.tags:
            for t in m.tags:
                tags[t] = tags.get(t, 0) + 1
    return {
        "n_markets": len(markets),
        "categories_top10": sorted(cats.items(), key=lambda kv: -kv[1])[:10],
        "tags_top10": sorted(tags.items(), key=lambda kv: -kv[1])[:10],
        "sample_titles": [m.title for m in markets[:15]],
    }


def main():
    result = {"generated_at": datetime.now(timezone.utc).isoformat(),
              "venues": {}}

    for name, cls in VENUE_CLASSES.items():
        print(f"\n=== {name} ===", flush=True)
        try:
            client = cls()
            # Try to fetch current markets (active only if the API supports)
            t0 = datetime.now()
            markets = client.fetch_markets()
            dt = (datetime.now() - t0).total_seconds()
            print(f"  fetched {len(markets)} markets in {dt:.1f}s")
            summary = summarize(markets)
            summary["fetch_seconds"] = round(dt, 2)
            # Try specifically sports filter
            try:
                sports = client.filter_markets(
                    markets, pmxt.MarketFilterCriteria(text="", category="sports"))
                summary["n_sports_category"] = len(sports)
            except Exception as e:
                summary["sports_filter_error"] = str(e)
            # Free-text: nba, nfl, football, soccer
            for kw in ["nba", "nfl", "premier league", "soccer", "football",
                       "mlb", "nhl", "tennis", "ufc", "boxing"]:
                try:
                    hits = client.filter_markets(markets, kw)
                    summary[f"kw_{kw}"] = len(hits)
                except Exception:
                    pass
            result["venues"][name] = summary
        except Exception as e:
            print(f"  ERROR: {e}")
            result["venues"][name] = {
                "error": str(e),
                "traceback": traceback.format_exc().splitlines()[-4:],
            }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, default=str))
    print(f"\nwrote {OUT}")

    # Concise table
    print("\n=== Summary ===")
    print(f"{'venue':<15} {'n_total':>8} {'n_sports':>9}  sample title")
    for name, v in result["venues"].items():
        if "error" in v:
            print(f"{name:<15} ERROR: {v['error'][:60]}")
        else:
            sample = v["sample_titles"][0][:50] if v["sample_titles"] else ""
            print(f"{name:<15} {v['n_markets']:>8} "
                  f"{v.get('n_sports_category', '-'):>9}  {sample}")


if __name__ == "__main__":
    main()
