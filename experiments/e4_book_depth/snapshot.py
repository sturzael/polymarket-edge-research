"""Single-pass CLOB book-depth snapshot across active 5m markets at
different lifecycle stages.

For each tracked 5m crypto market currently live in probe.db, fetch /book
for the Up-token via CLOB REST. Record best bid/ask, depth at each 1¢ level,
total book notional.

Not a 1-hour sampler (that needs user approval for the background process);
this is a point-in-time survey to characterize the distribution.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

import aiohttp


OUT_DIR = Path(__file__).parent
CLOB = "https://clob.polymarket.com"


async def get_book(session: aiohttp.ClientSession, token_id: str) -> dict | None:
    async with session.get(f"{CLOB}/book", params={"token_id": token_id}) as r:
        if r.status != 200:
            return None
        return await r.json()


def summarize_book(book: dict) -> dict:
    """Compute useful depth statistics from a CLOB book payload.

    bids/asks are sorted with best (highest bid / lowest ask) first.
    Each entry: {price: '0.05', size: '123.4'}.
    """
    bids = book.get("bids", [])
    asks = book.get("asks", [])
    best_bid = float(bids[0]["price"]) if bids else None
    best_ask = float(asks[0]["price"]) if asks else None
    spread = (best_ask - best_bid) if (best_bid is not None and best_ask is not None) else None
    def notional(side):
        tot = 0.0
        for lvl in side:
            try:
                # CLOB sizes on binary markets are in shares (each share = $1 on win)
                # so "notional" = price × size
                tot += float(lvl["price"]) * float(lvl["size"])
            except Exception:
                continue
        return tot
    return {
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread": spread,
        "bid_levels": len(bids),
        "ask_levels": len(asks),
        "bid_notional_usd": round(notional(bids), 2),
        "ask_notional_usd": round(notional(asks), 2),
        "bid_top_level_size": float(bids[0]["size"]) if bids else None,
        "ask_top_level_size": float(asks[0]["size"]) if asks else None,
    }


async def main() -> None:
    import time
    now_ms = int(time.time() * 1000)
    c = sqlite3.connect("probe/probe.db")
    # Pick markets across lifecycle stages: some newly-minted (>4m to end),
    # some mid (~2m to end), some final-stretch (<1m), some just-expired.
    buckets = [
        ("newly-minted",    300, 280),  # 4.7-5m to end
        ("mid-life",        180, 140),  # 2-3m to end
        ("final-stretch",    60,   10), # 10s-1m to end
        ("just-expired",    -60,  -30), # 30-60s past
    ]
    picks: list[tuple[str, dict]] = []
    for label, lo_s, hi_s in buckets:
        lo = now_ms + lo_s * 1000
        hi = now_ms + hi_s * 1000
        if lo > hi:
            lo, hi = hi, lo
        rows = c.execute(
            """
            SELECT market_id, slug, underlying, duration_s, end_ts, clob_token_ids
            FROM markets
            WHERE is_crypto=1 AND duration_s=300 AND clob_token_ids IS NOT NULL
              AND end_ts BETWEEN ? AND ?
            ORDER BY end_ts ASC
            LIMIT 3
            """,
            (lo, hi),
        ).fetchall()
        for r in rows:
            picks.append((label, {
                "market_id": r[0], "slug": r[1], "underlying": r[2],
                "duration_s": r[3], "end_ts": r[4], "clob_token_ids": r[5],
                "time_to_end_s": (r[4] - now_ms) / 1000,
            }))
    if not picks:
        print("no active 5m markets in lifecycle buckets right now; try again later")
        return

    results: list[dict] = []
    async with aiohttp.ClientSession() as session:
        for label, m in picks:
            tokens = json.loads(m["clob_token_ids"])
            # We want the "Up"/"Yes" token price. Identify via CLOB market metadata
            async with session.get(f"{CLOB}/markets/{m['market_id']}") as r:
                if r.status != 200:
                    continue
                mkt = await r.json()
            up_tok = next((str(t["token_id"]) for t in mkt.get("tokens", [])
                           if (t.get("outcome") or "").lower() in ("up", "yes")), None)
            if up_tok is None:
                continue
            book = await get_book(session, up_tok)
            if not book:
                continue
            stats = summarize_book(book)
            result = {
                "bucket": label,
                "time_to_end_s": m["time_to_end_s"],
                "underlying": m["underlying"],
                "slug": m["slug"],
                **stats,
            }
            results.append(result)
            print(f"{label:17s}  t_end={m['time_to_end_s']:+6.1f}s  {m['underlying']:4s}  "
                  f"bid={stats['best_bid']}  ask={stats['best_ask']}  spread={stats['spread']}  "
                  f"bid_$={stats['bid_notional_usd']}  ask_$={stats['ask_notional_usd']}  "
                  f"{m['slug'][:40]}")
    (OUT_DIR / "snapshot_results.json").write_text(json.dumps(results, indent=2))
    print(f"\n-> {OUT_DIR / 'snapshot_results.json'}")


if __name__ == "__main__":
    asyncio.run(main())
