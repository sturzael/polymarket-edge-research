"""Pull trades for all barrier markets tracked in probe.db, aggregate by
wallet, then for the top-N wallets pull their full Polymarket trade history
and per-market P&L.

Everything goes to JSONL/CSV under ./data/. Safe to rerun — overwrites.

Usage:
    uv run python experiments/e9_wallet_competitor_intel/fetch.py            # full sweep
    uv run python experiments/e9_wallet_competitor_intel/fetch.py --smoke    # single market sanity check
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sqlite3
from collections import defaultdict
from pathlib import Path

import aiohttp

log = logging.getLogger(__name__)

DATA_API = "https://data-api.polymarket.com"
HERE = Path(__file__).parent
DATA_DIR = HERE / "data"
PROBE_DB = HERE.parent.parent / "probe" / "probe.db"

BARRIER_SQL = """
SELECT market_id, slug
FROM markets
WHERE slug LIKE '%-reach-%' OR slug LIKE '%-dip-to-%' OR slug LIKE '%-hit-%'
"""

SMOKE_CID = "0xad8cf68ee86ca676ba97bd0ec8f5a57c8f93c697d8d841cbb09e6329516e7ce0"  # xrp-reach-1pt6

CONCURRENCY = 4
PAGE_LIMIT = 500
MAX_TRADES_PER_MARKET = 5000
MAX_TRADES_PER_WALLET = 2000
TOP_N = 20


async def get_json(
    session: aiohttp.ClientSession,
    path: str,
    params: dict,
    retries: int = 5,
) -> list | dict | None:
    url = f"{DATA_API}{path}"
    backoff = 1.0
    for attempt in range(retries):
        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status == 429:
                    log.warning("429 on %s (attempt %d); sleeping %.1fs", path, attempt, backoff)
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 30.0)
                    continue
                if r.status >= 400:
                    log.warning("HTTP %d on %s params=%s", r.status, path, params)
                    return None
                return await r.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            log.warning("err %s on %s (attempt %d): %s", type(e).__name__, path, attempt, e)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)
    return None


async def fetch_trades_for_market(
    session: aiohttp.ClientSession,
    sem: asyncio.Semaphore,
    market_id: str,
) -> list[dict]:
    """Paginate /trades?market=<cid> until empty or capped."""
    out: list[dict] = []
    offset = 0
    while offset < MAX_TRADES_PER_MARKET:
        async with sem:
            page = await get_json(session, "/trades", {
                "market": market_id,
                "limit": str(PAGE_LIMIT),
                "offset": str(offset),
            })
        if not page:
            break
        out.extend(page)
        if len(page) < PAGE_LIMIT:
            break
        offset += PAGE_LIMIT
    return out


async def fetch_user_trades(
    session: aiohttp.ClientSession,
    sem: asyncio.Semaphore,
    wallet: str,
) -> list[dict]:
    out: list[dict] = []
    offset = 0
    while offset < MAX_TRADES_PER_WALLET:
        async with sem:
            page = await get_json(session, "/trades", {
                "user": wallet,
                "limit": str(PAGE_LIMIT),
                "offset": str(offset),
            })
        if not page:
            break
        out.extend(page)
        if len(page) < PAGE_LIMIT:
            break
        offset += PAGE_LIMIT
    return out


async def fetch_user_positions(
    session: aiohttp.ClientSession,
    sem: asyncio.Semaphore,
    wallet: str,
) -> list[dict]:
    async with sem:
        data = await get_json(session, "/positions", {"user": wallet, "limit": "500"})
    return data or []


def load_barrier_markets(smoke: bool) -> list[tuple[str, str]]:
    if smoke:
        return [(SMOKE_CID, "will-xrp-reach-1pt6-on-april-17")]
    con = sqlite3.connect(PROBE_DB)
    try:
        rows = con.execute(BARRIER_SQL).fetchall()
    finally:
        con.close()
    return [(mid, slug) for (mid, slug) in rows]


def aggregate_by_wallet(trades_path: Path) -> dict[str, dict]:
    agg: dict[str, dict] = defaultdict(lambda: {
        "n_trades": 0,
        "notional": 0.0,
        "markets": set(),
        "first_ts": None,
        "last_ts": None,
        "name": None,
        "pseudonym": None,
    })
    with trades_path.open() as f:
        for line in f:
            t = json.loads(line)
            w = t.get("proxyWallet")
            if not w:
                continue
            try:
                size = float(t.get("size") or 0)
                price = float(t.get("price") or 0)
            except (TypeError, ValueError):
                continue
            ts = t.get("timestamp")
            a = agg[w]
            a["n_trades"] += 1
            a["notional"] += size * price
            a["markets"].add(t.get("conditionId") or t.get("slug"))
            if ts is not None:
                if a["first_ts"] is None or ts < a["first_ts"]:
                    a["first_ts"] = ts
                if a["last_ts"] is None or ts > a["last_ts"]:
                    a["last_ts"] = ts
            if a["name"] is None:
                a["name"] = t.get("name")
                a["pseudonym"] = t.get("pseudonym")
    return agg


def write_wallet_csv(agg: dict[str, dict], path: Path) -> None:
    rows = sorted(
        agg.items(),
        key=lambda kv: (kv[1]["notional"], kv[1]["n_trades"]),
        reverse=True,
    )
    with path.open("w") as f:
        f.write("proxy_wallet,name,pseudonym,n_trades,notional_usd,n_markets,first_ts,last_ts\n")
        for w, a in rows:
            name = (a["name"] or "").replace(",", " ")
            pseud = (a["pseudonym"] or "").replace(",", " ")
            f.write(f"{w},{name},{pseud},{a['n_trades']},{a['notional']:.2f},"
                    f"{len(a['markets'])},{a['first_ts'] or ''},{a['last_ts'] or ''}\n")


async def main_async(smoke: bool) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    markets = load_barrier_markets(smoke)
    log.info("loaded %d barrier markets (smoke=%s)", len(markets), smoke)

    sem = asyncio.Semaphore(CONCURRENCY)
    trades_path = DATA_DIR / ("barrier_trades_smoke.jsonl" if smoke else "barrier_trades.jsonl")

    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(*[
            fetch_trades_for_market(session, sem, mid) for mid, _ in markets
        ])

    total = 0
    with trades_path.open("w") as f:
        for (mid, slug), trades in zip(markets, results):
            log.info("  %s %s: %d trades", mid[:10], slug, len(trades))
            for t in trades:
                f.write(json.dumps(t) + "\n")
            total += len(trades)
    log.info("wrote %d trades -> %s", total, trades_path)

    agg = aggregate_by_wallet(trades_path)
    log.info("%d distinct wallets on barrier markets", len(agg))

    agg_path = DATA_DIR / ("barrier_wallet_aggregate_smoke.csv" if smoke else "barrier_wallet_aggregate.csv")
    write_wallet_csv(agg, agg_path)
    log.info("wrote wallet aggregate -> %s", agg_path)

    if smoke:
        log.info("smoke mode: skipping top-wallet history pull")
        return

    top = sorted(agg.items(), key=lambda kv: kv[1]["notional"], reverse=True)[:TOP_N]
    log.info("fetching history+positions for top %d wallets", len(top))

    hist_path = DATA_DIR / "top_wallet_history.jsonl"
    pos_path = DATA_DIR / "top_wallet_positions.jsonl"

    async with aiohttp.ClientSession() as session:
        hist_results = await asyncio.gather(*[
            fetch_user_trades(session, sem, w) for w, _ in top
        ])
        pos_results = await asyncio.gather(*[
            fetch_user_positions(session, sem, w) for w, _ in top
        ])

    with hist_path.open("w") as f:
        for (w, _), trades in zip(top, hist_results):
            for t in trades:
                f.write(json.dumps(t) + "\n")
            log.info("  %s %d trades in user history", w, len(trades))
    with pos_path.open("w") as f:
        for (w, _), positions in zip(top, pos_results):
            for p in positions:
                f.write(json.dumps(p) + "\n")
            log.info("  %s %d positions", w, len(positions))

    log.info("done")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="single-market sanity check only")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(main_async(args.smoke))


if __name__ == "__main__":
    main()
