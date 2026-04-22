"""Forward validation of the T-7d sports favorite-longshot bias finding.

Recipe from FINDINGS.md §2f: every hour, snapshot active Polymarket sports
markets that are 6.5-7.5 days from resolution. Record price, bid/ask, depth,
category. When those markets later resolve, join snapshot → outcome, bucket
by price, compare forward yes_rate to the historical table.

If forward yes_rate within each bucket matches the historical result within
~5pp, the bias is real and tradeable.

Inputs (at runtime):
    gamma-api.polymarket.com — source of truth for active-market state

Outputs:
    data/forward_validator.db  — SQLite
        tables:
            scans          — one row per hourly scan
            snapshots      — one row per (market, scan) with price + depth
            resolutions    — one row per market once it resolves
    data/forward_validator.log

Usage:
    # Single scan (for launchd)
    uv run python -m experiments.e16_calibration_study.forward_validator scan

    # Resolution sweep (daily)
    uv run python -m experiments.e16_calibration_study.forward_validator resolve

    # Current snapshot summary
    uv run python -m experiments.e16_calibration_study.forward_validator status

    # Analysis (once we have resolutions)
    uv run python -m experiments.e16_calibration_study.forward_validator analyze
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

DATA_DIR = Path(__file__).parent / "data"
DB = DATA_DIR / "forward_validator.db"
GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"

# Same sports categories as e16 sports_deep run.
SPORT_CATEGORIES = {
    "sports_nba", "sports_nfl", "sports_mlb", "sports_nhl", "sports_soccer",
    "sports_ufc_boxing", "sports_tennis", "sports_f1",
}

# Category classifier copied from 01_markets_audit.py — keep in sync if updated.
CATEGORY_RULES = [
    ("sports_nfl",    re.compile(r"\b(nfl|super[-_ ]?bowl|afc|nfc|packers|49ers|cowboys|eagles|ravens|chiefs)\b", re.I)),
    ("sports_nba",    re.compile(r"\b(nba|warriors|celtics|lakers|bucks|nets|knicks|suns|heat|thunder|mavericks|raptors|sixers|pacers|bulls)\b|\bnba-\w+|-nba-", re.I)),
    ("sports_mlb",    re.compile(r"\b(mlb|world[-_ ]?series|yankees|dodgers|red[-_ ]?sox|astros|mets|phillies|braves|rays|cubs)\b", re.I)),
    ("sports_nhl",    re.compile(r"\b(nhl|stanley[-_ ]?cup|bruins|leafs|avalanche|oilers|canadiens)\b", re.I)),
    ("sports_soccer", re.compile(r"\b(epl|premier[-_ ]?league|la[-_ ]?liga|uefa|champions[-_ ]?league|europa|bundesliga|serie[-_ ]?a|mls|fifa|world[-_ ]?cup|man[-_ ]?(u|city)|liverpool|arsenal|real[-_ ]?madrid|barcelona|psg|bayern|juventus|chelsea|spurs)\b", re.I)),
    ("sports_ufc_boxing", re.compile(r"\b(ufc|mma|boxing|fighter|paul[-_ ]?vs|fury[-_ ]?vs)\b", re.I)),
    ("sports_tennis", re.compile(r"\b(tennis|atp|wta|djokovic|alcaraz|sinner|us[-_ ]?open|wimbledon|french[-_ ]?open|australian[-_ ]?open)\b", re.I)),
    ("sports_f1",     re.compile(r"\b(formula[-_ ]?1|f1[-_ ]?|verstappen|hamilton|leclerc|norris|piastri|grand[-_ ]?prix)\b", re.I)),
]

# Target window: days to end_date
T_TARGET_DAYS = 7.0
WINDOW_HALF_DAYS = 0.5  # accept 6.5–7.5 days

SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    id               INTEGER PRIMARY KEY,
    scan_at          TEXT NOT NULL,
    n_active_total   INTEGER NOT NULL,
    n_in_window      INTEGER NOT NULL,
    notes            TEXT
);

CREATE TABLE IF NOT EXISTS snapshots (
    id               INTEGER PRIMARY KEY,
    scan_id          INTEGER NOT NULL REFERENCES scans(id),
    condition_id     TEXT NOT NULL,
    slug             TEXT NOT NULL,
    event_slug       TEXT,
    event_title      TEXT,
    category         TEXT NOT NULL,
    snapshot_at      TEXT NOT NULL,
    end_date         TEXT,
    days_to_end      REAL,
    last_price       REAL,
    best_bid         REAL,
    best_ask         REAL,
    mid_price        REAL,
    spread           REAL,
    volume_lifetime  REAL,
    UNIQUE (scan_id, condition_id)
);

CREATE INDEX IF NOT EXISTS idx_snap_cid ON snapshots (condition_id);
CREATE INDEX IF NOT EXISTS idx_snap_snap_at ON snapshots (snapshot_at);

CREATE TABLE IF NOT EXISTS resolutions (
    condition_id     TEXT PRIMARY KEY,
    resolved_at      TEXT NOT NULL,
    outcome          TEXT NOT NULL,     -- 'YES' | 'NO' | 'UNRESOLVED'
    end_date         TEXT,
    notes            TEXT
);
"""


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"[{ts}] {msg}", flush=True)


