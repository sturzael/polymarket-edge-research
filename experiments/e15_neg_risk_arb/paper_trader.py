"""Scanner-driven paper-trader for neg-risk multi-leg arbs at $5k bankroll.

Extends forward_trader (which tracks 6 hand-picked events) with a scanner-driven
mode: every tick, scanner.scan() finds qualifying GUARANTEED arbs; any that we
don't already hold get auto-entered at simulated best-ask prices, sized by
MAX_PER_POSITION_USD capped by min_executable_sets × sum_asks.

Exits only at resolution (Q3 finding: neg-risk arbs end abruptly, no decay).

Fees are NOT applied at entry — entry cost records raw fill. report.py re-scores
PnL under --fee-bps X, matching the e12 pattern.

Schema:
  positions  — one row per entered arb (UNIQUE event_slug)
  closures   — one row per resolved position (FK positions.id)
  ticks      — one row per scan cycle, for audit/debug

Usage:
  uv run python -m experiments.e15_neg_risk_arb.paper_trader tick
  uv run python -m experiments.e15_neg_risk_arb.paper_trader loop --interval-min 60
  uv run python -m experiments.e15_neg_risk_arb.paper_trader status
  uv run python -m experiments.e15_neg_risk_arb.paper_trader report --fee-bps 0
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from . import scanner
from .forward_trader import fetch_event, parse_outcome_prices

DATA_DIR = Path(__file__).parent / "data"
DB = DATA_DIR / "paper_trader.db"

BANKROLL_USD = 5000.0
MAX_PER_POSITION_USD = 500.0
MIN_EDGE_PCT = 1.0
MIN_DAYS_TO_RES = 0.5
MAX_DAYS_TO_RES = 90.0
ALLOWED_COMPLETENESS = ("GUARANTEED",)
# Uncapped for learning: enter every qualifying opportunity. Real deployment
# would enforce a lower cap — this is paper-trade research mode.
MAX_CONCURRENT = 200

SCHEMA = """
CREATE TABLE IF NOT EXISTS ticks (
    id              INTEGER PRIMARY KEY,
    tick_at         TEXT NOT NULL,
    n_opps_seen     INTEGER NOT NULL,
    n_qualifying    INTEGER NOT NULL,
    n_entered       INTEGER NOT NULL,
    n_skipped_cap   INTEGER NOT NULL,
    n_resolved      INTEGER NOT NULL,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS positions (
    id                    INTEGER PRIMARY KEY,
    event_slug            TEXT NOT NULL UNIQUE,
    entry_tick_id         INTEGER REFERENCES ticks(id),
    entry_at              TEXT NOT NULL,
    entry_cost            REAL NOT NULL,
    sets_bought           REAL NOT NULL,
    sum_asks_at_entry     REAL NOT NULL,
    edge_pct_at_entry     REAL NOT NULL,
    n_legs                INTEGER NOT NULL,
    completeness          TEXT NOT NULL,
    days_to_res_at_entry  REAL,
    legs_json             TEXT NOT NULL,
    status                TEXT NOT NULL DEFAULT 'open'
);

CREATE TABLE IF NOT EXISTS closures (
    position_id      INTEGER PRIMARY KEY REFERENCES positions(id),
    closed_at        TEXT NOT NULL,
    winning_slug     TEXT,
    realized_payout  REAL NOT NULL,
    realized_pnl     REAL NOT NULL,
    hold_days        REAL NOT NULL,
    notes            TEXT
);

CREATE INDEX IF NOT EXISTS idx_pos_status ON positions (status);
"""


def init_db() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with sqlite3.connect(DB) as c:
        c.executescript(SCHEMA)


def open_positions(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return conn.execute("SELECT * FROM positions WHERE status='open'").fetchall()


def qualifies(opp: scanner.Opportunity) -> bool:
    if opp.completeness not in ALLOWED_COMPLETENESS:
        return False
    if opp.edge_pct < MIN_EDGE_PCT:
        return False
    if opp.days_to_resolution is None:
        return False
    if not (MIN_DAYS_TO_RES <= opp.days_to_resolution <= MAX_DAYS_TO_RES):
        return False
    if opp.min_executable_sets is None or opp.min_executable_sets <= 0:
        return False
    return True


def size_position(opp: scanner.Opportunity) -> tuple[float, float]:
    """Returns (entry_cost_usd, sets_bought).

    Cap by: MAX_PER_POSITION_USD, available book depth (min_executable_sets),
    and sum_asks (cost per set).
    """
    max_sets_by_budget = MAX_PER_POSITION_USD / opp.sum_asks
    max_sets_by_depth = opp.min_executable_sets or 0.0
    sets = min(max_sets_by_budget, max_sets_by_depth)
    entry_cost = sets * opp.sum_asks
    return round(entry_cost, 4), round(sets, 4)


def enter_position(conn: sqlite3.Connection, tick_id: int, opp: scanner.Opportunity) -> int:
    entry_cost, sets = size_position(opp)
    legs_payload = [
        {"slug": l.slug, "yes_token_id": l.yes_token_id,
         "ask": l.best_ask, "bid": l.best_bid,
         "ask_depth": l.ask_depth, "bid_depth": l.bid_depth}
        for l in opp.legs
    ]
    cur = conn.execute(
        """INSERT INTO positions
           (event_slug, entry_tick_id, entry_at, entry_cost, sets_bought,
            sum_asks_at_entry, edge_pct_at_entry, n_legs, completeness,
            days_to_res_at_entry, legs_json, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')""",
        (opp.event_slug, tick_id, datetime.now(timezone.utc).isoformat(),
         entry_cost, sets, opp.sum_asks, opp.edge_pct, opp.n_active,
         opp.completeness, opp.days_to_resolution, json.dumps(legs_payload)),
    )
    return cur.lastrowid


def try_resolve(conn: sqlite3.Connection, pos: sqlite3.Row, client: httpx.Client) -> bool:
    event = fetch_event(pos["event_slug"], client)
    if not event or not event.get("closed"):
        return False
    winner = None
    for m in event.get("markets", []):
        if not m.get("active"):
            continue
        op = parse_outcome_prices(m.get("outcomePrices"))
        if op and op[0] == 1.0:
            winner = m.get("slug")
            break
    realized_payout = pos["sets_bought"] if winner else 0.0
    realized_pnl = realized_payout - pos["entry_cost"]
    entry_dt = datetime.fromisoformat(pos["entry_at"])
    hold_days = (datetime.now(timezone.utc) - entry_dt).total_seconds() / 86400.0
    notes = "" if winner else "TAIL: no listed candidate won (unexpected for GUARANTEED)"
    conn.execute(
        """INSERT OR REPLACE INTO closures
           (position_id, closed_at, winning_slug, realized_payout,
            realized_pnl, hold_days, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (pos["id"], datetime.now(timezone.utc).isoformat(),
         winner, realized_payout, realized_pnl, round(hold_days, 2), notes),
    )
    conn.execute("UPDATE positions SET status='closed' WHERE id=?", (pos["id"],))
    return True


def cmd_tick(dry_run: bool = False) -> None:
    init_db()
    print(f"[{datetime.now(timezone.utc).isoformat()}] scanning...")
    opps = scanner.scan(check_depth=True)
    print(f"  found {len(opps)} opps total")

    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        existing = {r["event_slug"] for r in conn.execute(
            "SELECT event_slug FROM positions").fetchall()}
        open_rows = open_positions(conn)

        n_qualifying = 0
        entries = []
        skipped_cap = 0
        for opp in opps:
            if not qualifies(opp):
                continue
            n_qualifying += 1
            if opp.event_slug in existing:
                continue
            if len(open_rows) + len(entries) >= MAX_CONCURRENT:
                skipped_cap += 1
                continue
            entries.append(opp)

        n_resolved = 0
        if not dry_run:
            cur = conn.execute(
                """INSERT INTO ticks
                   (tick_at, n_opps_seen, n_qualifying, n_entered,
                    n_skipped_cap, n_resolved, notes)
                   VALUES (?, ?, ?, 0, ?, 0, '')""",
                (datetime.now(timezone.utc).isoformat(), len(opps),
                 n_qualifying, skipped_cap),
            )
            tick_id = cur.lastrowid

            for opp in entries:
                pos_id = enter_position(conn, tick_id, opp)
                cost, sets = size_position(opp)
                print(f"  ENTER #{pos_id} {opp.event_slug[:50]} "
                      f"edge={opp.edge_pct:+.2f}% cost=${cost:.2f} sets={sets:.1f} "
                      f"days={opp.days_to_resolution}")

            with httpx.Client(timeout=20) as client:
                for pos in open_rows:
                    if try_resolve(conn, pos, client):
                        n_resolved += 1
                        r = conn.execute(
                            "SELECT realized_pnl FROM closures WHERE position_id=?",
                            (pos["id"],)).fetchone()
                        pnl = r["realized_pnl"] if r else 0.0
                        print(f"  RESOLVE #{pos['id']} {pos['event_slug'][:50]} "
                              f"pnl=${pnl:+.2f}")

            conn.execute(
                "UPDATE ticks SET n_entered=?, n_resolved=? WHERE id=?",
                (len(entries), n_resolved, tick_id),
            )
        else:
            print(f"  [DRY-RUN] would enter {len(entries)} positions:")
            for opp in entries:
                cost, sets = size_position(opp)
                print(f"    {opp.event_slug[:50]} edge={opp.edge_pct:+.2f}% "
                      f"cost=${cost:.2f} sets={sets:.1f}")

        print(f"  qualifying={n_qualifying} entered={len(entries)} "
              f"resolved={n_resolved} skipped_cap={skipped_cap}")


def cmd_status() -> None:
    init_db()
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        print("=== open positions ===")
        rows = conn.execute(
            "SELECT * FROM positions WHERE status='open' ORDER BY entry_at").fetchall()
        if not rows:
            print("  none")
        total_open_cost = 0.0
        for r in rows:
            total_open_cost += r["entry_cost"]
            print(f"  #{r['id']:>3} {r['event_slug'][:45]:<45} "
                  f"cost=${r['entry_cost']:>7.2f} sets={r['sets_bought']:>7.1f} "
                  f"edge={r['edge_pct_at_entry']:+.2f}% days={r['days_to_res_at_entry']}")
        print(f"  total deployed: ${total_open_cost:.2f} / ${BANKROLL_USD:.0f} "
              f"({len(rows)}/{MAX_CONCURRENT} concurrent)")

        print("\n=== closed positions ===")
        rows = conn.execute(
            """SELECT p.event_slug, p.entry_cost, p.completeness,
                      c.realized_payout, c.realized_pnl, c.hold_days, c.winning_slug
               FROM closures c JOIN positions p ON p.id = c.position_id
               ORDER BY c.closed_at DESC LIMIT 40""").fetchall()
        if not rows:
            print("  none")
        total_pnl = sum(r["realized_pnl"] for r in rows)
        wins = sum(1 for r in rows if r["realized_pnl"] > 0)
        for r in rows:
            print(f"  {r['event_slug'][:45]:<45} cost=${r['entry_cost']:>7.2f} "
                  f"payout=${r['realized_payout']:>7.2f} pnl=${r['realized_pnl']:+8.2f} "
                  f"hold={r['hold_days']:>5.1f}d")
        if rows:
            print(f"  closed n={len(rows)}  wins={wins}  total_pnl=${total_pnl:+.2f}")


def cmd_report(fee_bps: float) -> None:
    """Re-score realized PnL under a different fee assumption.

    Polymarket fee formula: shares × feeRate × p × (1-p) on each leg.
    For a basket of legs at entry, total fee = sets × Σ (feeRate × p_i × (1-p_i)).
    """
    init_db()
    fee_rate = fee_bps / 10_000.0
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT p.id, p.event_slug, p.entry_cost, p.sets_bought, p.legs_json,
                      c.realized_payout, c.realized_pnl AS raw_pnl, c.hold_days
               FROM closures c JOIN positions p ON p.id = c.position_id""").fetchall()
        if not rows:
            print("no closed positions yet")
            return
        total_raw = total_fee = total_net = 0.0
        wins = 0
        total_hold_days = 0.0
        print(f"=== report at fee_bps={fee_bps} ===")
        for r in rows:
            legs = json.loads(r["legs_json"])
            fee_per_set = sum(fee_rate * l["ask"] * (1 - l["ask"]) for l in legs)
            total_fee_pos = r["sets_bought"] * fee_per_set
            net = r["raw_pnl"] - total_fee_pos
            total_raw += r["raw_pnl"]
            total_fee += total_fee_pos
            total_net += net
            total_hold_days += r["hold_days"]
            if net > 0:
                wins += 1
            print(f"  {r['event_slug'][:45]:<45} raw=${r['raw_pnl']:+7.2f} "
                  f"fee=${total_fee_pos:>6.2f} net=${net:+7.2f}")
        n = len(rows)
        avg_hold = total_hold_days / n if n else 0.0
        annualized = (total_net / total_hold_days * 365.0) if total_hold_days else 0.0
        print(f"\n  n={n}  wins={wins} ({wins/n*100:.0f}%)")
        print(f"  raw_pnl=${total_raw:+.2f}  fees=${total_fee:.2f}  net_pnl=${total_net:+.2f}")
        print(f"  avg_hold={avg_hold:.1f}d  position-days={total_hold_days:.1f}")
        print(f"  annualized (position-day weighted): ${annualized:+.2f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    tick = sub.add_parser("tick", help="run one scan + entry + resolution cycle")
    tick.add_argument("--dry-run", action="store_true")

    loop = sub.add_parser("loop", help="run tick on interval forever")
    loop.add_argument("--interval-min", type=float, default=60.0)

    sub.add_parser("status", help="show open + recent closed positions")

    rep = sub.add_parser("report", help="re-score realized PnL at a fee assumption")
    rep.add_argument("--fee-bps", type=float, default=0.0)

    args = ap.parse_args()

    if args.cmd == "tick":
        cmd_tick(dry_run=args.dry_run)
    elif args.cmd == "loop":
        while True:
            try:
                cmd_tick(dry_run=False)
            except Exception as e:
                print(f"[{datetime.now(timezone.utc).isoformat()}] tick ERROR: "
                      f"{type(e).__name__}: {e}")
            time.sleep(args.interval_min * 60)
    elif args.cmd == "status":
        cmd_status()
    elif args.cmd == "report":
        cmd_report(fee_bps=args.fee_bps)
    return 0


if __name__ == "__main__":
    sys.exit(main())
