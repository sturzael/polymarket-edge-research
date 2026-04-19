"""Risk gates: drawdown breaker + event concentration cap + early-kill check."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from . import config, trader_client


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(config.SIDECAR_DB, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def cell_drawdown(cell: str) -> float:
    """Return drawdown as a negative fraction of seed (e.g. -0.15 = down 15%)."""
    bal = trader_client.get_balance_sync(cell)
    if not bal:
        return 0.0
    cash = float(bal.get("cash", 0))
    portfolio_value = float(bal.get("total_value", bal.get("portfolio_value", cash)))
    seed = config.SEED_BALANCE
    return (portfolio_value - seed) / seed if seed > 0 else 0.0


def drawdown_exceeded(cell: str) -> bool:
    return cell_drawdown(cell) < -config.MAX_DRAWDOWN_PER_CELL


def event_concentration_exceeded(cell: str, event_id: str | None) -> bool:
    if not event_id:
        return False
    with _db() as conn:
        cur = conn.execute(
            """SELECT COUNT(*) FROM position_context
               WHERE account = ? AND event_id = ? AND resolution_status = 'open'""",
            (cell, event_id),
        )
        n = cur.fetchone()[0]
    return n >= config.MAX_OPEN_PER_EVENT


def already_open_position(cell: str, market_slug: str, side: str) -> bool:
    with _db() as conn:
        cur = conn.execute(
            """SELECT 1 FROM position_context
               WHERE account = ? AND market_slug = ? AND side = ? AND resolution_status = 'open'
               LIMIT 1""",
            (cell, market_slug, side),
        )
        return cur.fetchone() is not None


def early_killed(cell: str) -> bool:
    """20-trade rule: KILL the cell if it's clearly negative at n>=EARLY_KILL_AFTER_TRADES."""
    with _db() as conn:
        cur = conn.execute(
            """SELECT COUNT(*) AS n,
                      COALESCE(SUM(CASE WHEN resolution_status IN ('resolved_win','resolved_loss')
                                        THEN 1 ELSE 0 END), 0) AS resolved
               FROM position_context WHERE account = ?""",
            (cell,),
        )
        row = cur.fetchone()
    if not row or row["resolved"] < config.EARLY_KILL_AFTER_TRADES:
        return False
    # Pull realized PnL from pm-trader history for this cell
    history = trader_client.get_history_sync(cell)
    if not history:
        return False
    realized_pnl = sum(getattr(t, "realized_pnl", 0) or 0 for t in history)
    if realized_pnl >= 0:
        return False
    # Notional-weighted net edge: average per-share net pnl across resolved positions
    # (rough: realized_pnl < 0 + n >= 20 → kill cell)
    return True
