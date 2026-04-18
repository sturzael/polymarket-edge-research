"""Phase 0a step 2: for each historical barrier condition_id, fetch:
  - CLOB resolution (winner)
  - market metadata (question, end_date, token_ids)
  - trade history via data-api (to reconstruct ask levels over time)

Stored to experiments/e10_regime_stratified_backtest/data.db for reproducibility.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from pathlib import Path

import aiohttp

OUT_DB = Path(__file__).parent / "data.db"
WALLET_HISTORY = Path(__file__).parent.parent / "e9_wallet_competitor_intel" / "data" / "top_wallet_history.jsonl"
BARRIER_TRADES = Path(__file__).parent.parent / "e9_wallet_competitor_intel" / "data" / "barrier_trades.jsonl"

SCHEMA = """
CREATE TABLE IF NOT EXISTS markets (
  condition_id TEXT PRIMARY KEY,
  slug TEXT,
  question TEXT,
  underlying TEXT,
  kind TEXT,
  strike REAL,
  end_date_iso TEXT,
  winner TEXT,
  yes_token_id TEXT,
  no_token_id TEXT,
  fetched_at INTEGER
);

CREATE TABLE IF NOT EXISTS trades (
  tx_hash TEXT PRIMARY KEY,
  condition_id TEXT NOT NULL,
  asset_id TEXT NOT NULL,
  timestamp INTEGER NOT NULL,
  side TEXT,
  outcome TEXT,
  price REAL,
  size REAL
);
CREATE INDEX IF NOT EXISTS idx_trades_cid_ts ON trades(condition_id, timestamp);
"""


def parse_kind_strike(slug: str) -> tuple[str, float | None]:
    import re
    s = (slug or "").lower()
    for kind_marker, kind in (("-reach-", "reach"), ("-dip-to-", "dip"), ("-hit-", "hit")):
        if kind_marker in s:
            m = re.search(rf"{kind_marker}(\d+)(?:k)?", s)
            if m:
                val = float(m.group(1))
                if "k-" in s or s.endswith("k"):
                    val *= 1000
                return kind, val
            # pt notation: 1pt6 -> 1.6
            m = re.search(rf"{kind_marker}(\d+pt\d+)", s)
            if m:
                val = float(m.group(1).replace("pt", "."))
                return kind, val
    return "?", None


def parse_underlying(slug: str) -> str | None:
    s = (slug or "").lower()
    for kw, sym in (("bitcoin", "BTC"), ("btc", "BTC"), ("ethereum", "ETH"), ("eth", "ETH"),
                     ("solana", "SOL"), ("sol", "SOL"), ("xrp", "XRP"),
                     ("doge", "DOGE"), ("bnb", "BNB")):
        if kw in s:
            return sym
    return None


def gather_condition_ids() -> dict[str, dict]:
    """Return cid -> {slug, first_ts} from both history files."""
    out: dict[str, dict] = {}
    for path in (WALLET_HISTORY, BARRIER_TRADES):
        if not path.exists():
            continue
        with path.open() as f:
            for line in f:
                try:
                    t = json.loads(line)
                except json.JSONDecodeError:
                    continue
                cid = t.get("conditionId")
                if not cid:
                    continue
                slug = (t.get("slug") or t.get("eventSlug") or "").lower()
                if not any(k in slug for k in ("-reach-", "-dip-to-", "-hit-")):
                    continue
                if not any(k in slug for k in ("bitcoin", "ethereum", "solana", "btc", "eth", "sol", "xrp", "doge", "bnb")):
                    continue
                ts = int(t.get("timestamp", 0))
                if cid not in out or ts < out[cid]["first_ts"]:
                    out[cid] = {"slug": slug, "first_ts": ts}
    return out


async def fetch_market(session: aiohttp.ClientSession, cid: str) -> dict | None:
    try:
        async with session.get(f"https://clob.polymarket.com/markets/{cid}", timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status != 200:
                return None
            return await r.json()
    except Exception:
        return None


async def main():
    conn = sqlite3.connect(OUT_DB)
    conn.executescript(SCHEMA)
    conn.commit()

    cids_info = gather_condition_ids()
    already_done = {row[0] for row in conn.execute("SELECT condition_id FROM markets WHERE winner IS NOT NULL")}
    to_do = [cid for cid in cids_info if cid not in already_done]
    print(f"gathered {len(cids_info)} cids; already have {len(already_done)}; fetching {len(to_do)}")

    async with aiohttp.ClientSession(headers={"User-Agent": "e10-backtest/0.1"}) as s:
        for i, cid in enumerate(to_do):
            if i % 50 == 0:
                print(f"  progress: {i}/{len(to_do)}")
            mkt = await fetch_market(s, cid)
            if not mkt:
                continue
            tokens = mkt.get("tokens", [])
            yes_tok = next((t for t in tokens if (t.get("outcome") or "").lower() in ("yes", "up")), None)
            no_tok = next((t for t in tokens if (t.get("outcome") or "").lower() in ("no", "down")), None)
            winner = next((t.get("outcome") for t in tokens if t.get("winner")), None)
            slug = mkt.get("market_slug") or cids_info[cid]["slug"]
            kind, strike = parse_kind_strike(slug)
            underlying = parse_underlying(slug)
            conn.execute(
                "INSERT OR REPLACE INTO markets (condition_id, slug, question, underlying, kind, strike, end_date_iso, winner, yes_token_id, no_token_id, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    cid, slug, mkt.get("question"), underlying, kind, strike,
                    mkt.get("end_date_iso"),
                    winner.upper() if winner else None,
                    str(yes_tok["token_id"]) if yes_tok else None,
                    str(no_tok["token_id"]) if no_tok else None,
                    int(time.time()),
                )
            )
            conn.commit()
    # Summary
    rows = conn.execute("SELECT winner, COUNT(*) FROM markets GROUP BY winner").fetchall()
    print("\nwinner distribution:")
    for w, n in rows:
        print(f"  {w}: {n}")
    conn.close()


if __name__ == "__main__":
    asyncio.run(main())
