"""Binance + Coinbase BTC trade collector for lead-lag rig calibration.

Runs for N hours. Stores every BTC-USD trade from both exchanges with:
  - venue ('binance' | 'coinbase')
  - local_ts_ms  (our wall-clock when message was received)
  - exch_ts_ms   (exchange-reported trade time)
  - price
  - size

We'll analyze this post-hoc with 100ms-binned returns cross-correlation.

Run: uv run python experiments/e3_leadlag/collect.py [--hours 2]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import sqlite3
import time
from pathlib import Path

import websockets

log = logging.getLogger("leadlag")

BINANCE_URL = "wss://stream.binance.com:9443/ws/btcusdt@trade"
COINBASE_URL = "wss://ws-feed.exchange.coinbase.com"

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
  venue        TEXT    NOT NULL,
  local_ts_ms  INTEGER NOT NULL,
  exch_ts_ms   INTEGER NOT NULL,
  price        REAL    NOT NULL,
  size         REAL    NOT NULL,
  side         TEXT,
  PRIMARY KEY (venue, local_ts_ms, exch_ts_ms)
);
CREATE INDEX IF NOT EXISTS idx_trades_venue_ts ON trades(venue, exch_ts_ms);
"""


def now_ms() -> int:
    return int(time.time() * 1000)


class LeadLagCollector:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self._stop = asyncio.Event()
        self._counts = {"binance": 0, "coinbase": 0}

    def insert(self, row: tuple) -> None:
        try:
            self.conn.execute(
                "INSERT OR IGNORE INTO trades (venue, local_ts_ms, exch_ts_ms, price, size, side) VALUES (?, ?, ?, ?, ?, ?)",
                row,
            )
            self.conn.commit()
        except sqlite3.OperationalError as e:
            log.warning("sqlite error: %s", e)

    async def binance_loop(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                async with websockets.connect(BINANCE_URL, ping_interval=20) as ws:
                    log.info("binance connected")
                    backoff = 1.0
                    while not self._stop.is_set():
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=30)
                        except asyncio.TimeoutError:
                            continue
                        d = json.loads(msg)
                        if d.get("e") != "trade":
                            continue
                        local = now_ms()
                        self.insert((
                            "binance", local, int(d["T"]),
                            float(d["p"]), float(d["q"]),
                            "sell" if d.get("m") else "buy",
                        ))
                        self._counts["binance"] += 1
            except Exception as e:
                if self._stop.is_set():
                    return
                log.warning("binance reconnect (%.1fs): %s", backoff, e)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)

    async def coinbase_loop(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                async with websockets.connect(COINBASE_URL, ping_interval=20) as ws:
                    await ws.send(json.dumps({
                        "type": "subscribe",
                        "product_ids": ["BTC-USD"],
                        "channels": ["matches"],
                    }))
                    log.info("coinbase connected + subscribed")
                    backoff = 1.0
                    while not self._stop.is_set():
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=30)
                        except asyncio.TimeoutError:
                            continue
                        d = json.loads(msg)
                        if d.get("type") != "match":
                            continue
                        # time: "2026-04-18T14:59:52.123456Z"
                        from datetime import datetime, timezone
                        try:
                            dt = datetime.fromisoformat(d["time"].replace("Z", "+00:00"))
                            exch_ts = int(dt.timestamp() * 1000)
                        except Exception:
                            exch_ts = now_ms()
                        local = now_ms()
                        self.insert((
                            "coinbase", local, exch_ts,
                            float(d["price"]), float(d["size"]),
                            d.get("side"),
                        ))
                        self._counts["coinbase"] += 1
            except Exception as e:
                if self._stop.is_set():
                    return
                log.warning("coinbase reconnect (%.1fs): %s", backoff, e)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)

    async def stats_loop(self) -> None:
        last = dict(self._counts)
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=60)
                return
            except asyncio.TimeoutError:
                pass
            delta = {k: self._counts[k] - last[k] for k in self._counts}
            last = dict(self._counts)
            log.info("minute stats: binance=+%d coinbase=+%d total=%s",
                     delta["binance"], delta["coinbase"], self._counts)

    async def run(self, duration_s: float) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._stop.set)

        tasks = [
            asyncio.create_task(self.binance_loop(), name="binance"),
            asyncio.create_task(self.coinbase_loop(), name="coinbase"),
            asyncio.create_task(self.stats_loop(), name="stats"),
        ]

        async def deadline():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=duration_s)
            except asyncio.TimeoutError:
                log.info("duration reached, stopping")
                self._stop.set()

        tasks.append(asyncio.create_task(deadline(), name="deadline"))
        await self._stop.wait()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.conn.close()


async def amain(args) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s leadlag: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("websockets").setLevel(logging.WARNING)
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    c = LeadLagCollector(db_path)
    log.info("leadlag collector starting: hours=%s db=%s", args.hours, args.db)
    await c.run(duration_s=args.hours * 3600)
    log.info("done; counts=%s", c._counts)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--hours", type=float, default=2.0)
    p.add_argument("--db", default="experiments/e3_leadlag/leadlag.db")
    args = p.parse_args()
    asyncio.run(amain(args))


if __name__ == "__main__":
    main()
