"""Main loop. Restart-safe (state in SQLite — kill -9 and re-launch continues).

Per plan §"Daemon loop":
  - book_poll detection at POLL_INTERVAL_S
  - ESPN feed listener for game-end events (Path A)
  - missed_scanner periodic worker
  - resolver checks open positions every loop
  - cutover-window pause via daemon_state.paused
  - per-cell 2x2 grid: cap_too_tight / drawdown / event_concentration / early_killed gates
  - position_context + detections logging in sidecar
"""
from __future__ import annotations

import asyncio
import logging
import sys
import time
from datetime import datetime, timezone

from . import (config, detector, gamma_client, missed_scanner, resolver, risk,
               sidecar, sports_feeds, trader_client)

logger = logging.getLogger("e12.daemon")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


_started_at = time.time()


def reached_sample_target() -> bool:
    """All 4 cells need to hit SAMPLE_TARGET_TRADES."""
    counts = sidecar.total_completed_trades_per_cell()
    return all(
        counts.get(config.cell_name(*acc), 0) >= config.SAMPLE_TARGET_TRADES
        for acc in config.ACCOUNTS
    )


def past_max_run() -> bool:
    return (time.time() - _started_at) > (config.MAX_RUN_HOURS * 3600)


def cutover_pause_active() -> bool:
    """Paused between V2_CUTOVER_PAUSE_AT and V2_CUTOVER_RESUME_NO_EARLIER_THAN
    (or while sidecar state.paused == 1)."""
    if sidecar.is_paused():
        return True
    now = datetime.now(timezone.utc)
    return config.V2_CUTOVER_PAUSE_AT <= now < config.V2_CUTOVER_RESUME_NO_EARLIER_THAN


async def _record_fill(det_id: int, cell: str, c: detector.Candidate,
                       size_model: str, entry_cap: float,
                       protocol_version: str, started_ms: float) -> None:
    """Place the buy via pm-trader and update sidecar."""
    size_usd = detector.compute_size_usd(c, size_model)
    if size_usd < 1:
        sidecar.update_detection_fill(
            det_id, fill_completed_at=datetime.now(timezone.utc).isoformat(),
            fill_price=0.0, fill_qty=0.0, latency_ms=0, slippage_bps=0.0,
        )
        return
    try:
        tr = await trader_client.buy(cell, c.market_slug, c.side, size_usd, "fok")
    except Exception as e:
        logger.warning(f"buy failed cell={cell} slug={c.market_slug}: {e}")
        sidecar.update_detection_fill(
            det_id, fill_completed_at=datetime.now(timezone.utc).isoformat(),
            fill_price=0.0, fill_qty=0.0,
            latency_ms=int((time.time() * 1000) - started_ms), slippage_bps=0.0,
        )
        return
    completed = datetime.now(timezone.utc).isoformat()
    fill_price = float(tr.trade.avg_price)
    fill_qty = float(tr.trade.shares)
    latency_ms = int((time.time() * 1000) - started_ms)
    slippage_bps = ((fill_price - c.best_ask) / max(c.best_ask, 1e-9)) * 10_000
    sidecar.update_detection_fill(
        det_id, fill_completed_at=completed,
        fill_price=fill_price, fill_qty=fill_qty,
        latency_ms=latency_ms, slippage_bps=slippage_bps,
    )
    sidecar.insert_position_context(
        pm_trade_id=f"{cell}::{tr.trade.id}", account=cell,
        strategy="sports_lag", size_model=size_model, entry_cap=entry_cap,
        detection_path=c.detection_path, market_slug=c.market_slug,
        event_id=c.event_id, side=c.side,
        entry_ask=c.best_ask, entry_bid=c.best_bid,
        ask_size_at_entry=c.ask_size, protocol_version=protocol_version,
        market_context={"condition_id": c.condition_id, "last_trade": c.last_trade},
    )
    logger.info(
        f"FILL cell={cell} slug={c.market_slug[:50]} side={c.side} "
        f"size_usd={size_usd:.2f} fill_price={fill_price:.4f} qty={fill_qty:.2f} "
        f"latency_ms={latency_ms}",
    )


