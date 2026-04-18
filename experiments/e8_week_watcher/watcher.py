"""Week-long passive book watcher for balanced-probability crypto above-K markets.

Purpose: answer the "is there room to quote at all" question that gates the
full MM backtest. Not a backtest itself — just a cheap factual collector.

For each tracked market, every 15 seconds:
  - snapshot best bid / best ask / real-depth bid (biggest-notional bid level)
    and real-depth ask
  - compute a simple fair-value proxy using a GBM model on BTC/ETH/SOL spot
  - record whether an MM is quoting inside [fair_value - 5¢, fair_value + 5¢]

Output: SQLite + a live summary every hour ("in the last hour, X% of snapshots
had no rational quote inside 10¢ of fair value — that's our addressable window
where we could be the tight quote").

Not launched — awaiting user approval for background spawn.

Usage: uv run python experiments/e8_week_watcher/watcher.py [--hours N] [--db path]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import signal
import time
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
import aiosqlite
import ccxt.async_support as ccxt

log = logging.getLogger("watcher")

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
  ts INTEGER NOT NULL,
  market_id TEXT NOT NULL,
  slug TEXT,
  underlying TEXT,
  strike REAL,
  ttm_s REAL,
  spot REAL,
  best_bid REAL,
  best_ask REAL,
  rational_bid REAL,      -- top bid at price > 0.05 (filter penny stubs)
  rational_ask REAL,      -- top ask at price < 0.95
  rational_bid_notional REAL,
  rational_ask_notional REAL,
  mm_present INTEGER,     -- 1 if there's a quote within ±5¢ of fair_value
  fair_value_gbm REAL,
  PRIMARY KEY (ts, market_id)
);
CREATE INDEX IF NOT EXISTS idx_snap_market_ts ON snapshots(market_id, ts);

CREATE TABLE IF NOT EXISTS meta (
  k TEXT PRIMARY KEY,
  v TEXT
);
"""


async def discover_targets(session: aiohttp.ClientSession, max_targets: int = 10) -> list[dict]:
    """Return up to N 'above-K' crypto markets in the balanced-probability zone
    (last_trade ∈ [0.2, 0.8]) with end in (6h, 48h)."""
    out: list[dict] = []
    import re
    for off in range(0, 8000, 200):
        async with session.get(
            "https://gamma-api.polymarket.com/markets",
            params={"closed": "false", "active": "true", "limit": "200",
                    "offset": str(off), "order": "endDate", "ascending": "true"},
        ) as r:
            data = await r.json()
            if not data:
                break
            for m in data:
                slug = (m.get("slug") or "").lower()
                ma = re.match(r"(bitcoin|ethereum|solana)-above-(\d+)-on-", slug)
                if not ma:
                    continue
                last = m.get("lastTradePrice")
                if last is None:
                    continue
                last = float(last)
                if last < 0.2 or last > 0.8:
                    continue
                end = m.get("endDate")
                if not end:
                    continue
                hrs = (datetime.fromisoformat(end.replace("Z", "+00:00"))
                       - datetime.now(timezone.utc)).total_seconds() / 3600
                if hrs < 6 or hrs > 48:
                    continue
                out.append({
                    "market_id": m["conditionId"],
                    "slug": m["slug"],
                    "underlying": ma.group(1).upper()[:3],
                    "strike": float(ma.group(2)),
                    "end_ts_s": int(datetime.fromisoformat(end.replace("Z", "+00:00")).timestamp()),
                })
                if len(out) >= max_targets:
                    return out
            if len(data) < 200:
                break
    return out


def fair_value_gbm(spot: float, strike: float, ttm_s: float, sigma_annual: float = 0.50) -> float:
    """P(S_T > K) under GBM with no drift."""
    if ttm_s <= 0:
        return 1.0 if spot > strike else 0.0
    T = ttm_s / (365.25 * 86400)
    sig_sqrt_T = sigma_annual * math.sqrt(T)
    if sig_sqrt_T == 0:
        return 1.0 if spot > strike else 0.0
    d2 = (math.log(spot / strike) - (sigma_annual ** 2) * T / 2) / sig_sqrt_T
    return 0.5 * (1.0 + math.erf(d2 / math.sqrt(2)))


def summarize_book(book: dict) -> dict:
    bids = book.get("bids", []) or []
    asks = book.get("asks", []) or []
    def best_rational(side, is_bid):
        out = None
        for l in side:
            p = float(l["price"])
            if is_bid and p <= 0.05:
                continue
            if not is_bid and p >= 0.95:
                continue
            if out is None or (is_bid and p > float(out["price"])) or (not is_bid and p < float(out["price"])):
                out = l
        return out
    rb = best_rational(bids, True)
    ra = best_rational(asks, False)
    return {
        "best_bid": float(bids[0]["price"]) if bids else None,
        "best_ask": float(asks[0]["price"]) if asks else None,
        "rational_bid": float(rb["price"]) if rb else None,
        "rational_ask": float(ra["price"]) if ra else None,
        "rational_bid_notional": float(rb["price"]) * float(rb["size"]) if rb else None,
        "rational_ask_notional": float(ra["price"]) * float(ra["size"]) if ra else None,
    }


