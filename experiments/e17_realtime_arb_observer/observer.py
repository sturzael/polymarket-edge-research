"""Real-time Polymarket neg-risk arb observer.

Subscribes to Polymarket's public WebSocket, maintains in-memory orderbook
state for all children of all GUARANTEED neg-risk events, and logs every
moment where sum_asks < 1.0 (a live arb). No trading — observation only.

Purpose: answer "how fast do these arbs die" before we spend on VPS+execution
infrastructure. Saguillo 2025 said median arb duration 2.7s for general arbs
on Polymarket. Our data to build from there.

Architecture:
  - Gamma API once per 15 min: enumerate active GUARANTEED neg-risk events,
    extract asset_ids (token1 of each active child — the YES token).
  - WebSocket subscribe to those asset_ids.
  - On initial 'book' snapshot: seed in-memory book for that asset.
  - On 'price_change' delta: apply delta to in-memory book.
  - After every update of any asset in an event, recompute sum_asks for that
    event. If sum_asks drops below 1.0: write arb_started row. If it comes
    back above: write arb_ended row (or periodic extend).

Output: data/observer.db with tables scans, arbs, ticks. Plus arb_log.jsonl.

Usage:
    uv run python -m experiments.e17_realtime_arb_observer.observer
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sqlite3
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
import websockets

DATA_DIR = Path(__file__).parent / "data"
DB = DATA_DIR / "observer.db"
LOG = DATA_DIR / "observer.log"
GAMMA = "https://gamma-api.polymarket.com"
WSS = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

# From e15 scanner.py — keep in sync
PLACEHOLDER_SLUGS = ("will-option-", "will-other-")
PLACEHOLDER_REGEX = re.compile(r"(?:^|-)(player|option|candidate|other)-\d+$", re.IGNORECASE)
COMPLETENESS_RED_FLAGS = (
    "may be added", "added at a later date", "will be added",
    "additional candidates", "other candidates",
)

REFRESH_EVENT_UNIVERSE_SECONDS = 15 * 60
ARB_GAP_CLOSE_SECONDS = 3.0  # if no update in 3s, assume the arb ended

SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    id           INTEGER PRIMARY KEY,
    scan_at      TEXT NOT NULL,
    n_events     INTEGER NOT NULL,
    n_assets     INTEGER NOT NULL,
    notes        TEXT
);

-- One row per arb detection (contiguous period where sum_asks < 1.0).
CREATE TABLE IF NOT EXISTS arbs (
    id                INTEGER PRIMARY KEY,
    event_slug        TEXT NOT NULL,
    condition_id      TEXT NOT NULL,
    started_at        TEXT NOT NULL,   -- our observer's wall-clock time
    ended_at          TEXT,            -- NULL if still live
    duration_ms       INTEGER,
    min_sum_asks      REAL NOT NULL,
    avg_sum_asks      REAL,
    max_edge_pct      REAL NOT NULL,   -- = (1 - min_sum_asks) * 100
    n_legs            INTEGER NOT NULL,
    first_server_ts   INTEGER,         -- server timestamp on first tick that triggered it
    first_local_ts_ms INTEGER,         -- our observer's monotonic time at receipt
    n_updates         INTEGER NOT NULL DEFAULT 1,
    phantom           INTEGER NOT NULL DEFAULT 0  -- 1 if min_sum_asks < 0.05
);

CREATE INDEX IF NOT EXISTS idx_arbs_event ON arbs (event_slug);
CREATE INDEX IF NOT EXISTS idx_arbs_started ON arbs (started_at);

-- Raw tick log for latency analysis — optional, gated by env var to keep small
CREATE TABLE IF NOT EXISTS ticks (
    id               INTEGER PRIMARY KEY,
    server_ts        INTEGER,
    local_ts_ms      INTEGER NOT NULL,
    event_slug       TEXT NOT NULL,
    sum_asks         REAL NOT NULL,
    is_arb           INTEGER NOT NULL
);
"""


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    line = f"[{ts}] {msg}"
    print(line, flush=True)


def init_db() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with sqlite3.connect(DB) as c:
        c.executescript(SCHEMA)


# ---------- Gamma universe enumeration ----------


def parse_token_ids(raw) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return []
    return raw if isinstance(raw, list) else []


def classify_guaranteed(event: dict) -> bool:
    """Return True if event meets GUARANTEED criteria (no placeholders, no
    red-flag language, >= 2 active children)."""
    desc = (event.get("description") or "").lower()
    if any(rf in desc for rf in COMPLETENESS_RED_FLAGS):
        return False
    markets = event.get("markets", [])
    active = [m for m in markets if m.get("active") and not m.get("closed")]
    if len(active) < 2:
        return False
    for m in markets:
        slug = m.get("slug") or ""
        if any(slug.startswith(p) for p in PLACEHOLDER_SLUGS):
            return False
        if PLACEHOLDER_REGEX.search(slug):
            return False
    return True


