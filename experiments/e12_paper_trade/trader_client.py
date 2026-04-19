"""Per-cell pm-trader Engine wrapper.

pm_trader.engine.Engine takes a `data_dir: Path`. We give each cell its own
directory so balances, positions, and trade history are fully isolated.

API surface used:
  - init_account(balance) → Account (idempotent on re-call? — we check first)
  - get_balance() → dict
  - get_portfolio() → dict
  - get_history() → trades
  - buy(slug_or_id, outcome, amount_usd, order_type='fok') → TradeResult
  - resolve_all() → handles closed markets
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from pm_trader.engine import Engine

from . import config


_engines: dict[str, Engine] = {}


def engine_for(cell: str) -> Engine:
    """Return (creating if needed) the Engine for one cell."""
    if cell not in _engines:
        cell_dir = config.CELLS_DIR / cell
        cell_dir.mkdir(parents=True, exist_ok=True)
        eng = Engine(data_dir=cell_dir)
        # init_account is idempotent in spirit — guard by trying get_balance first
        try:
            bal = eng.get_balance()
            if not bal or bal.get("cash") is None:
                eng.init_account(balance=config.SEED_BALANCE)
        except Exception:
            eng.init_account(balance=config.SEED_BALANCE)
        _engines[cell] = eng
    return _engines[cell]


def ensure_all_cells() -> dict[str, dict]:
    """Initialize every cell from config.ACCOUNTS. Returns balances per cell."""
    out: dict[str, dict] = {}
    for strategy, size_model, entry_cap in config.ACCOUNTS:
        cell = config.cell_name(strategy, size_model, entry_cap)
        eng = engine_for(cell)
        out[cell] = eng.get_balance()
    return out


async def buy(cell: str, slug: str, outcome: str, amount_usd: float, order_type: str = "fok"):
    """Async wrapper. Returns the pm-trader TradeResult or raises."""
    eng = engine_for(cell)
    return await asyncio.to_thread(eng.buy, slug, outcome, amount_usd, order_type)


async def get_balance(cell: str) -> dict:
    eng = engine_for(cell)
    return await asyncio.to_thread(eng.get_balance)


async def get_portfolio(cell: str) -> dict:
    eng = engine_for(cell)
    return await asyncio.to_thread(eng.get_portfolio)


async def get_history(cell: str) -> list:
    eng = engine_for(cell)
    return await asyncio.to_thread(eng.get_history)


async def resolve_all(cell: str):
    eng = engine_for(cell)
    return await asyncio.to_thread(eng.resolve_all)
