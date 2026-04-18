"""Geopolitical informed-trading reconnaissance watcher.

Collects Polymarket price snapshots + RSS news items, matched by keyword.
Does NOT detect anything — detection is run offline by analyze.py against e10.db.

See README.md for scope, decision gate, and known limitations.

Run:
    uv run python experiments/e10_geo_informed_trading/watcher.py --hours 48
    uv run python experiments/e10_geo_informed_trading/watcher.py --smoke --hours 0.1

Health check while running:
    sqlite3 e10.db "select source,count(*) from news_items group by source"
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import signal
import sys
import time
from pathlib import Path

import aiohttp
import aiosqlite
import feedparser
import yaml

# Add project root to sys.path so we can reuse probe.api
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from probe.api import PolymarketAPI, normalize_market, now_utc_ms  # noqa: E402

log = logging.getLogger("e10")

HERE = Path(__file__).parent
MARKETS_YAML = HERE / "markets.yaml"
FEEDS_YAML = HERE / "feeds.yaml"
DEFAULT_DB = HERE / "e10.db"
CANDIDATES_JSONL = HERE / "data" / "candidates_new.jsonl"

SNAPSHOT_INTERVAL_S = 60
SMOKE_SNAPSHOT_INTERVAL_S = 15
NEWS_MATCH_INTERVAL_S = 30
DISCOVERY_INTERVAL_S = 6 * 3600
SMOKE_DISCOVERY_INTERVAL_S = 300
FEED_HEALTH_INTERVAL_S = 5 * 60

# Slug-substring patterns used for discovery (gamma-api tag/category filters
# confirmed silently ignored on 2026-04-18). These are broad — anything matching
# is logged to candidates_new.jsonl for manual review before adding to markets.yaml.
GEO_SLUG_RE = re.compile(
    r"(iran|israel|russia|ukraine|china|taiwan|north-korea|nkorea|venezuela|"
    r"gaza|hamas|hezbollah|houthi|putin|xi-jinping|netanyahu|zelenskyy|zelensky|"
    r"war|strike|invade|invasion|sanction|ceasefire|treaty|nuclear|missile|"
    r"airstrike|hostage|drone|nato|starmer|macron|merz|tariff|hormuz|syria)",
    re.I,
)
CRYPTO_SLUG_RE = re.compile(r"(bitcoin|btc|ethereum|eth|solana|sol|crypto|xrp|doge)", re.I)
SPORTS_SLUG_RE = re.compile(r"(nba|nfl|nhl|mlb|epl|cs2-|ucl|champions-league|formula-1|f1-)", re.I)


SCHEMA = """
CREATE TABLE IF NOT EXISTS markets (
  market_id TEXT PRIMARY KEY,
  slug TEXT,
  question TEXT,
  theme TEXT,
  keywords_json TEXT,
  start_ts INTEGER,
  end_ts INTEGER,
  volume_24hr_at_discovery REAL,
  added_ts INTEGER NOT NULL,
  still_active INTEGER NOT NULL DEFAULT 1,
  is_control INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS snapshots (
  market_id TEXT NOT NULL,
  ts INTEGER NOT NULL,
  best_bid REAL,
  best_ask REAL,
  last_trade_price REAL,
  mid REAL,
  volume_24hr REAL,
  PRIMARY KEY (market_id, ts)
);
CREATE INDEX IF NOT EXISTS idx_snap_ts ON snapshots(ts);

CREATE TABLE IF NOT EXISTS news_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  guid TEXT,
  title TEXT,
  summary TEXT,
  url TEXT,
  pub_ts INTEGER,
  seen_ts INTEGER NOT NULL,
  best_ts INTEGER NOT NULL,
  tokens_json TEXT,
  UNIQUE(source, guid)
);
CREATE INDEX IF NOT EXISTS idx_news_best_ts ON news_items(best_ts);

CREATE TABLE IF NOT EXISTS news_market_matches (
  news_id INTEGER NOT NULL,
  market_id TEXT NOT NULL,
  match_keyword_count INTEGER,
  PRIMARY KEY (news_id, market_id)
);