class Watcher:
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self._stop = asyncio.Event()
        self._spot: dict[str, float] = {}
        self._targets: list[dict] = []
        self._snapshot_count = 0

    async def refresh_targets(self, session: aiohttp.ClientSession) -> None:
        self._targets = await discover_targets(session, max_targets=10)
        log.info("targets refreshed: %d", len(self._targets))
        for t in self._targets:
            log.info("  %s K=%.0f (%s)", t["slug"], t["strike"], t["underlying"])

    async def spot_loop(self, exchange: ccxt.Exchange) -> None:
        while not self._stop.is_set():
            try:
                tickers = await exchange.fetch_tickers(["BTC/USDT", "ETH/USDT", "SOL/USDT"])
                for sym, t in tickers.items():
                    price = t.get("last") or t.get("close")
                    if price:
                        self._spot[sym.split("/")[0]] = float(price)
            except Exception as e:
                log.warning("spot err: %s", e)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=10)
            except asyncio.TimeoutError:
                pass

    async def snapshot_loop(self, session: aiohttp.ClientSession, db: aiosqlite.Connection) -> None:
        last_refresh = 0
        while not self._stop.is_set():
            now_s = int(time.time())
            if now_s - last_refresh > 1800:  # refresh targets every 30 min
                await self.refresh_targets(session)
                last_refresh = now_s
            for t in self._targets:
                await self._snapshot_one(session, db, t)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=15)
            except asyncio.TimeoutError:
                pass

    async def _snapshot_one(self, session, db, target) -> None:
        try:
            async with session.get(
                f"https://clob.polymarket.com/markets/{target['market_id']}",
                timeout=aiohttp.ClientTimeout(total=8),
            ) as r:
                if r.status != 200:
                    return
                mkt = await r.json()
            yes = next((tok for tok in mkt.get("tokens", [])
                        if (tok.get("outcome") or "").lower() in ("yes", "up")), None)
            if not yes:
                return
            async with session.get(
                "https://clob.polymarket.com/book",
                params={"token_id": str(yes["token_id"])},
                timeout=aiohttp.ClientTimeout(total=8),
            ) as r:
                if r.status != 200:
                    return
                book = await r.json()
            snap = summarize_book(book)
            now = int(time.time())
            spot = self._spot.get(target["underlying"])
            ttm_s = target["end_ts_s"] - now
            fv = fair_value_gbm(spot, target["strike"], ttm_s) if spot else None
            mm_present = 0
            if fv is not None and snap["rational_bid"] is not None:
                if abs(snap["rational_bid"] - fv) <= 0.05 or abs(snap["rational_ask"] - fv) <= 0.05:
                    mm_present = 1
            await db.execute(
                """INSERT OR REPLACE INTO snapshots
                   (ts, market_id, slug, underlying, strike, ttm_s, spot,
                    best_bid, best_ask, rational_bid, rational_ask,
                    rational_bid_notional, rational_ask_notional, mm_present, fair_value_gbm)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (now, target["market_id"], target["slug"], target["underlying"],
                 target["strike"], ttm_s, spot,
                 snap["best_bid"], snap["best_ask"],
                 snap["rational_bid"], snap["rational_ask"],
                 snap["rational_bid_notional"], snap["rational_ask_notional"],
                 mm_present, fv),
            )
            await db.commit()
            self._snapshot_count += 1
        except Exception as e:
            log.warning("snap err %s: %s", target.get("slug"), e)

    async def summary_loop(self, db: aiosqlite.Connection) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=3600)
                return
            except asyncio.TimeoutError:
                pass
            async with db.execute(
                """SELECT
                     COUNT(*),
                     SUM(CASE WHEN mm_present=1 THEN 1 ELSE 0 END),
                     AVG(rational_ask - rational_bid)
                   FROM snapshots WHERE ts > strftime('%s','now','-1 hour')"""
            ) as cur:
                row = await cur.fetchone()
            if row and row[0]:
                n, n_mm, avg_spread = row
                pct_mm = 100.0 * n_mm / n
                log.info("HOUR SUMMARY: snapshots=%d  mm_present=%d (%.1f%%)  avg_rational_spread=%.3f",
                         n, n_mm, pct_mm, avg_spread or 0)


async def amain(args):
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s watcher: %(message)s",
                        datefmt="%H:%M:%S")
    logging.getLogger("ccxt").setLevel(logging.WARNING)
    db_path = Path(args.db); db_path.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(db_path)
    await db.execute("PRAGMA journal_mode=WAL")
    await db.executescript(SCHEMA)
    await db.commit()

    w = Watcher(db_path)
    session = aiohttp.ClientSession(headers={"User-Agent": "watcher/0.1"})
    exchange = ccxt.binance({"enableRateLimit": True})

    loop = asyncio.get_running_loop()
    for s in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(s, w._stop.set)

    await w.refresh_targets(session)

    tasks = [
        asyncio.create_task(w.spot_loop(exchange)),
        asyncio.create_task(w.snapshot_loop(session, db)),
        asyncio.create_task(w.summary_loop(db)),
    ]

    async def deadline():
        try:
            await asyncio.wait_for(w._stop.wait(), timeout=args.hours * 3600)
        except asyncio.TimeoutError:
            w._stop.set()

    tasks.append(asyncio.create_task(deadline()))
    await w._stop.wait()
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await exchange.close()
    await session.close()
    await db.close()
    log.info("done; total_snapshots=%d", w._snapshot_count)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--hours", type=float, default=168.0)  # 1 week
    p.add_argument("--db", default="experiments/e8_week_watcher/watcher.db")
    args = p.parse_args()
    asyncio.run(amain(args))


if __name__ == "__main__":
    main()