def init_db() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with sqlite3.connect(DB) as c:
        c.executescript(SCHEMA)


def categorize(slug: str, question: str, event_slug: str) -> str:
    text = f"{slug} {question} {event_slug}".lower()
    for label, pattern in CATEGORY_RULES:
        if pattern.search(text):
            return label
    return "other"


def parse_ts(raw) -> datetime | None:
    """Handles all three Polymarket timestamp formats:
        '2026-04-28T19:00:00Z'       (ISO with Z)
        '2026-04-28T19:00:00+00:00'  (ISO with offset)
        '2026-04-20 22:45:00+00'     (gameStartTime: space-separated, +00)
    """
    if not raw:
        return None
    try:
        s = str(raw).replace(" ", "T")
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        elif s.endswith("+00"):
            s = s + ":00"
        return datetime.fromisoformat(s)
    except Exception:
        return None


def fetch_active_markets(client: httpx.Client, max_pages: int = 80) -> list[dict]:
    """Paginate gamma /markets?active=true&closed=false. Polymarket has
    25k-40k active markets; default is ≤80 pages (40k)."""
    out = []
    offset = 0
    for _ in range(max_pages):
        r = client.get(f"{GAMMA}/markets",
                       params={"active": "true", "closed": "false",
                               "limit": 500, "offset": offset},
                       timeout=30)
        if r.status_code != 200:
            break
        batch = r.json()
        if not batch:
            break
        out.extend(batch)
        if len(batch) < 500:
            break
        offset += 500
    return out


