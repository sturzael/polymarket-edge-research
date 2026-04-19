"""Hourly arb logger — durable scanner that runs forever, writes JSONL.

Per the user's revised plan: build the scanner as a research instrument
first; over weeks of data we'll know how often standing violations appear,
how long they persist, and what their typical edge shape is.

Storage: one row per opportunity per scan. Each row links to a scan_at
timestamp so we can reconstruct "which arbs were live at this moment"
or "how did this specific event evolve over time."

Run in tmux:
    uv run python -m experiments.e15_neg_risk_arb.logger

Defaults to 60-min interval. Override with --interval-min N.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import scanner

DATA_DIR = Path(__file__).parent / "data"
LOG_DB = DATA_DIR / "arb_log.db"


SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    scan_id     INTEGER PRIMARY KEY,
    scan_at     TEXT NOT NULL,
    n_opps      INTEGER NOT NULL,
    n_guaranteed INTEGER NOT NULL,
    n_probabilistic INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS arbs (
    id              INTEGER PRIMARY KEY,
    scan_id         INTEGER NOT NULL REFERENCES scans(scan_id),
    event_slug      TEXT NOT NULL,
    completeness    TEXT NOT NULL,
    edge_pct        REAL NOT NULL,
    sum_asks        REAL NOT NULL,
    sum_bids        REAL NOT NULL,
    n_active        INTEGER NOT NULL,
    n_inactive_placeholders INTEGER NOT NULL,
    days_to_resolution REAL,
    min_executable_sets REAL,
    max_profit_usd  REAL,
    legs_json       TEXT
);

CREATE INDEX IF NOT EXISTS idx_arbs_event ON arbs (event_slug);
CREATE INDEX IF NOT EXISTS idx_arbs_scan ON arbs (scan_id);
CREATE INDEX IF NOT EXISTS idx_arbs_edge ON arbs (edge_pct);
"""


def init_db() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with sqlite3.connect(LOG_DB) as conn:
        conn.executescript(SCHEMA)


def write_scan(opps: list[scanner.Opportunity]) -> int:
    n_g = sum(1 for o in opps if o.completeness == "GUARANTEED")
    n_p = sum(1 for o in opps if o.completeness == "PROBABILISTIC")
    with sqlite3.connect(LOG_DB) as conn:
        cur = conn.execute(
            "INSERT INTO scans (scan_at, n_opps, n_guaranteed, n_probabilistic) VALUES (?, ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), len(opps), n_g, n_p),
        )
        scan_id = cur.lastrowid
        for o in opps:
            conn.execute(
                """INSERT INTO arbs
                   (scan_id, event_slug, completeness, edge_pct, sum_asks, sum_bids,
                    n_active, n_inactive_placeholders, days_to_resolution,
                    min_executable_sets, max_profit_usd, legs_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (scan_id, o.event_slug, o.completeness, o.edge_pct,
                 o.sum_asks, o.sum_bids, o.n_active, o.n_inactive_placeholders,
                 o.days_to_resolution, o.min_executable_sets, o.max_profit_usd,
                 json.dumps([{"slug": l.slug, "ask": l.best_ask, "bid": l.best_bid,
                              "ask_depth": l.ask_depth, "bid_depth": l.bid_depth}
                             for l in o.legs])),
            )
        return scan_id


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval-min", type=float, default=60.0)
    ap.add_argument("--with-depth", action="store_true", default=True,
                    help="fetch order book depth (default: yes)")
    ap.add_argument("--once", action="store_true", help="run one scan and exit")
    args = ap.parse_args()

    init_db()
    while True:
        try:
            t0 = time.time()
            opps = scanner.scan(check_depth=args.with_depth)
            scan_id = write_scan(opps)
            print(f"[{datetime.now(timezone.utc).isoformat()}] scan_id={scan_id} "
                  f"opps={len(opps)} (G={sum(1 for o in opps if o.completeness=='GUARANTEED')}, "
                  f"P={sum(1 for o in opps if o.completeness=='PROBABILISTIC')}) "
                  f"in {time.time()-t0:.0f}s")
        except Exception as e:
            print(f"[{datetime.now(timezone.utc).isoformat()}] scan ERROR: {type(e).__name__}: {e}")
        if args.once:
            break
        time.sleep(args.interval_min * 60)


if __name__ == "__main__":
    sys.exit(main() or 0)
