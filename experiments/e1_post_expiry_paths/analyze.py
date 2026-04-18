"""Pull trade history for resolved markets in probe.db and analyze
price path from T-60s through T+400s (nominal expiry at T=0).

Three questions:
  1. Does price snap to 0/1 immediately at T, or drift over 400s?
  2. Is there trading activity between T and resolution? How much?
  3. Is there a discernible window where price is "clearly determined
     but mispriced"?
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import statistics
from pathlib import Path

import aiohttp

OUT_DIR = Path(__file__).parent
DATA_API = "https://data-api.polymarket.com"


async def fetch_trades_for_market(session: aiohttp.ClientSession, cid: str) -> list[dict]:
    """Pull the full per-market trade stream. data-api returns up to 1000 most-recent
    trades by default; we paginate using offset until we hit empty."""
    out: list[dict] = []
    offset = 0
    while True:
        async with session.get(
            f"{DATA_API}/trades",
            params={"market": cid, "limit": "1000", "offset": str(offset)},
        ) as r:
            if r.status != 200:
                break
            chunk = await r.json()
            if not isinstance(chunk, list) or not chunk:
                break
            out.extend(chunk)
            if len(chunk) < 1000:
                break
            offset += 1000
            if offset > 5000:  # safety
                break
    return out


def classify_path(prices_post: list[tuple[float, float]], outcome_is_up: bool) -> str:
    """Given list of (t_rel, up_price) after T=0, classify the shape.

    Returns one of: 'snap' (price reaches target within 30s),
                    'drift' (price reaches target between 30-300s),
                    'slow' (price still not at target by 300s),
                    'no-data' (no trades in post window).
    """
    if not prices_post:
        return "no-data"
    target = 1.0 if outcome_is_up else 0.0
    tol = 0.02
    reached = next((t for t, p in prices_post if abs(p - target) <= tol), None)
    if reached is None:
        return "slow"
    if reached <= 30:
        return "snap"
    if reached <= 300:
        return "drift"
    return "slow"


async def main(n_markets: int = 20) -> None:
    out_dir = OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect("probe/probe.db")
    rows = c.execute(
        """
        SELECT m.market_id, m.slug, m.underlying, m.end_ts, m.clob_token_ids, r.outcome
        FROM resolutions r
        JOIN markets m ON m.market_id = r.market_id
        WHERE r.outcome IN ('UP','DOWN') AND r.resolved_cleanly = 1
          AND m.clob_token_ids IS NOT NULL
        ORDER BY m.end_ts ASC
        LIMIT ?
        """,
        (n_markets,),
    ).fetchall()

    print(f"analyzing {len(rows)} resolved markets")

    per_market: list[dict] = []
    shape_counts: dict[str, int] = {"snap": 0, "drift": 0, "slow": 0, "no-data": 0}
    post_trades_counts: list[int] = []

    async with aiohttp.ClientSession() as session:
        for cid, slug, underlying, end_ts_ms, tokens_json, outcome in rows:
            tokens = json.loads(tokens_json)
            # Token ordering: clobTokenIds is [yes_id, no_id] for standard markets.
            # For up/down: outcome names are "Up" / "Down" so we fetch the actual
            # market metadata to be sure.
            trades = await fetch_trades_for_market(session, cid)
            if not trades:
                continue
            end_s = end_ts_ms / 1000

            # Identify up-token and down-token via CLOB
            async with session.get(f"https://clob.polymarket.com/markets/{cid}") as r:
                if r.status != 200:
                    continue
                mkt = await r.json()
            up_tok = None
            for t in mkt.get("tokens", []):
                if (t.get("outcome") or "").lower() in ("up", "yes"):
                    up_tok = str(t.get("token_id"))
            if up_tok is None:
                continue

            # Convert trades into (t_rel_seconds, up_price) series
            series: list[tuple[float, float]] = []
            for tr in trades:
                ts = float(tr.get("timestamp", 0))
                price = float(tr.get("price", 0))
                asset = str(tr.get("asset", ""))
                # If trade is on up-token, price is directly P(up).
                # If on down-token, P(up) = 1 - price.
                if asset == up_tok:
                    p_up = price
                else:
                    p_up = 1.0 - price
                series.append((ts - end_s, p_up))
            series.sort(key=lambda x: x[0])

            pre = [(t, p) for t, p in series if -60 <= t < 0]
            post = [(t, p) for t, p in series if 0 <= t <= 400]
            first_30s = [p for t, p in post if t <= 30]
            at_60s = [p for t, p in post if 50 <= t <= 70]

            outcome_is_up = outcome == "UP"
            shape = classify_path(post, outcome_is_up)
            shape_counts[shape] = shape_counts.get(shape, 0) + 1
            post_trades_counts.append(len(post))

            price_at_T0 = pre[-1][1] if pre else None
            target = 1.0 if outcome_is_up else 0.0

            per_market.append({
                "slug": slug,
                "underlying": underlying,
                "outcome": outcome,
                "trades_total": len(trades),
                "pre_trades_60s": len(pre),
                "post_trades_0_400s": len(post),
                "first_price_post_T": post[0][1] if post else None,
                "price_at_T0": price_at_T0,
                "mean_first_30s": statistics.mean(first_30s) if first_30s else None,
                "mean_around_60s": statistics.mean(at_60s) if at_60s else None,
                "shape": shape,
                "target": target,
            })

    # Write per-market table
    csv_path = out_dir / "per_market.csv"
    with csv_path.open("w") as f:
        f.write("slug,underlying,outcome,trades_total,pre_60s,post_0_400s,price_T0,mean_first_30s,mean_at_60s,shape\n")
        for m in per_market:
            f.write(
                f"{m['slug']},{m['underlying']},{m['outcome']},"
                f"{m['trades_total']},{m['pre_trades_60s']},{m['post_trades_0_400s']},"
                f"{m['price_at_T0']},{m['mean_first_30s']},{m['mean_around_60s']},{m['shape']}\n"
            )

    # Summary
    summary = {
        "n_markets": len(per_market),
        "shape_counts": shape_counts,
        "post_trades_mean": statistics.mean(post_trades_counts) if post_trades_counts else None,
        "post_trades_median": statistics.median(post_trades_counts) if post_trades_counts else None,
        "sample_per_market_keys": list(per_market[0].keys()) if per_market else [],
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    print(json.dumps(summary, indent=2))
    print(f"\nper_market csv: {csv_path}")


if __name__ == "__main__":
    asyncio.run(main())