def cmd_scan() -> int:
    init_db()
    now = datetime.now(timezone.utc)
    _log("fetching active markets...")
    with httpx.Client() as client:
        all_active = fetch_active_markets(client)
    _log(f"  {len(all_active):,} active markets total")

    # Filter: sports category + T-7d to EVENT (gameStartTime), not endDate.
    # MLB markets have endDate = gameStart + 7d (settlement delay); using
    # endDate would false-positive on every post-game MLB market.
    in_window = []
    for m in all_active:
        event_ts = parse_ts(m.get("gameStartTime") or m.get("endDate"))
        if event_ts is None:
            continue
        days_to_end = (event_ts - now).total_seconds() / 86400.0
        if not (T_TARGET_DAYS - WINDOW_HALF_DAYS <= days_to_end
                <= T_TARGET_DAYS + WINDOW_HALF_DAYS):
            continue
        cat = categorize(m.get("slug", ""),
                         m.get("question", ""),
                         m.get("eventSlug", "") or "")
        if cat not in SPORT_CATEGORIES:
            continue
        m["_category"] = cat
        m["_days_to_end"] = round(days_to_end, 3)
        in_window.append(m)

    _log(f"  {len(in_window)} sports markets in T-7d ±12h window")

    # Write snapshots
    with sqlite3.connect(DB) as conn:
        cur = conn.execute(
            "INSERT INTO scans (scan_at, n_active_total, n_in_window, notes) "
            "VALUES (?, ?, ?, ?)",
            (now.isoformat(), len(all_active), len(in_window), ""),
        )
        scan_id = cur.lastrowid

        for m in in_window:
            cid = m.get("conditionId") or m.get("condition_id") or ""
            if not cid:
                continue
            try:
                bid = float(m.get("bestBid")) if m.get("bestBid") else None
                ask = float(m.get("bestAsk")) if m.get("bestAsk") else None
                last = float(m.get("lastTradePrice")) if m.get("lastTradePrice") else None
                vol = float(m.get("volume") or 0)
            except Exception:
                bid = ask = last = None
                vol = 0.0
            mid = None
            spread = None
            if bid is not None and ask is not None and 0 < bid < ask < 1:
                mid = (bid + ask) / 2
                spread = ask - bid
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO snapshots
                        (scan_id, condition_id, slug, event_slug, event_title,
                         category, snapshot_at, end_date, days_to_end,
                         last_price, best_bid, best_ask, mid_price, spread,
                         volume_lifetime)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (scan_id, cid, m.get("slug"),
                     m.get("eventSlug"), m.get("eventTitle"),
                     m["_category"], now.isoformat(),
                     m.get("endDate"), m["_days_to_end"],
                     last, bid, ask, mid, spread, vol),
                )
            except Exception as e:
                _log(f"  skip {cid[:16]}: {e}")
    _log(f"scan #{scan_id} wrote {len(in_window)} snapshots")
    return 0


def cmd_resolve() -> int:
    """Sweep: for every condition_id we've snapshotted, query gamma to see
    if it's resolved yet. If so, record outcome."""
    init_db()
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        # Distinct condition_ids we've snapshotted but not yet resolved
        pending = [r["condition_id"] for r in conn.execute("""
            SELECT DISTINCT s.condition_id FROM snapshots s
            LEFT JOIN resolutions r ON r.condition_id = s.condition_id
            WHERE r.condition_id IS NULL
        """).fetchall()]

    _log(f"checking resolution for {len(pending)} snapshotted markets...")
    n_resolved = 0
    now_iso = datetime.now(timezone.utc).isoformat()
    with httpx.Client(timeout=20) as client:
        for cid in pending:
            try:
                r = client.get(f"{CLOB}/markets/{cid}")
            except Exception:
                continue
            if r.status_code != 200:
                continue
            data = r.json() or {}
            # CLOB returns market data; we want closed + outcomePrices
            closed = data.get("closed") or data.get("state") == "closed"
            op = data.get("outcome_prices") or data.get("outcomePrices")
            if not closed:
                continue
            outcome = "UNRESOLVED"
            if op:
                try:
                    if isinstance(op, str):
                        op = ast.literal_eval(op)
                    if isinstance(op, (list, tuple)) and len(op) == 2:
                        p0, p1 = float(op[0]), float(op[1])
                        if p0 == 1.0 and p1 == 0.0:
                            outcome = "YES"
                        elif p0 == 0.0 and p1 == 1.0:
                            outcome = "NO"
                except Exception:
                    pass
            if outcome == "UNRESOLVED":
                continue
            with sqlite3.connect(DB) as conn:
                conn.execute(
                    """INSERT OR IGNORE INTO resolutions
                        (condition_id, resolved_at, outcome, end_date, notes)
                       VALUES (?, ?, ?, ?, ?)""",
                    (cid, now_iso, outcome, data.get("end_date") or "", ""),
                )
            n_resolved += 1
    _log(f"recorded {n_resolved} new resolutions")
    return 0


