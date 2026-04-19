"""Forward paper-trade tracker for short-duration neg-risk arbs.

Picks 6 events whose arb survives short-duration + closed-set criteria,
records "what we would have bought at entry" snapshot, then re-checks each
hour. At resolution, computes what the paper basket actually paid.

Picks (user-curated; replace open-ended ones with NBA/NHL conference markets):
  KEEP:    uefa-europa-league-winner       (~35d, n=4)
           la-liga-winner-114              (~41d, n=3)
           colombia-presidential-election  (~64d, n=18)
  DROPPED: next-james-bond-actor (open-ended)
           ny-democratic-governor-primary (ballot not locked)
  ADD:     nba-eastern-conference-champion-442 (~58d, n=8)  ← bracket starts today
           nba-western-conference-champion-933 (~58d, n=8)
           fed-decision-in-april (~10d, n=4)              ← shortest data point

Tables:
  paper_picks      — one row per (pick, snapshot_at) ; full leg snapshot
  paper_resolutions — one row per pick when resolved; realized PnL
"""
from __future__ import annotations

import argparse
import ast
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

DATA_DIR = Path(__file__).parent / "data"
DB = DATA_DIR / "forward_trader.db"
GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"

PICKS = (
    "uefa-europa-league-winner",
    "la-liga-winner-114",
    "colombia-presidential-election",
    "nba-eastern-conference-champion-442",
    "nba-western-conference-champion-933",
    "fed-decision-in-april",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS picks (
    id              INTEGER PRIMARY KEY,
    event_slug      TEXT NOT NULL,
    snapshot_at     TEXT NOT NULL,
    sum_asks        REAL,
    sum_bids        REAL,
    edge_pct        REAL,
    n_active        INTEGER,
    days_to_resolution REAL,
    legs_json       TEXT,
    UNIQUE (event_slug, snapshot_at)
);

CREATE TABLE IF NOT EXISTS resolutions (
    event_slug      TEXT PRIMARY KEY,
    resolved_at     TEXT NOT NULL,
    winning_slug    TEXT,
    realized_payout REAL,
    entry_cost      REAL,
    realized_pnl    REAL,
    notes           TEXT
);

CREATE INDEX IF NOT EXISTS idx_picks_event ON picks (event_slug);
"""


def init_db():
    DATA_DIR.mkdir(exist_ok=True)
    with sqlite3.connect(DB) as c:
        c.executescript(SCHEMA)


def parse_token_ids(raw):
    if not raw: return []
    if isinstance(raw, str):
        try: return json.loads(raw)
        except: return []
    return raw if isinstance(raw, list) else []


def fetch_event(slug: str, client: httpx.Client) -> dict | None:
    """Pull a specific event by slug param (gamma supports it directly)."""
    r = client.get(f"{GAMMA}/events", params={"slug": slug})
    if r.status_code == 200:
        data = r.json()
        if data and isinstance(data, list):
            return data[0]
    # Fallback: paginate active then closed
    for closed in ("false", "true"):
        offset = 0
        while True:
            r = client.get(f"{GAMMA}/events",
                           params={"limit": 200, "offset": offset, "closed": closed})
            if r.status_code != 200:
                break
            batch = r.json()
            if not batch:
                break
            for e in batch:
                if e.get("slug") == slug:
                    return e
            if len(batch) < 200:
                break
            offset += 200
            if offset > 5000:
                break
    return None


def snapshot_event(event: dict, client: httpx.Client) -> dict:
    """Build a leg-by-leg snapshot with depth."""
    legs = []
    sum_a, sum_b = 0.0, 0.0
    for m in event.get("markets", []):
        if not m.get("active") or m.get("closed"):
            continue
        ba = m.get("bestAsk")
        bb = m.get("bestBid")
        if ba is None:
            continue
        try: ba, bb = float(ba), float(bb) if bb else 0.0
        except: continue
        tids = parse_token_ids(m.get("clobTokenIds"))
        yes_token = tids[0] if tids else ""
        ask_depth = bid_depth = 0.0
        if yes_token:
            try:
                br = client.get(f"{CLOB}/book", params={"token_id": yes_token}, timeout=10)
                if br.status_code == 200:
                    book = br.json()
                    asks = sorted([(float(a["price"]), float(a["size"])) for a in book.get("asks", [])], key=lambda x: x[0])
                    bids = sorted([(float(b["price"]), float(b["size"])) for b in book.get("bids", [])], key=lambda x: -x[0])
                    if asks:
                        ask_depth = sum(s for p, s in asks if abs(p - asks[0][0]) <= 0.005)
                    if bids:
                        bid_depth = sum(s for p, s in bids if abs(p - bids[0][0]) <= 0.005)
            except Exception:
                pass
        legs.append({"slug": m.get("slug"), "ask": ba, "bid": bb,
                     "ask_depth": ask_depth, "bid_depth": bid_depth})
        sum_a += ba; sum_b += bb
    days = None
    ed = event.get("endDate")
    if ed:
        try:
            edt = datetime.fromisoformat(ed.replace("Z", "+00:00"))
            days = (edt - datetime.now(timezone.utc)).total_seconds() / 86400
        except Exception:
            pass
    return {"sum_asks": round(sum_a, 4), "sum_bids": round(sum_b, 4),
            "edge_pct": round((1-sum_a)*100, 3), "n_active": len(legs),
            "days_to_resolution": round(days, 1) if days is not None else None,
            "legs": legs}


def write_pick(event_slug: str, snap: dict):
    ts = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(DB) as c:
        try:
            c.execute("""INSERT INTO picks
                (event_slug, snapshot_at, sum_asks, sum_bids, edge_pct,
                 n_active, days_to_resolution, legs_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (event_slug, ts, snap["sum_asks"], snap["sum_bids"], snap["edge_pct"],
                 snap["n_active"], snap["days_to_resolution"], json.dumps(snap["legs"])))
        except sqlite3.IntegrityError:
            pass  # duplicate (event, snapshot_at) — ignore


def parse_outcome_prices(raw):
    if raw is None: return None
    if isinstance(raw, list) and len(raw) == 2:
        try: return (float(raw[0]), float(raw[1]))
        except: return None
    if isinstance(raw, str):
        try:
            v = ast.literal_eval(raw)
            if isinstance(v, list) and len(v) == 2:
                return (float(v[0]), float(v[1]))
        except: pass
    return None


def maybe_resolve(event_slug: str, event: dict):
    """If event is closed and clean, write resolution row + compute realized P&L."""
    if not event.get("closed"):
        return False
    # Find winning leg
    winner = None
    for m in event.get("markets", []):
        if not m.get("active"):
            continue
        op = parse_outcome_prices(m.get("outcomePrices"))
        if op and op[0] == 1.0:
            winner = m.get("slug")
            break
    # Pull our entry snapshot (the FIRST one we recorded for this event)
    with sqlite3.connect(DB) as c:
        row = c.execute("""SELECT sum_asks, legs_json FROM picks
                           WHERE event_slug = ? ORDER BY snapshot_at ASC LIMIT 1""",
                        (event_slug,)).fetchone()
    if not row:
        return False
    entry_cost = row[0] or 0.0
    realized_payout = 1.0 if winner else 0.0
    realized_pnl = realized_payout - entry_cost
    notes = "" if winner else "TAIL: no listed candidate won"
    with sqlite3.connect(DB) as c:
        c.execute("""INSERT OR REPLACE INTO resolutions
            (event_slug, resolved_at, winning_slug, realized_payout, entry_cost,
             realized_pnl, notes) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (event_slug, datetime.now(timezone.utc).isoformat(),
             winner, realized_payout, entry_cost, realized_pnl, notes))
    return True


def cmd_snapshot():
    init_db()
    with httpx.Client(timeout=20) as client:
        for slug in PICKS:
            print(f"[{slug}]")
            e = fetch_event(slug, client)
            if not e:
                print(f"  not found in gamma /events")
                continue
            if maybe_resolve(slug, e):
                print(f"  RESOLVED — recorded")
                continue
            snap = snapshot_event(e, client)
            write_pick(slug, snap)
            print(f"  sum_asks={snap['sum_asks']} edge={snap['edge_pct']:+.2f}% "
                  f"n={snap['n_active']} days={snap['days_to_resolution']} "
                  f"min_depth={min((l['ask_depth'] for l in snap['legs']), default=0):.0f} sets")


def cmd_status():
    init_db()
    with sqlite3.connect(DB) as c:
        c.row_factory = sqlite3.Row
        print("=== picks (latest snapshot per event) ===")
        rows = c.execute("""SELECT event_slug, MAX(snapshot_at) AS latest,
                                   COUNT(*) AS n_snapshots,
                                   AVG(edge_pct) AS avg_edge,
                                   MIN(edge_pct) AS min_edge,
                                   MAX(edge_pct) AS max_edge
                            FROM picks GROUP BY event_slug""").fetchall()
        for r in rows:
            print(f"  {r['event_slug']:<45} snapshots={r['n_snapshots']:>3} "
                  f"edge_min={r['min_edge']:+.2f}% avg={r['avg_edge']:+.2f}% max={r['max_edge']:+.2f}%")
        print()
        print("=== resolutions ===")
        rows = c.execute("SELECT * FROM resolutions ORDER BY resolved_at DESC").fetchall()
        if not rows:
            print("  none yet")
        for r in rows:
            print(f"  {r['event_slug']}  payout=${r['realized_payout']:.2f}  cost=${r['entry_cost']:.4f}  pnl=${r['realized_pnl']:+.4f}  {r['notes']}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("snapshot", help="record current state of all picks")
    sub.add_parser("status", help="show snapshot history + resolutions")
    sub.add_parser("loop", help="run snapshot every hour forever").add_argument(
        "--interval-min", type=float, default=60)
    args = ap.parse_args()
    if args.cmd == "snapshot":
        cmd_snapshot()
    elif args.cmd == "status":
        cmd_status()
    elif args.cmd == "loop":
        while True:
            try:
                cmd_snapshot()
            except Exception as e:
                print(f"snapshot error: {e}")
            time.sleep(args.interval_min * 60)


if __name__ == "__main__":
    sys.exit(main() or 0)
