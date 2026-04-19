"""Phase 1b — observe-only detection counter for N hours.

Runs the full detection loop without placing orders. Logs every detection
to the sidecar `detections` table with skipped_reason='observe_only'.

Output: extrapolated hours-to-SAMPLE_TARGET_TRADES, and a flag if > 7 days.

Usage:
    uv run python -m experiments.e12_paper_trade.pre_run --hours 1
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import datetime, timezone

from . import config, detector, sidecar


async def run(hours: float) -> int:
    sidecar.init_db()
    print(f"[pre_run] observe-only detection for {hours:.1f}h, "
          f"target sample {config.SAMPLE_TARGET_TRADES} trades/cell")
    started = time.time()
    end_at = started + hours * 3600
    seen_markets: dict[str, int] = {}  # slug → count of detections
    detection_count = 0
    while time.time() < end_at:
        try:
            candidates = await detector.find_entries_book_poll()
        except Exception as e:
            print(f"  detector error: {e}")
            await asyncio.sleep(config.POLL_INTERVAL_S)
            continue
        for c in candidates:
            sidecar.log_detection(
                account=None, strategy="sports_lag",
                detection_path=c.detection_path, market_slug=c.market_slug,
                event_id=c.event_id, last_trade=c.last_trade,
                best_ask=c.best_ask, ask_size=c.ask_size,
                skipped_reason="observe_only",
            )
            seen_markets[c.market_slug] = seen_markets.get(c.market_slug, 0) + 1
            detection_count += 1
        elapsed = time.time() - started
        if int(elapsed) % 60 == 0 and elapsed > 0:
            unique = len(seen_markets)
            print(f"  t+{int(elapsed)}s: {detection_count} detections, "
                  f"{unique} unique markets, {len(candidates)} in last scan")
        await asyncio.sleep(config.POLL_INTERVAL_S)
    elapsed = time.time() - started
    unique = len(seen_markets)
    rate_per_hour = unique / max(elapsed / 3600, 1e-9)
    # Sample target is per cell × 4 cells = 300 trades; but each unique market is
    # at most 1 fill per cell (already_open guard), so we estimate by:
    # extrapolated_trades = unique_markets × 4 cells × probability-cell-takes-it
    # Conservative: each unique market → 1 trade (averaging across the 4 cells).
    extrapolated_to_target_hours = (config.SAMPLE_TARGET_TRADES / max(rate_per_hour, 1e-9))
    print()
    print("=" * 60)
    print(f"[pre_run] elapsed {elapsed/3600:.2f}h, {detection_count} detections, {unique} unique markets")
    print(f"  unique-market detection rate: {rate_per_hour:.1f}/hour")
    print(f"  extrapolated hours to {config.SAMPLE_TARGET_TRADES} trades/cell: {extrapolated_to_target_hours:.1f}")
    if extrapolated_to_target_hours > 7 * 24:
        print(f"  ⚠ projection > 7 days — scope change required (broaden filter, lower target, or add cells)")
        return 1
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--hours", type=float, default=1.0)
    args = p.parse_args()
    return asyncio.run(run(args.hours))


if __name__ == "__main__":
    sys.exit(main())
