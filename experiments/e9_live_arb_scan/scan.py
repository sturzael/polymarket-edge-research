"""Repeatable live-arb scan.

For each run, looks at all currently-active Polymarket markets in selected
categories (crypto barriers, sports, entertainment, politics, etc.),
identifies those where the outcome is economically determined, measures
whether there's executable depth on the winning side at ask < 0.99.

Appends each run as one JSON line to `runs.jsonl`.

Usage:
    uv run python experiments/e9_live_arb_scan/scan.py
    uv run python experiments/e9_live_arb_scan/scan.py --categories sports,crypto_barrier

Schedule from a shell (runs every 4 hours for the next 24h):
    for i in {1..6}; do
      uv run python experiments/e9_live_arb_scan/scan.py;
      sleep 14400;
    done
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

OUT = Path(__file__).parent / "runs.jsonl"


CATEGORY_FILTERS = {
    # Slug substrings that identify each category
    "crypto_barrier": {
        "required_any": ["-reach-", "-dip-to-", "-hit-", "-above-", "-below-"],
        "required_any2": ["bitcoin", "ethereum", "solana", "btc", "eth", "sol", "xrp", "doge", "bnb"],
    },
    "sports": {
        "required_any": ["atp-", "wta-", "nba-", "nfl-", "nhl-", "mlb-", "cricipl-", "ufc-", "mls-", "wnba-"],
    },
    "politics": {
        # Political event markets - executive orders, Congress, court, elections
        "required_any": ["executive-order", "congress", "supreme-court", "scotus", "secretary", "confirmation", "bill-", "senate", "house-vote", "nominate", "impeach"],
    },
    "entertainment": {
        # Entertainment / social-culture markets
        "required_any": ["oscar", "grammy", "chart-topping", "billboard", "netflix", "album", "movie", "concert", "taylor-swift", "kanye", "celebrity"],
    },
}


async def pull_all_active(session: aiohttp.ClientSession, max_pages: int = 40) -> list[dict]:
    out: list[dict] = []
    for off in range(0, max_pages * 200, 200):
        async with session.get(
            "https://gamma-api.polymarket.com/markets",
            params={"closed": "false", "active": "true", "limit": "200", "offset": str(off),
                    "order": "endDate", "ascending": "true"},
        ) as r:
            if r.status != 200:
                break
            d = await r.json()
            if not d:
                break
            out.extend(d)
            if len(d) < 200:
                break
    return out


def matches_category(slug: str, cat: str) -> bool:
    filt = CATEGORY_FILTERS[cat]
    if not any(k in slug for k in filt["required_any"]):
        return False
    if "required_any2" in filt:
        if not any(k in slug for k in filt["required_any2"]):
            return False
    return True


async def check_market(session: aiohttp.ClientSession, m: dict) -> dict | None:
    """Returns arb-opportunity dict if executable arb exists at ask<0.99; else None."""
    last = m.get("lastTradePrice")
    if last is None:
        return None
    last = float(last)
    # only economically-certain markets
    if 0.05 < last < 0.95:
        return None
    cid = m["conditionId"]
    try:
        async with session.get(
            f"https://clob.polymarket.com/markets/{cid}",
            timeout=aiohttp.ClientTimeout(total=8),
        ) as r:
            if r.status != 200:
                return None
            mkt = await r.json()
    except Exception:
        return None
    tokens = mkt.get("tokens", [])
    yes_tok = next((t for t in tokens if (t.get("outcome") or "").lower() in ("yes", "up")), None)
    no_tok = next((t for t in tokens if (t.get("outcome") or "").lower() in ("no", "down")), None)
    if not yes_tok or not no_tok:
        return None
    # infer winner from last_trade_price direction
    if last < 0.05:
        win_tok = no_tok; win_side = "NO"
    else:
        win_tok = yes_tok; win_side = "YES"
    try:
        async with session.get(
            "https://clob.polymarket.com/book",
            params={"token_id": str(win_tok["token_id"])},
            timeout=aiohttp.ClientTimeout(total=8),
        ) as r:
            if r.status != 200:
                return None
            book = await r.json()
    except Exception:
        return None
    asks = book.get("asks", [])
    if not asks:
        return None
    best_ask = min(float(l["price"]) for l in asks)
    cheap_at_97 = sum(float(l["price"]) * float(l["size"]) for l in asks if float(l["price"]) < 0.97)
    cheap_at_99 = sum(float(l["price"]) * float(l["size"]) for l in asks if float(l["price"]) < 0.99)
    return {
        "slug": m.get("slug"),
        "win_side": win_side,
        "best_ask": best_ask,
        "capture_below_0_97": round(cheap_at_97, 2),
        "capture_below_0_99": round(cheap_at_99, 2),
        "vol_24h": float(m.get("volume24hr") or 0),
    }


async def scan_once(session: aiohttp.ClientSession, categories: list[str]) -> dict:
    all_m = await pull_all_active(session)
    now = datetime.now(timezone.utc)
    by_cat: dict[str, list] = {c: [] for c in categories}
    for m in all_m:
        slug = (m.get("slug") or "").lower()
        end = m.get("endDate")
        if not end:
            continue
        try:
            hrs = (datetime.fromisoformat(end.replace("Z", "+00:00")) - now).total_seconds() / 3600
        except Exception:
            continue
        if hrs <= 0:
            continue
        for c in categories:
            if matches_category(slug, c):
                by_cat[c].append(m)
                break
    # For each category, check markets for live arb opps
    cat_results: dict[str, dict] = {}
    for c, ms in by_cat.items():
        arbs = []
        certain_count = 0
        for m in ms:
            last = m.get("lastTradePrice")
            if last is None:
                continue
            last = float(last)
            if last < 0.05 or last > 0.95:
                certain_count += 1
            res = await check_market(session, m)
            if res and res["best_ask"] < 0.99 and res["capture_below_0_99"] > 20:
                arbs.append(res)
        cat_results[c] = {
            "n_active": len(ms),
            "n_economic_certainty": certain_count,
            "n_executable_arbs": len(arbs),
            "arbs": sorted(arbs, key=lambda x: -x["capture_below_0_99"])[:10],
            "total_capture_below_0_99": round(sum(a["capture_below_0_99"] for a in arbs), 2),
            "total_capture_below_0_97": round(sum(a["capture_below_0_97"] for a in arbs), 2),
        }
    return {
        "run_at": now.isoformat(),
        "total_active_markets_scanned": len(all_m),
        "per_category": cat_results,
    }


async def amain(args):
    cats = args.categories.split(",") if args.categories else list(CATEGORY_FILTERS.keys())
    async with aiohttp.ClientSession(headers={"User-Agent": "e9-live-arb-scan/0.1"}) as s:
        result = await scan_once(s, cats)
    with OUT.open("a") as f:
        f.write(json.dumps(result) + "\n")
    # Print summary
    print(f"[{result['run_at']}] scanned {result['total_active_markets_scanned']} active markets")
    for c, r in result["per_category"].items():
        print(f"  {c:17s}: {r['n_active']:4d} active / {r['n_economic_certainty']:3d} certainty / "
              f"{r['n_executable_arbs']:2d} arbs / ${r['total_capture_below_0_99']:>8,.0f} capture<0.99 "
              f"/ ${r['total_capture_below_0_97']:>8,.0f} capture<0.97")
        for a in r["arbs"][:3]:
            print(f"    arb: {a['slug'][:50]:50s} side={a['win_side']} ask={a['best_ask']:.3f} "
                  f"${a['capture_below_0_99']:,.0f}@<0.99")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--categories", default=None, help="comma-separated: crypto_barrier,sports,politics,entertainment")
    args = p.parse_args()
    asyncio.run(amain(args))


if __name__ == "__main__":
    main()