CREATE TABLE IF NOT EXISTS feed_health (
  source TEXT NOT NULL,
  ts INTEGER NOT NULL,
  items_received INTEGER,
  last_pub_ts INTEGER,
  PRIMARY KEY (source, ts)
);

-- Populated by analyze.py, not the watcher. analyze.py DROPs and recreates
-- this table each run, so the canonical schema lives there; this is a
-- placeholder so a fresh DB has the table available.
CREATE TABLE IF NOT EXISTS flagged_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  market_id TEXT NOT NULL,
  t_move_start INTEGER,
  t_move_end INTEGER,
  price_before REAL,
  price_after REAL,
  z_score REAL,
  volume_delta REAL,
  first_matching_news_ts INTEGER,
  news_lead_minutes REAL,
  feeds_healthy_relevant INTEGER,
  low_confidence INTEGER,
  feeds_detail_json TEXT,
  nearby_markets_json TEXT,
  manual_verdict TEXT
);
"""


TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9'-]+")


def tokenise(text: str) -> list[str]:
    return TOKEN_RE.findall((text or "").lower())


def load_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


class Watcher:
    def __init__(self, db_path: Path, smoke: bool = False):
        self.db_path = db_path
        self.smoke = smoke
        self._stop = asyncio.Event()
        self._snapshot_count = 0
        self._news_count = 0
        self._match_count = 0
        self._markets: list[dict] = []   # loaded from markets.yaml
        self._feeds: list[dict] = []     # loaded from feeds.yaml

    async def _open_db(self) -> aiosqlite.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        db = await aiosqlite.connect(self.db_path)
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")
        await db.executescript(SCHEMA)
        await db.commit()
        return db

    async def _load_config(self, db: aiosqlite.Connection) -> None:
        mkt_payload = load_yaml(MARKETS_YAML)
        feeds_payload = load_yaml(FEEDS_YAML)
        self._markets = mkt_payload.get("markets", []) or []
        self._feeds = feeds_payload.get("feeds", []) or []
        if self.smoke:
            # In smoke mode, keep only a handful to reduce HTTP load.
            self._markets = self._markets[:3]
            self._feeds = self._feeds[:2]
        # Upsert markets.
        now = now_utc_ms()
        for m in self._markets:
            await db.execute(
                """INSERT INTO markets(market_id, slug, question, theme, keywords_json,
                                        start_ts, end_ts, volume_24hr_at_discovery,
                                        added_ts, still_active, is_control)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(market_id) DO UPDATE SET
                     slug=excluded.slug,
                     question=excluded.question,
                     theme=excluded.theme,
                     keywords_json=excluded.keywords_json,
                     still_active=1,
                     is_control=excluded.is_control""",
                (
                    m["market_id"],
                    m.get("slug"),
                    m.get("question"),
                    m.get("theme"),
                    json.dumps(m.get("keywords") or []),
                    None,
                    _parse_end_ms(m.get("end_date")),
                    m.get("volume_24hr_at_discovery"),
                    now,
                    1,
                    1 if m.get("is_control") else 0,
                ),
            )
        await db.commit()
        log.info("loaded %d markets (%d control) and %d feeds",
                 len(self._markets),
                 sum(1 for m in self._markets if m.get("is_control")),
                 len(self._feeds))

    # ---- snapshot sampler ----

    async def snapshot_loop(self, db: aiosqlite.Connection, session: aiohttp.ClientSession) -> None:
        api = PolymarketAPI(session)
        interval = SMOKE_SNAPSHOT_INTERVAL_S if self.smoke else SNAPSHOT_INTERVAL_S
        while not self._stop.is_set():
            try:
                await self._do_snapshot(db, api)
            except asyncio.CancelledError:
                return
            except Exception as e:
                log.exception("snapshot error: %s", e)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    async def _do_snapshot(self, db: aiosqlite.Connection, api: PolymarketAPI) -> None:
        if not self._markets:
            return
        cids = [m["market_id"] for m in self._markets]
        raws = await api.get_markets_bulk(cids)
        if not raws:
            log.warning("snapshot: bulk fetch returned 0 rows for %d ids", len(cids))
            return
        ts = now_utc_ms()
        rows: list[tuple] = []
        for raw in raws:
            n = normalize_market(raw)
            cid = n.get("market_id")
            if not cid:
                continue
            bid = _as_float(n.get("best_bid"))
            ask = _as_float(n.get("best_ask"))
            last = _as_float(n.get("last_trade_price"))
            mid = None
            if bid is not None and ask is not None and ask > 0:
                mid = (bid + ask) / 2.0
            elif last is not None:
                mid = last
            rows.append((
                cid, ts, bid, ask, last, mid, _as_float(n.get("volume_24hr")),
            ))
        if rows:
            await db.executemany(
                """INSERT OR IGNORE INTO snapshots
                   (market_id, ts, best_bid, best_ask, last_trade_price, mid, volume_24hr)
                   VALUES(?,?,?,?,?,?,?)""",
                rows,
            )
            await db.commit()
            self._snapshot_count += len(rows)
            log.info("snapshot: %d markets recorded (total=%d)", len(rows), self._snapshot_count)

    # ---- news polling ----

    async def news_feed_loop(self, db: aiosqlite.Connection, session: aiohttp.ClientSession, feed: dict) -> None:
        name = feed["name"]
        url = feed["url"]
        interval = feed.get("poll_interval_s", 60)
        if self.smoke:
            interval = min(interval, 30)
        # Stagger first run to avoid thundering herd.
        await asyncio.sleep(hash(name) % 20)
        while not self._stop.is_set():
            try:
                n = await self._poll_feed(db, session, name, url)
                if n > 0:
                    log.info("feed %s: %d new items (total=%d)", name, n, self._news_count)
            except asyncio.CancelledError:
                return
            except Exception as e:
                log.warning("feed %s error: %s", name, e)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    async def _poll_feed(self, db: aiosqlite.Connection, session: aiohttp.ClientSession, name: str, url: str) -> int:
        # feedparser is sync; fetch the bytes ourselves, then parse off-loop.
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=20),
                                   headers={"User-Agent": "Mozilla/5.0 (e10 watcher)"}) as r:
                if r.status != 200:
                    log.warning("feed %s http %d", name, r.status)
                    await self._record_feed_health(db, name, 0, None)
                    return 0
                body = await r.read()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            log.warning("feed %s fetch error: %s", name, e)
            await self._record_feed_health(db, name, 0, None)
            return 0

        parsed = await asyncio.to_thread(feedparser.parse, body)
        entries = parsed.get("entries") or []
        inserted = 0
        latest_pub_ts = 0
        seen_ts = now_utc_ms()
        for e in entries:
            guid = e.get("id") or e.get("guid") or e.get("link") or e.get("title")
            if not guid:
                continue
            title = e.get("title") or ""
            summary = e.get("summary") or e.get("description") or ""
            link = e.get("link") or ""
            pub_ts = _struct_to_ms(e.get("published_parsed") or e.get("updated_parsed"))
            best_ts = min(pub_ts, seen_ts) if pub_ts else seen_ts
            if pub_ts and pub_ts > latest_pub_ts:
                latest_pub_ts = pub_ts
            tokens = tokenise(title + " " + summary)
            try:
                cur = await db.execute(
                    """INSERT INTO news_items(source, guid, title, summary, url,
                                              pub_ts, seen_ts, best_ts, tokens_json)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (name, guid, title, summary, link, pub_ts, seen_ts, best_ts, json.dumps(tokens)),
                )
                if cur.rowcount > 0:
                    inserted += 1
            except aiosqlite.IntegrityError:
                pass   # duplicate
        await db.commit()
        self._news_count += inserted
        await self._record_feed_health(db, name, inserted, latest_pub_ts or None)
        return inserted

    async def _record_feed_health(self, db: aiosqlite.Connection, source: str,
                                  items_received: int, latest_pub_ts: int | None) -> None:
        await db.execute(
            "INSERT OR REPLACE INTO feed_health(source, ts, items_received, last_pub_ts) VALUES(?,?,?,?)",
            (source, now_utc_ms(), items_received, latest_pub_ts),
        )
        await db.commit()

    # ---- news matcher ----

    async def matcher_loop(self, db: aiosqlite.Connection) -> None:
        while not self._stop.is_set():
            try:
                await self._match_new_news(db)
            except asyncio.CancelledError:
                return
            except Exception as e:
                log.exception("matcher error: %s", e)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=NEWS_MATCH_INTERVAL_S)
            except asyncio.TimeoutError:
                pass

    async def _match_new_news(self, db: aiosqlite.Connection) -> None:
        # Find news_items not yet in news_market_matches (LEFT JOIN == NULL).
        async with db.execute(
            """SELECT ni.id, ni.tokens_json, ni.title
               FROM news_items ni
               WHERE NOT EXISTS (
                 SELECT 1 FROM news_market_matches m WHERE m.news_id = ni.id
               )
               ORDER BY ni.id DESC LIMIT 500"""
        ) as cur:
            rows = await cur.fetchall()
        if not rows:
            return
        # Build (news_id, market_id, kw_count) tuples, but only for matches ≥2.
        # Also insert a sentinel "no-match" row to prevent re-processing: we use
        # market_id='__nomatch__' to represent "processed but matched nothing".
        matches: list[tuple] = []
        NOMATCH = "__nomatch__"
        for news_id, tokens_json, title in rows:
            try:
                tokens = set(json.loads(tokens_json or "[]"))
            except json.JSONDecodeError:
                tokens = set()
            matched_any = False
            for m in self._markets:
                kws = [k.lower() for k in (m.get("keywords") or [])]
                hits = 0
                for k in kws:
                    # multi-word keyword: substring check against joined title
                    if " " in k:
                        if k in title.lower():
                            hits += 1
                    else:
                        if k in tokens:
                            hits += 1
                if hits >= 2:
                    matches.append((news_id, m["market_id"], hits))
                    matched_any = True
            if not matched_any:
                matches.append((news_id, NOMATCH, 0))
        if matches:
            await db.executemany(
                "INSERT OR IGNORE INTO news_market_matches(news_id, market_id, match_keyword_count) VALUES(?,?,?)",
                matches,
            )
            await db.commit()
            real = sum(1 for m in matches if m[1] != NOMATCH)
            self._match_count += real
            if real:
                log.info("matched %d news→market (total matches=%d)", real, self._match_count)

    # ---- discovery ----

    async def discovery_loop(self, session: aiohttp.ClientSession) -> None:
        api = PolymarketAPI(session)
        interval = SMOKE_DISCOVERY_INTERVAL_S if self.smoke else DISCOVERY_INTERVAL_S
        # Run once at startup so users see coverage right away.
        try:
            await self._run_discovery(api)
        except Exception as e:
            log.warning("initial discovery failed: %s", e)
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass
            if self._stop.is_set():
                return
            try:
                await self._run_discovery(api)
            except Exception as e:
                log.exception("discovery error: %s", e)

    async def _run_discovery(self, api: PolymarketAPI) -> None:
        """Slug-substring scan across top N markets by volume. Log new geo candidates."""
        tracked = {m["market_id"] for m in self._markets}
        new_candidates: list[dict] = []
        pages_scanned = 0
        for offset in range(0, 2000, 200):
            raws = await api._get_json(
                "/markets",
                {"closed": "false", "active": "true", "limit": "200",
                 "offset": str(offset), "order": "volume24hr", "ascending": "false"},
            )
            if not raws:
                break
            pages_scanned += 1
            for raw in raws:
                slug = (raw.get("slug") or "").lower()
                cid = raw.get("conditionId")
                if not cid or cid in tracked:
                    continue
                if CRYPTO_SLUG_RE.search(slug) or SPORTS_SLUG_RE.search(slug):
                    continue
                if not GEO_SLUG_RE.search(slug):
                    continue
                vol24 = raw.get("volume24hr") or 0
                if vol24 < 5000:
                    continue
                new_candidates.append({
                    "market_id": cid,
                    "slug": raw.get("slug"),
                    "question": raw.get("question"),
                    "end_date": raw.get("endDate"),
                    "volume_24hr": vol24,
                    "last_trade_price": raw.get("lastTradePrice"),
                    "discovered_at": now_utc_ms(),
                })
            if len(raws) < 200:
                break
        if new_candidates:
            CANDIDATES_JSONL.parent.mkdir(parents=True, exist_ok=True)
            with open(CANDIDATES_JSONL, "a") as f:
                for c in new_candidates:
                    f.write(json.dumps(c) + "\n")
            log.info("discovery: %d new geo candidates logged to %s (scanned %d pages)",
                     len(new_candidates), CANDIDATES_JSONL, pages_scanned)
        else:
            log.info("discovery: no new candidates (scanned %d pages)", pages_scanned)

    # ---- feed health monitor ----

    async def health_loop(self, db: aiosqlite.Connection) -> None:
        while not self._stop.is_set():
            try:
                await self._summarise_feed_health(db)
            except asyncio.CancelledError:
                return
            except Exception as e:
                log.warning("health summary error: %s", e)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=FEED_HEALTH_INTERVAL_S)
            except asyncio.TimeoutError:
                pass

    async def _summarise_feed_health(self, db: aiosqlite.Connection) -> None:
        now = now_utc_ms()
        async with db.execute(
            """SELECT source, MAX(last_pub_ts), MAX(ts)
               FROM feed_health GROUP BY source"""
        ) as cur:
            rows = await cur.fetchall()
        silent = []
        for source, last_pub, last_seen in rows:
            last_signal = last_pub or last_seen or 0
            mins_ago = (now - last_signal) / 60000 if last_signal else 0
            if mins_ago > 180:   # 3h threshold from README
                silent.append((source, mins_ago))
        if silent:
            for src, mins in silent:
                log.warning("feed silent >3h: %s (%.0f min since last publish)", src, mins)

    # ---- run ----

    async def run(self, duration_s: float) -> None:
        db = await self._open_db()
        await self._load_config(db)

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._stop.set)

        connector = aiohttp.TCPConnector(limit=20)
        session = aiohttp.ClientSession(connector=connector,
                                        headers={"User-Agent": "event-impact-e10/0.1"})
        try:
            tasks = [
                asyncio.create_task(self.snapshot_loop(db, session), name="snapshot"),
                asyncio.create_task(self.matcher_loop(db), name="matcher"),
                asyncio.create_task(self.discovery_loop(session), name="discovery"),
                asyncio.create_task(self.health_loop(db), name="health"),
            ]
            for feed in self._feeds:
                tasks.append(asyncio.create_task(
                    self.news_feed_loop(db, session, feed), name=f"feed-{feed['name']}"
                ))

            async def deadline():
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=duration_s)
                except asyncio.TimeoutError:
                    log.info("duration reached (%ds), stopping", int(duration_s))
                    self._stop.set()

            tasks.append(asyncio.create_task(deadline(), name="deadline"))
            log.info("watcher running: duration=%.1fh db=%s smoke=%s",
                     duration_s / 3600, self.db_path, self.smoke)
            await self._stop.wait()
            log.info("shutdown signaled")
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            await session.close()
            await db.close()
            log.info("watcher stopped. snapshots=%d news=%d matches=%d",
                     self._snapshot_count, self._news_count, self._match_count)


def _as_float(v):
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_end_ms(iso_str: str | None) -> int | None:
    if not iso_str:
        return None
    try:
        from datetime import datetime
        return int(datetime.fromisoformat(iso_str.replace("Z", "+00:00")).timestamp() * 1000)
    except Exception:
        return None


def _struct_to_ms(tm) -> int | None:
    if not tm:
        return None
    try:
        # feedparser's *_parsed is a time.struct_time in UTC
        return int(time.mktime(tm) * 1000) - int(time.timezone * 1000)
    except Exception:
        return None


async def amain(args) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    db_path = Path(args.db) if args.db else DEFAULT_DB
    w = Watcher(db_path=db_path, smoke=args.smoke)
    await w.run(duration_s=args.hours * 3600)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--hours", type=float, default=48.0)
    p.add_argument("--db", default=None, help="override e10.db path")
    p.add_argument("--smoke", action="store_true",
                   help="trim to 3 markets + 2 feeds, tighter cadence for quick validation")
    args = p.parse_args()
    asyncio.run(amain(args))


if __name__ == "__main__":
    main()
