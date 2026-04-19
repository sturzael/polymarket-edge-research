"""SQLite sidecar helpers — schema init, detection logging, position context."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import config


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    config.SIDECAR_DB.parent.mkdir(parents=True, exist_ok=True)
    schema = config.SCHEMA_SQL.read_text()
    with sqlite3.connect(config.SIDECAR_DB) as conn:
        conn.executescript(schema)


def conn() -> sqlite3.Connection:
    c = sqlite3.connect(config.SIDECAR_DB, timeout=30)
    c.row_factory = sqlite3.Row
    return c


# --- daemon state ---

def get_state(key: str) -> str | None:
    with conn() as c:
        row = c.execute("SELECT value FROM daemon_state WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_state(key: str, value: str) -> None:
    with conn() as c:
        c.execute(
            "INSERT INTO daemon_state (key, value) VALUES (?, ?) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def is_paused() -> bool:
    return get_state("paused") == "1"


def current_protocol_version() -> str:
    return get_state("protocol_version") or "v1"


# --- detections ---

def log_detection(*, account: str | None, strategy: str, detection_path: str,
                  market_slug: str, event_id: str | None,
                  last_trade: float | None, best_ask: float | None,
                  ask_size: float | None,
                  skipped_reason: str | None = None,
                  fill_attempted_at: str | None = None) -> int:
    with conn() as c:
        cur = c.execute(
            """INSERT INTO detections
               (ts, account, strategy, detection_path, market_slug, event_id,
                last_trade, best_ask, ask_size, skipped_reason, fill_attempted_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (_now_iso(), account, strategy, detection_path, market_slug, event_id,
             last_trade, best_ask, ask_size, skipped_reason, fill_attempted_at),
        )
        return cur.lastrowid


def update_detection_fill(det_id: int, *, fill_completed_at: str,
                          fill_price: float, fill_qty: float,
                          latency_ms: int, slippage_bps: float) -> None:
    with conn() as c:
        c.execute(
            """UPDATE detections
               SET fill_completed_at = ?, fill_price = ?, fill_qty = ?,
                   latency_ms = ?, slippage_bps = ?
               WHERE id = ?""",
            (fill_completed_at, fill_price, fill_qty, latency_ms, slippage_bps, det_id),
        )


# --- position_context ---

def insert_position_context(*, pm_trade_id: str, account: str,
                            strategy: str, size_model: str, entry_cap: float,
                            detection_path: str, market_slug: str,
                            event_id: str | None, side: str,
                            entry_ask: float, entry_bid: float | None,
                            ask_size_at_entry: float,
                            protocol_version: str,
                            market_context: dict | None = None) -> None:
    with conn() as c:
        c.execute(
            """INSERT OR REPLACE INTO position_context
               (pm_trade_id, account, strategy, size_model, entry_cap,
                detection_path, market_slug, event_id, side, detected_at,
                entry_ask, entry_bid, ask_size_at_entry, protocol_version,
                market_context, resolution_status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')""",
            (pm_trade_id, account, strategy, size_model, entry_cap,
             detection_path, market_slug, event_id, side, _now_iso(),
             entry_ask, entry_bid, ask_size_at_entry, protocol_version,
             json.dumps(market_context or {})),
        )


def open_positions(account: str | None = None) -> list[sqlite3.Row]:
    with conn() as c:
        if account:
            return list(c.execute(
                "SELECT * FROM position_context WHERE account = ? AND resolution_status = 'open'",
                (account,),
            ))
        return list(c.execute("SELECT * FROM position_context WHERE resolution_status = 'open'"))


def update_resolution(pm_trade_id: str, *, resolution_price: float,
                      resolution_status: str) -> None:
    with conn() as c:
        c.execute(
            "UPDATE position_context SET resolved_at = ?, resolution_price = ?, resolution_status = ? WHERE pm_trade_id = ?",
            (_now_iso(), resolution_price, resolution_status, pm_trade_id),
        )


def total_completed_trades_per_cell() -> dict[str, int]:
    with conn() as c:
        rows = c.execute(
            """SELECT account, COUNT(*) AS n
               FROM position_context
               WHERE resolution_status IN ('resolved_win', 'resolved_loss')
               GROUP BY account"""
        ).fetchall()
    return {r["account"]: r["n"] for r in rows}


# --- missed opportunities ---

def log_missed_opportunity(*, market_slug: str, event_id: str | None,
                            detected_via: str, arb_window_start_ts: str,
                            arb_window_end_ts: str,
                            best_price_observed: float,
                            total_capturable_usd: float,
                            reason_we_missed: str,
                            our_detection_id: int | None = None,
                            our_fill_id: str | None = None) -> None:
    with conn() as c:
        c.execute(
            """INSERT INTO missed_opportunities
               (market_slug, event_id, detected_via, arb_window_start_ts,
                arb_window_end_ts, best_price_observed, total_capturable_usd,
                reason_we_missed, our_detection_id, our_fill_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (market_slug, event_id, detected_via, arb_window_start_ts,
             arb_window_end_ts, best_price_observed, total_capturable_usd,
             reason_we_missed, our_detection_id, our_fill_id),
        )