def fetch_universe() -> dict:
    """Return {'events': [{slug, condition_id, yes_token_ids: [str]}], 'all_assets': set}."""
    events_out = []
    all_assets = set()
    with httpx.Client(timeout=20) as c:
        r = c.get(f"{GAMMA}/events",
                  params={"closed": "false", "active": "true", "limit": 500})
        events = r.json() if r.status_code == 200 else []
    for e in events:
        if not e.get("negRisk"):
            continue
        if not classify_guaranteed(e):
            continue
        yes_tokens = []
        for m in e.get("markets", []):
            if not m.get("active") or m.get("closed"):
                continue
            tids = parse_token_ids(m.get("clobTokenIds"))
            if tids:
                yes_tokens.append(tids[0])  # token1 = YES
        if len(yes_tokens) < 2:
            continue
        events_out.append({
            "slug": e.get("slug", ""),
            "condition_id": e.get("conditionId") or e.get("condition_id") or "",
            "yes_token_ids": yes_tokens,
        })
        all_assets.update(yes_tokens)
    return {"events": events_out, "all_assets": all_assets}


# ---------- In-memory state ----------


class BookState:
    """Minimal orderbook: per-asset best-ask price. We don't need full book
    depth for the observer — we only care about sum(best_ask) across a basket.
    """
    def __init__(self) -> None:
        self.best_ask: dict[str, float] = {}  # asset_id -> best ask price
        self.last_update_server_ts: dict[str, int] = {}
        self.last_update_local_ts_ms: dict[str, int] = {}

    def apply_book_snapshot(self, asset_id: str, book: dict, server_ts: int) -> None:
        """Book message schema: { market, asset_id, timestamp, hash,
        bids: [{price, size}, ...], asks: [{price, size}, ...] }
        """
        asks = book.get("asks", [])
        if not asks:
            self.best_ask.pop(asset_id, None)
        else:
            # asks sorted? We don't assume. Find min price with size > 0.
            candidates = []
            for a in asks:
                try:
                    p = float(a.get("price"))
                    s = float(a.get("size") or 0)
                    if s > 0 and 0 < p <= 1:
                        candidates.append(p)
                except Exception:
                    continue
            if candidates:
                self.best_ask[asset_id] = min(candidates)
            else:
                self.best_ask.pop(asset_id, None)
        self.last_update_server_ts[asset_id] = server_ts
        self.last_update_local_ts_ms[asset_id] = int(time.monotonic() * 1000)

    def apply_price_change(self, asset_id: str, changes: list, server_ts: int) -> None:
        """price_change message schema: { market, price_changes: [{asset_id,
        price, side, size, hash}], timestamp }

        We need to track the full ask levels to know "best ask" correctly
        after a delta. But we only stored best_ask (a scalar). To keep the
        observer simple, we instead re-poll the book on any ask-side update
        where the size change might affect best_ask.

        Simpler approximation: treat each price_change as informational about
        a single level. If a new ask price is LOWER than current best, update.
        If size on current best-ask drops to 0, we need a full book refresh —
        mark stale so next book-snapshot takes precedence.
        """
        # For observer v1, we treat every price_change as a refresh signal
        # and rely on periodic book refreshes (the WS sends them periodically
        # on subscribe). This is imperfect for fast arb detection but captures
        # the macro signal reliably.
        # Detailed implementation punt: in v2, we'd maintain full ask level
        # map per asset and compute min() properly on every tick.
        for ch in changes:
            if ch.get("asset_id") != asset_id:
                continue
            if ch.get("side", "").upper() != "SELL":
                continue  # asks only
            try:
                p = float(ch.get("price"))
                s = float(ch.get("size") or 0)
            except Exception:
                continue
            if not (0 < p <= 1):
                continue
            current = self.best_ask.get(asset_id)
            if s > 0 and (current is None or p < current):
                self.best_ask[asset_id] = p
            elif s == 0 and current is not None and abs(p - current) < 1e-9:
                # Our best-ask level hit 0 size. We don't know the next-best.
                # Mark unknown (remove). The next book snapshot will restore.
                self.best_ask.pop(asset_id, None)
        self.last_update_server_ts[asset_id] = server_ts
        self.last_update_local_ts_ms[asset_id] = int(time.monotonic() * 1000)


# ---------- Arb detection + logging ----------


