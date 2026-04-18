from __future__ import annotations

import asyncio
import time
from pathlib import Path

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS prices (
  ts    INTEGER NOT NULL,
  asset TEXT    NOT NULL,
  price REAL    NOT NULL,
  PRIMARY KEY (ts, asset)
);
CREATE INDEX IF NOT EXISTS idx_prices_asset_ts ON prices(asset, ts);

CREATE TABLE IF NOT EXISTS events (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  ts             INTEGER NOT NULL,
  source         TEXT    NOT NULL,
  url            TEXT    UNIQUE,
  title          TEXT    NOT NULL,
  summary        TEXT,
  lang           TEXT    NOT NULL DEFAULT 'en',
  original_title TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);

CREATE TABLE IF NOT EXISTS live_results (
  event_id     INTEGER NOT NULL,
  asset        TEXT    NOT NULL,
  move_30s     REAL,
  move_1m      REAL,
  move_5m      REAL,
  sigma_recent REAL,
  z_5m         REAL,
  signal       TEXT,
  computed_at  INTEGER NOT NULL,
  PRIMARY KEY (event_id, asset)
);

CREATE TABLE IF NOT EXISTS expiry_markets (
  market_id      TEXT PRIMARY KEY,
  slug           TEXT NOT NULL,
  underlying     TEXT,
  duration_s     INTEGER,
  expiry_ts      INTEGER NOT NULL,
  discovered_at  INTEGER NOT NULL,
  tracked        INTEGER DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_expiry_markets_ts ON expiry_markets(expiry_ts);

CREATE TABLE IF NOT EXISTS expiry_samples (
  market_id  TEXT    NOT NULL,
  ts         INTEGER NOT NULL,
  poly_price REAL,
  spot_price REAL,
  PRIMARY KEY (market_id, ts)
);

CREATE TABLE IF NOT EXISTS expiry_results (
  market_id        TEXT PRIMARY KEY,
  outcome          TEXT,
  poly_price_30s   REAL,
  poly_price_20s   REAL,
  poly_price_10s   REAL,
  poly_price_5s    REAL,
  poly_price_final REAL,
  spot_move_60s    REAL,
  spot_move_10s    REAL,
  spot_z_10s       REAL,
  lag_flag         INTEGER,
  err_30s          REAL,
  err_10s          REAL,
  err_5s           REAL,
  mispricing       INTEGER,
  actionable       INTEGER,
  resolved_at      INTEGER,
  FOREIGN KEY (market_id) REFERENCES expiry_markets(market_id)
);
"""


def now_ms() -> int:
    return int(time.time() * 1000)


class Storage:
    """Thin async wrapper over aiosqlite with a single shared writer coroutine.

    SQLite under asyncio needs serialized writes; we enforce that with a lock.
    Readers can use `conn()` for their own short-lived connections.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._write_lock = asyncio.Lock()
        self._conn: aiosqlite.Connection | None = None

    async def open(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA synchronous=NORMAL")
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def execute(self, sql: str, params: tuple = ()) -> None:
        assert self._conn is not None
        async with self._write_lock:
            await self._conn.execute(sql, params)
            await self._conn.commit()

    async def executemany(self, sql: str, rows: list[tuple]) -> None:
        assert self._conn is not None
        if not rows:
            return
        async with self._write_lock:
            await self._conn.executemany(sql, rows)
            await self._conn.commit()

    async def fetchall(self, sql: str, params: tuple = ()) -> list[tuple]:
        assert self._conn is not None
        async with self._conn.execute(sql, params) as cursor:
            return await cursor.fetchall()

    async def fetchone(self, sql: str, params: tuple = ()) -> tuple | None:
        assert self._conn is not None
        async with self._conn.execute(sql, params) as cursor:
            return await cursor.fetchone()

    # --- convenience inserts ---

    async def insert_prices(self, rows: list[tuple[int, str, float]]) -> None:
        """rows: (ts_ms, asset, price)"""
        await self.executemany(
            "INSERT OR IGNORE INTO prices (ts, asset, price) VALUES (?, ?, ?)",
            rows,
        )

    async def insert_event(
        self,
        ts_ms: int,
        source: str,
        url: str | None,
        title: str,
        summary: str | None,
        lang: str = "en",
        original_title: str | None = None,
    ) -> int | None:
        """Insert an event; return new row id or None if url already seen."""
        assert self._conn is not None
        async with self._write_lock:
            try:
                cursor = await self._conn.execute(
                    "INSERT INTO events (ts, source, url, title, summary, lang, original_title) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (ts_ms, source, url, title, summary, lang, original_title),
                )
                await self._conn.commit()
                return cursor.lastrowid
            except aiosqlite.IntegrityError:
                return None  # dup URL

    async def upsert_expiry_market(
        self,
        market_id: str,
        slug: str,
        underlying: str | None,
        duration_s: int | None,
        expiry_ts: int,
    ) -> None:
        await self.execute(
            "INSERT OR IGNORE INTO expiry_markets "
            "(market_id, slug, underlying, duration_s, expiry_ts, discovered_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (market_id, slug, underlying, duration_s, expiry_ts, now_ms()),
        )

    async def insert_expiry_samples(
        self, rows: list[tuple[str, int, float | None, float | None]]
    ) -> None:
        """rows: (market_id, ts_ms, poly_price, spot_price)"""
        await self.executemany(
            "INSERT OR REPLACE INTO expiry_samples (market_id, ts, poly_price, spot_price) "
            "VALUES (?, ?, ?, ?)",
            rows,
        )

    async def insert_expiry_result(self, row: dict) -> None:
        cols = [
            "market_id", "outcome",
            "poly_price_30s", "poly_price_20s", "poly_price_10s",
            "poly_price_5s", "poly_price_final",
            "spot_move_60s", "spot_move_10s", "spot_z_10s",
            "lag_flag",
            "err_30s", "err_10s", "err_5s",
            "mispricing", "actionable",
            "resolved_at",
        ]
        placeholders = ", ".join(["?"] * len(cols))
        await self.execute(
            f"INSERT OR REPLACE INTO expiry_results ({', '.join(cols)}) VALUES ({placeholders})",
            tuple(row.get(c) for c in cols),
        )

    async def insert_live_result(self, row: dict) -> None:
        cols = [
            "event_id", "asset", "move_30s", "move_1m", "move_5m",
            "sigma_recent", "z_5m", "signal", "computed_at",
        ]
        placeholders = ", ".join(["?"] * len(cols))
        await self.execute(
            f"INSERT OR REPLACE INTO live_results ({', '.join(cols)}) VALUES ({placeholders})",
            tuple(row.get(c) for c in cols),
        )

    async def price_at(self, asset: str, ts_ms: int, tolerance_ms: int = 2000) -> float | None:
        """Return the most recent price for asset at or before ts_ms, within tolerance."""
        row = await self.fetchone(
            "SELECT price FROM prices WHERE asset=? AND ts<=? AND ts>=? "
            "ORDER BY ts DESC LIMIT 1",
            (asset, ts_ms, ts_ms - tolerance_ms),
        )
        return row[0] if row else None
