"""Resolver — for each open position, mark resolved/disputed/stuck.

For pm-trader, calling resolve_all() per cell handles closed markets by
crediting payout. We additionally update the sidecar position_context
status so the report can stratify.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from . import config, gamma_client, sidecar, trader_client

logger = logging.getLogger(__name__)


async def check_open_positions() -> dict:
    out = {"resolved": 0, "disputed": 0, "stuck": 0, "still_open": 0, "errors": 0}
    rows = sidecar.open_positions()
    if not rows:
        return out

    by_slug = {}
    for r in rows:
        by_slug.setdefault(r["market_slug"], []).append(r)

    for slug, slug_rows in by_slug.items():
        try:
            m = await gamma_client.fetch_market_by_slug(slug)
        except Exception as e:
            logger.warning(f"resolver: gamma fetch failed for {slug}: {e}")
            out["errors"] += 1
            continue
        if m is None:
            out["errors"] += 1
            continue
        closed = bool(getattr(m, "closed", False))
        outcome_prices_raw = getattr(m, "outcome_prices", None)
        # outcome_prices comes through as list[float] or stringified
        try:
            if isinstance(outcome_prices_raw, str):
                outcomes = json.loads(outcome_prices_raw.replace("'", '"'))
            else:
                outcomes = list(outcome_prices_raw or [])
            outcomes = [float(x) for x in outcomes]
        except Exception:
            outcomes = []

        uma_status = getattr(m, "uma_resolution_status", None) or getattr(m, "umaResolutionStatus", None)

        for r in slug_rows:
            age_min = (datetime.now(timezone.utc) - datetime.fromisoformat(r["detected_at"])).total_seconds() / 60
            side = r["side"]
            if not closed:
                if age_min > 24 * 60:
                    sidecar.update_resolution(r["pm_trade_id"], resolution_price=0.0, resolution_status="stuck")
                    out["stuck"] += 1
                else:
                    out["still_open"] += 1
                continue
            if uma_status and uma_status.lower() != "resolved":
                sidecar.update_resolution(r["pm_trade_id"], resolution_price=0.0, resolution_status="disputed")
                out["disputed"] += 1
                continue
            if len(outcomes) >= 2 and set(outcomes).issubset({0.0, 1.0}):
                yes_payout = outcomes[0]
                payout = yes_payout if side == "YES" else (1 - yes_payout)
                status = "resolved_win" if payout == 1.0 else "resolved_loss"
                sidecar.update_resolution(r["pm_trade_id"], resolution_price=payout, resolution_status=status)
                out["resolved"] += 1
            else:
                # Unclear payout shape; mark stuck for human review
                sidecar.update_resolution(r["pm_trade_id"], resolution_price=0.0, resolution_status="stuck")
                out["stuck"] += 1

    # Also tell pm-trader to resolve internally so its portfolio reflects payouts
    for strategy, size_model, entry_cap in config.ACCOUNTS:
        cell = config.cell_name(strategy, size_model, entry_cap)
        try:
            await trader_client.resolve_all(cell)
        except Exception as e:
            logger.warning(f"pm-trader resolve_all failed for {cell}: {e}")

    return out


if __name__ == "__main__":
    sidecar.init_db()
    print(asyncio.run(check_open_positions()))
