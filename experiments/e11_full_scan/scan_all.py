"""Scan every active Polymarket market for two edge types:

  1. Tail-insurance: winning side ask < 0.99 on economically-certain markets (last ≥ 0.95 or ≤ 0.05)
  2. Pair-sum arb: YES_ask + NO_ask < 1.00 (dump-and-hedge)

Categorizes findings by topic. Reports total capturable notional per category.

Usage: uv run python experiments/e11_full_scan/scan_all.py [--max-books N]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import aiohttp


OUT_DIR = Path(__file__).parent
OUT_DIR.mkdir(parents=True, exist_ok=True)


CATEGORY_RULES = [
    # (category_name, list of slug/question substrings that match)
    ("crypto_barrier",     ["-reach-", "-dip-to-", "-hit-"], ["bitcoin","ethereum","solana","btc","eth","sol","xrp","doge","bnb","crypto"]),
    ("crypto_ladder",      ["-above-","-below-","-between-"], ["bitcoin","ethereum","solana","btc","eth","sol","xrp","doge","bnb"]),
    ("crypto_updown",      ["-updown-","-up-or-down-"], ["bitcoin","ethereum","solana","btc","eth","sol","xrp","doge","bnb"]),
    ("sports",             ["atp-","wta-","nba-","nfl-","nhl-","mlb-","mls-","cricipl-","wnba-","ufc-","fifa-","epl-","champions-league","-vs-"], None),
    ("weather",            ["weather","temperature","rain","snow","hurricane","sunny","highest-temp","lowest-temp"], None),
    ("politics",           ["trump","biden","harris","senate","congress","supreme-court","scotus","executive-order","bill-","impeach","nominate","confirmation","election","president","vote-"], None),
    ("entertainment",      ["oscar","grammy","billboard","netflix","movie","album","concert","taylor-swift","celebrity","emmy","tony-awards","mtv"], None),
    ("stocks_econ",        ["nasdaq","sp500","dow","stock","tesla","nvidia","apple","meta","fed-","jobs-report","cpi","inflation","gdp","unemployment"], None),
    ("tech",               ["openai","anthropic","gpt","claude","agi","ai-","model-release","product-launch","gpt-5","gpt-6","tesla","spacex","nvidia-"], None),
    ("geopolitics",        ["russia","ukraine","china","israel","iran","nato","war","peace-deal","ceasefire","sanctions"], None),
]


def categorize(slug: str, question: str) -> str:
    text = f"{slug} {question or ''}".lower()
    for cat, positive, secondary in CATEGORY_RULES:
        if any(p in text for p in positive):
            if secondary is None or any(s in text for s in secondary):
                return cat
    return "other"


async def pull_all_active(session: aiohttp.ClientSession, max_pages: int = 50) -> list[dict]:
    out: list[dict] = []
    for off in range(0, max_pages * 200, 200):
        try:
            async with session.get(
                "https://gamma-api.polymarket.com/markets",
                params={"closed": "false", "active": "true", "limit": "200",
                        "offset": str(off), "order": "endDate", "ascending": "true"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                if r.status != 200:
                    break
                d = await r.json()
        except Exception:
            break
        if not d:
            break
        out.extend(d)
        if len(d) < 200:
            break
    return out


def filter_candidates(markets: list[dict]) -> list[dict]:
    """Return markets that are:
       - economically certain (last_trade > 0.95 or < 0.05) for tail-insurance check
       - OR have best_bid + best_ask < 1.05 (pair-sum hint; loose threshold)
       with a sensible end_ts and binary structure.
    """
    now = datetime.now(timezone.utc)
    out: list[dict] = []
    for m in markets:
        end = m.get("endDate")
        if not end:
            continue
        try:
            hrs = (datetime.fromisoformat(end.replace("Z", "+00:00")) - now).total_seconds() / 3600
        except Exception:
            continue
        if hrs <= 0:
            continue
        if hrs > 168:  # more than 1 week out; unlikely to be immediately actionable
            continue
        last = m.get("lastTradePrice")
        bb = m.get("bestBid")
        ba = m.get("bestAsk")
        certainty_candidate = last is not None and (float(last) >= 0.95 or float(last) <= 0.05)
        pair_sum_candidate = (bb is not None and ba is not None and
                              float(bb) + float(ba) < 1.05)
        if certainty_candidate or pair_sum_candidate:
            out.append({"m": m, "hrs": hrs, "last": last, "bb": bb, "ba": ba,
                        "certainty": certainty_candidate, "pair_sum_hint": pair_sum_candidate})
    return out


async def fetch_book(session: aiohttp.ClientSession, token_id: str) -> dict | None:
    try:
        async with session.get(
            "https://clob.polymarket.com/book",
            params={"token_id": str(token_id)},
            timeout=aiohttp.ClientTimeout(total=8),
        ) as r:
            if r.status != 200:
                return None
            return await r.json()
    except Exception:
        return None


async def fetch_market(session: aiohttp.ClientSession, cid: str) -> dict | None:
    try:
        async with session.get(
            f"https://clob.polymarket.com/markets/{cid}",
            timeout=aiohttp.ClientTimeout(total=8),
        ) as r:
            if r.status != 200:
                return None
            return await r.json()
    except Exception:
        return None


async def analyze_candidate(session, c) -> dict:
    m = c["m"]
    cid = m.get("conditionId")
    if not cid:
        return {}
    mkt = await fetch_market(session, cid)
    if not mkt:
        return {}
    tokens = mkt.get("tokens", [])
    yes = next((t for t in tokens if (t.get("outcome") or "").lower() in ("yes", "up")), None)
    no = next((t for t in tokens if (t.get("outcome") or "").lower() in ("no", "down")), None)
    if not yes or not no:
        return {}

    book_y = await fetch_book(session, str(yes["token_id"]))
    book_n = await fetch_book(session, str(no["token_id"]))
    if not book_y or not book_n:
        return {}

    y_asks = book_y.get("asks", [])
    n_asks = book_n.get("asks", [])

    result = {
        "slug": m.get("slug"),
        "question": m.get("question"),
        "category": categorize(m.get("slug", ""), m.get("question")),
        "last": c["last"],
        "hrs_to_end": c["hrs"],
        "vol_24h": float(m.get("volume24hr") or 0),
    }

    # Tail-insurance check
    if c["certainty"]:
        last = float(c["last"])
        win_tok_id = str(no["token_id"]) if last <= 0.05 else str(yes["token_id"])
        win_side = "NO" if last <= 0.05 else "YES"
        win_asks = n_asks if win_side == "NO" else y_asks
        if win_asks:
            best_ask = min(float(l["price"]) for l in win_asks)
            cap_98 = sum(float(l["price"]) * float(l["size"]) for l in win_asks if float(l["price"]) < 0.98)
            cap_99 = sum(float(l["price"]) * float(l["size"]) for l in win_asks if float(l["price"]) < 0.99)
            cap_95 = sum(float(l["price"]) * float(l["size"]) for l in win_asks if float(l["price"]) < 0.95)
            if best_ask < 0.99 and cap_99 > 20:
                result["tail_arb"] = {
                    "win_side": win_side,
                    "best_ask": best_ask,
                    "cap_95": round(cap_95, 0),
                    "cap_98": round(cap_98, 0),
                    "cap_99": round(cap_99, 0),
                    "potential_profit_99": round(sum((1 - float(l["price"])) * float(l["size"])
                                                     for l in win_asks if float(l["price"]) < 0.99), 2),
                }

    # Pair-sum check
    if y_asks and n_asks:
        y_min = min(float(l["price"]) for l in y_asks)
        n_min = min(float(l["price"]) for l in n_asks)
        pair_sum = y_min + n_min
        if pair_sum < 1.00:
            y_size = next(float(l["size"]) for l in y_asks if float(l["price"]) == y_min)
            n_size = next(float(l["size"]) for l in n_asks if float(l["price"]) == n_min)
            max_shares = min(y_size, n_size)
            if max_shares * pair_sum > 5:
                result["pair_arb"] = {
                    "y_ask": y_min,
                    "n_ask": n_min,
                    "sum": round(pair_sum, 4),
                    "max_shares": round(max_shares, 2),
                    "potential_profit": round(max_shares * (1.0 - pair_sum), 2),
                }

    return result


async def main(args):
    t0 = time.time()
    async with aiohttp.ClientSession(headers={"User-Agent": "e11-full-scan/0.1"}) as s:
        print("fetching all active markets...")
        all_m = await pull_all_active(s)
        print(f"  {len(all_m)} active markets")

        candidates = filter_candidates(all_m)
        print(f"  {len(candidates)} candidates (tail-ins or pair-sum hint)")

        candidates = candidates[: args.max_books]
        print(f"  analyzing top {len(candidates)} (limited by --max-books)")

        sem = asyncio.Semaphore(8)

        async def worker(c):
            async with sem:
                return await analyze_candidate(s, c)

        results = await asyncio.gather(*[worker(c) for c in candidates])

    tail_arbs = [r for r in results if r and r.get("tail_arb")]
    pair_arbs = [r for r in results if r and r.get("pair_arb")]

    # Tail-insurance by category
    cat_tail: dict[str, list] = defaultdict(list)
    for r in tail_arbs:
        cat_tail[r["category"]].append(r)
    cat_pair: dict[str, list] = defaultdict(list)
    for r in pair_arbs:
        cat_pair[r["category"]].append(r)

    print(f"\n=== TAIL-INSURANCE ARBS: {len(tail_arbs)} across {len(cat_tail)} categories ===\n")
    print(f"{'category':20s} {'n':>4s} {'cap<0.95':>10s} {'cap<0.98':>10s} {'cap<0.99':>10s} {'profit@99':>10s}")
    for cat, arbs in sorted(cat_tail.items(), key=lambda kv: -sum(x["tail_arb"]["cap_99"] for x in kv[1])):
        c95 = sum(x["tail_arb"]["cap_95"] for x in arbs)
        c98 = sum(x["tail_arb"]["cap_98"] for x in arbs)
        c99 = sum(x["tail_arb"]["cap_99"] for x in arbs)
        prof = sum(x["tail_arb"]["potential_profit_99"] for x in arbs)
        print(f"{cat:20s} {len(arbs):>4d} ${c95:>9,.0f} ${c98:>9,.0f} ${c99:>9,.0f} ${prof:>9,.0f}")

    print(f"\n=== PAIR-SUM ARBS: {len(pair_arbs)} across {len(cat_pair)} categories ===\n")
    print(f"{'category':20s} {'n':>4s} {'total_profit':>14s}  (sum of max_shares * (1-pair_sum))")
    for cat, arbs in sorted(cat_pair.items(), key=lambda kv: -sum(x["pair_arb"]["potential_profit"] for x in kv[1])):
        prof = sum(x["pair_arb"]["potential_profit"] for x in arbs)
        print(f"{cat:20s} {len(arbs):>4d} ${prof:>13,.2f}")

    print(f"\n=== TOP 15 TAIL-INSURANCE ARBS BY POTENTIAL PROFIT ===\n")
    for r in sorted(tail_arbs, key=lambda x: -x["tail_arb"]["potential_profit_99"])[:15]:
        a = r["tail_arb"]
        print(f"  [{r['category']:15s}] side={a['win_side']} ask={a['best_ask']:.3f} "
              f"${a['cap_99']:>6,.0f}<0.99 "
              f"${a['potential_profit_99']:>5,.0f}prof "
              f"{r['hrs_to_end']:4.1f}h  {(r['slug'] or '')[:55]}")

    print(f"\n=== TOP 10 PAIR-SUM ARBS BY POTENTIAL PROFIT ===\n")
    for r in sorted(pair_arbs, key=lambda x: -x["pair_arb"]["potential_profit"])[:10]:
        a = r["pair_arb"]
        print(f"  [{r['category']:15s}] sum={a['sum']:.3f} "
              f"y={a['y_ask']:.3f} n={a['n_ask']:.3f} "
              f"shares={a['max_shares']:>6.0f} "
              f"prof=${a['potential_profit']:>5,.2f}  {(r['slug'] or '')[:55]}")

    out_file = OUT_DIR / f"scan_{int(time.time())}.json"
    with out_file.open("w") as f:
        json.dump({
            "run_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_s": round(time.time() - t0, 1),
            "total_active": len(all_m),
            "candidates_analyzed": len(candidates),
            "tail_arbs_found": len(tail_arbs),
            "pair_arbs_found": len(pair_arbs),
            "per_category_tail": {cat: {
                "count": len(arbs),
                "total_cap_99": sum(x["tail_arb"]["cap_99"] for x in arbs),
                "total_profit_99": sum(x["tail_arb"]["potential_profit_99"] for x in arbs),
                "markets": [{"slug": x["slug"], "ask": x["tail_arb"]["best_ask"],
                             "cap_99": x["tail_arb"]["cap_99"],
                             "profit_99": x["tail_arb"]["potential_profit_99"]} for x in arbs],
            } for cat, arbs in cat_tail.items()},
            "per_category_pair": {cat: {
                "count": len(arbs),
                "total_profit": sum(x["pair_arb"]["potential_profit"] for x in arbs),
                "markets": [{"slug": x["slug"], **x["pair_arb"]} for x in arbs],
            } for cat, arbs in cat_pair.items()},
        }, f, indent=2)
    print(f"\nfull results: {out_file}")
    print(f"elapsed: {time.time()-t0:.1f}s")


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--max-books", type=int, default=1200)
    return p.parse_args()


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