class ArbTracker:
    """Maintains 'currently-live' arb state per event + writes rows when they
    open/close."""
    def __init__(self) -> None:
        self.live: dict[str, dict] = {}  # event_slug -> live arb state

    def on_event_tick(self, conn: sqlite3.Connection, event: dict,
                      book: BookState, server_ts: int) -> None:
        asks = [book.best_ask.get(a) for a in event["yes_token_ids"]]
        if any(a is None for a in asks):
            # Incomplete book — can't compute sum_asks
            return
        sum_asks = sum(asks)
        is_arb = sum_asks < 1.0
        live = self.live.get(event["slug"])
        local_ts_ms = int(time.monotonic() * 1000)
        now = datetime.now(timezone.utc).isoformat()

        # Log raw tick — only during live arbs (sum_asks < 1.0), so volume stays modest.
        # If we need near-arb data for latency studies, widen this threshold.
        if is_arb:
            conn.execute(
                "INSERT INTO ticks (server_ts, local_ts_ms, event_slug, sum_asks, is_arb) "
                "VALUES (?, ?, ?, ?, ?)",
                (server_ts, local_ts_ms, event["slug"], round(sum_asks, 5), int(is_arb)),
            )

        if is_arb:
            if live is None:
                # New arb
                phantom = 1 if sum_asks < 0.05 else 0
                cur = conn.execute(
                    """INSERT INTO arbs (event_slug, condition_id, started_at,
                        min_sum_asks, avg_sum_asks, max_edge_pct, n_legs,
                        first_server_ts, first_local_ts_ms, n_updates, phantom)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
                    (event["slug"], event["condition_id"], now,
                     round(sum_asks, 5), round(sum_asks, 5),
                     round((1 - sum_asks) * 100, 3), len(asks),
                     server_ts, local_ts_ms, phantom),
                )
                arb_id = cur.lastrowid
                self.live[event["slug"]] = {
                    "arb_id": arb_id,
                    "min_sum_asks": sum_asks,
                    "sum_total": sum_asks,
                    "n_updates": 1,
                    "last_local_ts_ms": local_ts_ms,
                    "phantom": phantom,
                }
                _log(f"arb OPEN {event['slug'][:50]} sum_asks={sum_asks:.4f} "
                     f"edge={100*(1-sum_asks):+.2f}% legs={len(asks)}"
                     f"{' [PHANTOM]' if phantom else ''}")
            else:
                # Update existing arb
                live["min_sum_asks"] = min(live["min_sum_asks"], sum_asks)
                live["sum_total"] += sum_asks
                live["n_updates"] += 1
                live["last_local_ts_ms"] = local_ts_ms
                if sum_asks < 0.05:
                    live["phantom"] = 1
                conn.execute(
                    "UPDATE arbs SET min_sum_asks = ?, avg_sum_asks = ?, "
                    "max_edge_pct = ?, n_updates = ?, phantom = ? WHERE id = ?",
                    (round(live["min_sum_asks"], 5),
                     round(live["sum_total"] / live["n_updates"], 5),
                     round((1 - live["min_sum_asks"]) * 100, 3),
                     live["n_updates"], live["phantom"], live["arb_id"]),
                )
        else:
            if live is not None:
                # Arb closed
                duration_ms = local_ts_ms - live["last_local_ts_ms"]
                duration_total_ms = local_ts_ms - (
                    live.get("first_local_ts_ms") or live["last_local_ts_ms"]
                )
                # Pull first_local_ts from row
                conn.execute(
                    """UPDATE arbs SET ended_at = ?, duration_ms = ? WHERE id = ?""",
                    (now,
                     int(local_ts_ms - (conn.execute(
                         "SELECT first_local_ts_ms FROM arbs WHERE id=?",
                         (live["arb_id"],)).fetchone()[0] or local_ts_ms)),
                     live["arb_id"]),
                )
                _log(f"arb CLOSE {event['slug'][:50]} "
                     f"duration={duration_ms}ms min_edge={100*(1-live['min_sum_asks']):+.2f}%")
                self.live.pop(event["slug"], None)

    def gap_sweep(self, conn: sqlite3.Connection) -> None:
        """Close any live arbs whose last update is older than
        ARB_GAP_CLOSE_SECONDS ago — treat as ended."""
        now_ms = int(time.monotonic() * 1000)
        gap_ms = int(ARB_GAP_CLOSE_SECONDS * 1000)
        closed = []
        for slug, live in list(self.live.items()):
            if now_ms - live["last_local_ts_ms"] > gap_ms:
                first = conn.execute(
                    "SELECT first_local_ts_ms FROM arbs WHERE id=?",
                    (live["arb_id"],)).fetchone()[0] or now_ms
                conn.execute(
                    "UPDATE arbs SET ended_at = ?, duration_ms = ? WHERE id = ?",
                    (datetime.now(timezone.utc).isoformat(),
                     now_ms - first, live["arb_id"]),
                )
                closed.append(slug)
                _log(f"arb TIMEOUT {slug[:50]} (no update in {ARB_GAP_CLOSE_SECONDS}s)")
        for s in closed:
            self.live.pop(s, None)


# ---------- Main loop ----------


async def run(max_assets: int = 1000, refresh_seconds: int = REFRESH_EVENT_UNIVERSE_SECONDS):
    init_db()
    # Mark any arbs left open by a previous process as orphaned —
    # in-memory state was lost on restart, so we can't meaningfully close them.
    # Prevents the `arbs` table accumulating zombies forever.
    with sqlite3.connect(DB) as c:
        cur = c.execute(
            "UPDATE arbs SET ended_at = ?, duration_ms = NULL, "
            "avg_sum_asks = COALESCE(avg_sum_asks, min_sum_asks) "
            "WHERE ended_at IS NULL",
            (datetime.now(timezone.utc).isoformat(),),
        )
        c.commit()
        if cur.rowcount > 0:
            _log(f"orphan cleanup: marked {cur.rowcount} pre-restart arbs as ended (duration=NULL)")
    _log("fetching event universe...")
    universe = fetch_universe()
    events = universe["events"]
    all_assets = list(universe["all_assets"])[:max_assets]
    _log(f"universe: {len(events)} events, {len(all_assets)} assets "
         f"(capped at {max_assets})")

    # Build asset -> event(s) map
    asset_to_events = defaultdict(list)
    for e in events:
        for a in e["yes_token_ids"]:
            if a in all_assets:
                asset_to_events[a].append(e)

    with sqlite3.connect(DB) as conn:
        conn.execute(
            "INSERT INTO scans (scan_at, n_events, n_assets, notes) VALUES (?, ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), len(events), len(all_assets),
             "initial"),
        )
        conn.commit()

    book = BookState()
    tracker = ArbTracker()

    _log(f"connecting to {WSS}...")
    async with websockets.connect(WSS, max_size=2**24, ping_interval=20) as ws:
        sub = {"assets_ids": all_assets, "type": "market"}
        await ws.send(json.dumps(sub))
        _log(f"subscribed to {len(all_assets)} assets")

        last_refresh_t = time.monotonic()
        last_gap_sweep_t = time.monotonic()
        conn = sqlite3.connect(DB)

        async for raw in ws:
            try:
                data = json.loads(raw) if raw and raw[:1] in "[{" else None
                if data is None:
                    continue
                # Normalize: book snapshots come as list of snapshots; price_changes as dict
                if isinstance(data, list):
                    messages = data
                else:
                    messages = [data]

                affected_events: set[str] = set()
                for m in messages:
                    server_ts = None
                    try:
                        server_ts = int(m.get("timestamp") or 0)
                    except Exception:
                        pass
                    asset_id = m.get("asset_id")
                    if "asks" in m and asset_id:
                        # Full book snapshot
                        book.apply_book_snapshot(asset_id, m, server_ts or 0)
                        for ev in asset_to_events.get(asset_id, []):
                            affected_events.add(ev["slug"])
                    elif "price_changes" in m:
                        changes = m.get("price_changes", [])
                        for ch in changes:
                            aid = ch.get("asset_id")
                            if aid:
                                book.apply_price_change(aid, [ch], server_ts or 0)
                                for ev in asset_to_events.get(aid, []):
                                    affected_events.add(ev["slug"])

                # Recompute sum_asks for every affected event
                now_server_ts = int(time.time())
                slug_to_event = {e["slug"]: e for e in events}
                for slug in affected_events:
                    ev = slug_to_event.get(slug)
                    if ev is None:
                        continue
                    tracker.on_event_tick(conn, ev, book, now_server_ts)

                # Periodic gap sweep
                if time.monotonic() - last_gap_sweep_t > 5:
                    tracker.gap_sweep(conn)
                    conn.commit()
                    last_gap_sweep_t = time.monotonic()

                # Periodic universe refresh (reconnect with new assets)
                if time.monotonic() - last_refresh_t > refresh_seconds:
                    _log("refresh interval hit — exiting to let launchd restart + re-enumerate universe")
                    conn.close()
                    return
            except Exception as e:
                _log(f"message error: {type(e).__name__}: {e}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-assets", type=int, default=1000)
    ap.add_argument("--refresh-minutes", type=float, default=30.0)
    args = ap.parse_args()
    try:
        asyncio.run(run(max_assets=args.max_assets,
                        refresh_seconds=int(args.refresh_minutes * 60)))
    except KeyboardInterrupt:
        _log("interrupted")
    except Exception as e:
        _log(f"fatal: {type(e).__name__}: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