async def maybe_place(c: detector.Candidate, protocol_version: str) -> None:
    started_ms = time.time() * 1000
    for strategy, size_model, entry_cap in config.ACCOUNTS:
        cell = config.cell_name(strategy, size_model, entry_cap)
        # Each cell uses its own entry cap; book_poll detection uses max cap, so some cells skip
        if c.best_ask > entry_cap:
            sidecar.log_detection(
                account=cell, strategy=strategy, detection_path=c.detection_path,
                market_slug=c.market_slug, event_id=c.event_id,
                last_trade=c.last_trade, best_ask=c.best_ask, ask_size=c.ask_size,
                skipped_reason="cap_too_tight",
            ); continue
        if risk.already_open_position(cell, c.market_slug, c.side):
            sidecar.log_detection(
                account=cell, strategy=strategy, detection_path=c.detection_path,
                market_slug=c.market_slug, event_id=c.event_id,
                last_trade=c.last_trade, best_ask=c.best_ask, ask_size=c.ask_size,
                skipped_reason="already_open",
            ); continue
        if risk.drawdown_exceeded(cell):
            sidecar.log_detection(
                account=cell, strategy=strategy, detection_path=c.detection_path,
                market_slug=c.market_slug, event_id=c.event_id,
                last_trade=c.last_trade, best_ask=c.best_ask, ask_size=c.ask_size,
                skipped_reason="drawdown_breaker",
            ); continue
        if risk.event_concentration_exceeded(cell, c.event_id):
            sidecar.log_detection(
                account=cell, strategy=strategy, detection_path=c.detection_path,
                market_slug=c.market_slug, event_id=c.event_id,
                last_trade=c.last_trade, best_ask=c.best_ask, ask_size=c.ask_size,
                skipped_reason="event_concentration_cap",
            ); continue
        if risk.early_killed(cell):
            sidecar.log_detection(
                account=cell, strategy=strategy, detection_path=c.detection_path,
                market_slug=c.market_slug, event_id=c.event_id,
                last_trade=c.last_trade, best_ask=c.best_ask, ask_size=c.ask_size,
                skipped_reason="early_killed",
            ); continue

        det_id = sidecar.log_detection(
            account=cell, strategy=strategy, detection_path=c.detection_path,
            market_slug=c.market_slug, event_id=c.event_id,
            last_trade=c.last_trade, best_ask=c.best_ask, ask_size=c.ask_size,
            skipped_reason=None,
            fill_attempted_at=datetime.now(timezone.utc).isoformat(),
        )
        await _record_fill(det_id, cell, c, size_model, entry_cap, protocol_version, started_ms)


async def _feed_listener() -> None:
    """Path A — sports feed → detector → maybe_place."""
    async for ev in sports_feeds.listen():
        if cutover_pause_active():
            continue
        # Map (home, away, winner) → Polymarket market and check ask
        winner = ev.home if ev.winner == "home" else (ev.away if ev.winner == "away" else None)
        if not winner:
            continue
        try:
            c = await detector.check_entry_from_feed(ev.home, ev.away, ev.winner)
        except Exception as e:
            logger.warning(f"check_entry_from_feed error for {ev.home} vs {ev.away}: {e}")
            continue
        if c is None:
            continue
        # Override detection_path so we can stratify
        c.detection_path = "feed"
        await maybe_place(c, sidecar.current_protocol_version())


async def main() -> int:
    sidecar.init_db()
    print(f"[daemon] init cells: {[config.cell_name(*a) for a in config.ACCOUNTS]}")
    balances = trader_client.ensure_all_cells()
    for cell, bal in balances.items():
        print(f"  {cell}: {bal}")

    feed_task = asyncio.create_task(_feed_listener(), name="feed_listener")
    missed_task = asyncio.create_task(missed_scanner.run_periodic(300), name="missed_scanner")

    while not reached_sample_target() and not past_max_run():
        if cutover_pause_active():
            logger.info("cutover_pause_active — sleeping 60s")
            await asyncio.sleep(60)
            continue
        proto = sidecar.current_protocol_version()
        try:
            candidates = await detector.find_entries_book_poll()
        except Exception as e:
            logger.warning(f"book_poll error: {e}")
            await asyncio.sleep(config.POLL_INTERVAL_S)
            continue
        for c in candidates:
            await maybe_place(c, proto)

        try:
            await resolver.check_open_positions()
        except Exception as e:
            logger.warning(f"resolver error: {e}")

        await asyncio.sleep(config.POLL_INTERVAL_S)

    feed_task.cancel()
    missed_task.cancel()
    print("[daemon] reached sample target or max run; exiting cleanly")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
