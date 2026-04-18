"""Probe SQLite schema + async helpers. Separate DB from the main MVP."""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS markets (
  market_id          TEXT PRIMARY KEY,
  slug               TEXT,
  question           TEXT,
  underlying         TEXT,
  duration_s         INTEGER,
  start_ts           INTEGER,
  end_ts             INTEGER,
  resolution_source  TEXT,
  outcomes           TEXT,
  clob_token_ids     TEXT,
  first_seen         INTEGER NOT NULL,
  last_seen          INTEGER NOT NULL,
  is_crypto          INTEGER NOT NULL DEFAULT 0,
  raw_meta           TEXT
);
CREATE INDEX IF NOT EXISTS idx_markets_end_ts   ON markets(end_ts);
CREATE INDEX IF NOT EXISTS idx_markets_crypto   ON markets(is_crypto);

CREATE TABLE IF NOT EXISTS market_snapshots (
  market_id        TEXT NOT NULL,
  ts               INTEGER NOT NULL,
  best_bid         REAL,
  best_ask         REAL,
  last_trade_price REAL,
  volume_24hr      REAL,
  closed           INTEGER,
  active           INTEGER,
  spot_price       REAL,
  PRIMARY KEY (market_id, ts)
);
CREATE INDEX IF NOT EXISTS idx_snap_ts ON market_snapshots(ts);

CREATE TABLE IF NOT EXISTS resolutions (
  market_id          TEXT PRIMARY KEY,
  nominal_end_ts     INTEGER NOT NULL,
  first_closed_ts    INTEGER,
  resolved_ts        INTEGER,
  resolution_lag_s   REAL,
  outcome            TEXT,
  resolved_cleanly   INTEGER,
  umadata            TEXT,
  notes              TEXT
);

CREATE TABLE IF NOT EXISTS probe_meta (
  key   TEXT PRIMARY KEY,
  value TEXT
);
"""


def now_ms() -> int:
    return int(time.time() * 1000)


class ProbeDB:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = asyncio.Lock()
        self._conn: aiosqlite.Connection | None = None

    async def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA synchronous=NORMAL")
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def _exec(self, sql: str, params: tuple = ()) -> int | None:
        assert self._conn is not None
        async with self._lock:
            cur = await self._conn.execute(sql, params)
            await self._conn.commit()
            return cur.lastrowid

    async def fetchall(self, sql: str, params: tuple = ()) -> list[tuple]:
        assert self._conn is not None
        async with self._conn.execute(sql, params) as cur:
            return await cur.fetchall()

    async def fetchone(self, sql: str, params: tuple = ()) -> tuple | None:
        assert self._conn is not None
        async with self._conn.execute(sql, params) as cur:
            return await cur.fetchone()

    async def upsert_market(self, m: dict) -> bool:
        """Returns True if this is a newly inserted market."""
        assert self._conn is not None
        async with self._lock:
            cur = await self._conn.execute(
                "SELECT market_id FROM markets WHERE market_id=?",
                (m["market_id"],),
            )
            existing = await cur.fetchone()
            if existing is None:
                await self._conn.execute(
                    """
                    INSERT INTO markets (
                      market_id, slug, question, underlying, duration_s,
                      start_ts, end_ts, resolution_source, outcomes, clob_token_ids,
                      first_seen, last_seen, is_crypto, raw_meta
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        m["market_id"], m.get("slug"), m.get("question"),
                        m.get("underlying"), m.get("duration_s"),
                        m.get("start_ts"), m.get("end_ts"),
                        m.get("resolution_source"), m.get("outcomes"),
                        m.get("clob_token_ids"),
                        m["first_seen"], m["last_seen"],
                        int(bool(m.get("is_crypto"))),
                        m.get("raw_meta"),
                    ),
                )
                await self._conn.commit()
                return True
            else:
                await self._conn.execute(
                    "UPDATE markets SET last_seen=?, end_ts=COALESCE(?, end_ts), "
                    "resolution_source=COALESCE(?, resolution_source) WHERE market_id=?",
                    (m["last_seen"], m.get("end_ts"), m.get("resolution_source"), m["market_id"]),
                )
                await self._conn.commit()
                return False

    async def insert_snapshot(self, snap: dict) -> None:
        await self._exec(
            "INSERT OR REPLACE INTO market_snapshots "
            "(market_id, ts, best_bid, best_ask, last_trade_price, volume_24hr, closed, active, spot_price) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                snap["market_id"], snap["ts"],
                snap.get("best_bid"), snap.get("best_ask"),
                snap.get("last_trade_price"), snap.get("volume_24hr"),
                int(snap["closed"]) if snap.get("closed") is not None else None,
                int(snap["active"]) if snap.get("active") is not None else None,
                snap.get("spot_price"),
            ),
        )

    async def upsert_resolution(self, r: dict) -> None:
        await self._exec(
            "INSERT OR REPLACE INTO resolutions "
            "(market_id, nominal_end_ts, first_closed_ts, resolved_ts, resolution_lag_s, "
            " outcome, resolved_cleanly, umadata, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                r["market_id"], r["nominal_end_ts"],
                r.get("first_closed_ts"), r.get("resolved_ts"),
                r.get("resolution_lag_s"), r.get("outcome"),
                int(r["resolved_cleanly"]) if r.get("resolved_cleanly") is not None else None,
                r.get("umadata"), r.get("notes"),
            ),
        )

    async def all_tracked_markets(self) -> list[tuple]:
        return await self.fetchall(
            "SELECT market_id, end_ts, underlying FROM markets "
            "WHERE is_crypto=1 ORDER BY end_ts ASC"
        )

    async def set_meta(self, key: str, value: str) -> None:
        await self._exec(
            "INSERT OR REPLACE INTO probe_meta (key, value) VALUES (?, ?)", (key, value)
        )

    async def get_meta(self, key: str) -> str | None:
        row = await self.fetchone("SELECT value FROM probe_meta WHERE key=?", (key,))
        return row[0] if row else None