def cmd_status() -> int:
    init_db()
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        r = conn.execute("SELECT COUNT(*) AS n, MAX(scan_at) AS last FROM scans").fetchone()
        print(f"scans: n={r['n']}  last={r['last']}")
        r = conn.execute("SELECT COUNT(*) AS n, MAX(snapshot_at) AS last FROM snapshots").fetchone()
        print(f"snapshots: n={r['n']}  last={r['last']}")
        r = conn.execute(
            "SELECT COUNT(DISTINCT condition_id) AS n FROM snapshots"
        ).fetchone()
        print(f"unique markets seen: {r['n']}")
        r = conn.execute("SELECT COUNT(*) AS n FROM resolutions").fetchone()
        print(f"resolutions: n={r['n']}")
        print()
        # Per-category snapshot counts
        print("per-category cumulative snapshot count:")
        for row in conn.execute(
            "SELECT category, COUNT(*) AS n, COUNT(DISTINCT condition_id) AS m "
            "FROM snapshots GROUP BY category ORDER BY n DESC"
        ):
            print(f"  {row['category']:<22}  snapshots={row['n']:>5,}  unique_markets={row['m']:>4,}")
    return 0


def cmd_analyze() -> int:
    """Bucket pooled resolved markets by snapshot mid_price, compare to
    e16 historical table."""
    init_db()
    try:
        import pandas as pd  # noqa
    except ImportError:
        print("pandas required for analyze; skipping")
        return 1
    import pandas as pd

    with sqlite3.connect(DB) as conn:
        df = pd.read_sql("""
            SELECT s.condition_id, s.category, s.mid_price, s.last_price,
                   s.best_bid, s.best_ask, s.spread, s.volume_lifetime,
                   s.snapshot_at, r.outcome
            FROM snapshots s
            INNER JOIN resolutions r ON r.condition_id = s.condition_id
            WHERE r.outcome IN ('YES', 'NO')
              AND s.mid_price IS NOT NULL
        """, conn)

    print(f"resolved-market snapshots: {len(df):,} "
          f"({df['condition_id'].nunique()} unique markets)")
    if len(df) == 0:
        print("no resolved snapshots yet; wait for resolutions")
        return 0

    # One snapshot per market (use the one closest to T-7d)
    # Since we only snapshot in the 6.5-7.5 window, just take the most recent
    latest_per = df.sort_values("snapshot_at").groupby("condition_id").last().reset_index()

    def bucket(p):
        b = min(int(p * 20), 19)
        lo = b * 0.05
        return f"{lo:.2f}-{lo+0.05:.2f}", lo + 0.025

    latest_per[["bucket", "mid"]] = latest_per["mid_price"].apply(
        lambda p: pd.Series(bucket(p))
    )
    latest_per["yes"] = (latest_per["outcome"] == "YES").astype(int)

    # e16 historical for comparison
    historical = {
        "0.45-0.50": 0.481, "0.50-0.55": 0.640, "0.55-0.60": 0.833,
        "0.60-0.65": 0.799, "0.65-0.70": 0.922, "0.70-0.75": 0.923,
        "0.75-0.80": 0.971, "0.80-0.85": 0.969,
    }

    print(f"\n{'bucket':<12} {'n':>4} {'mid':>5} {'fwd_yes':>8} "
          f"{'hist_yes':>8} {'delta':>+7}")
    for b, g in latest_per.groupby("bucket"):
        mid = g["mid"].iloc[0]
        rate = g["yes"].mean()
        n = len(g)
        hist = historical.get(b)
        delta = (rate - hist) if hist is not None else None
        hist_str = f"{hist:.3f}" if hist is not None else "—"
        delta_str = f"{delta:+.3f}" if delta is not None else "—"
        print(f"  {b:<12} {n:>4} {mid:>5.3f} {rate:>8.3f} "
              f"{hist_str:>8} {delta_str:>+7}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["scan", "resolve", "status", "analyze"])
    args = ap.parse_args()
    if args.cmd == "scan":
        return cmd_scan()
    elif args.cmd == "resolve":
        return cmd_resolve()
    elif args.cmd == "status":
        return cmd_status()
    elif args.cmd == "analyze":
        return cmd_analyze()


if __name__ == "__main__":
    sys.exit(main())
