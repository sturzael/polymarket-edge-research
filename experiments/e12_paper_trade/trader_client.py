"""Per-cell pm-trader Engine wrapper.

pm_trader.engine.Engine takes a `data_dir: Path`. We give each cell its own
directory so balances, positions, and trade history are fully isolated.

Threading: pm-trader's SQLite connection is bound to the thread that creates
it, so we give each cell a SINGLE-WORKER executor and route all calls
through it. This way the Engine's connection always sees the same thread,
and async callers don't block the event loop.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

from pm_trader.engine import Engine

from . import config


_engines: dict[str, Engine] = {}
_executors: dict[str, ThreadPoolExecutor] = {}


def _executor_for(cell: str) -> ThreadPoolExecutor:
    if cell not in _executors:
        _executors[cell] = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"cell-{cell}")
    return _executors[cell]


def engine_for(cell: str) -> Engine:
    """Return (creating if needed) the Engine for one cell. Engine is created
    inside its dedicated executor thread so its SQLite connection stays pinned."""
    if cell not in _engines:
        cell_dir = config.CELLS_DIR / cell
        cell_dir.mkdir(parents=True, exist_ok=True)

        def _create() -> Engine:
            eng = Engine(data_dir=cell_dir)
            try:
                bal = eng.get_balance()
                if not bal or bal.get("cash") is None:
                    eng.init_account(balance=config.SEED_BALANCE)
            except Exception:
                eng.init_account(balance=config.SEED_BALANCE)
            return eng

        # Block here — engine creation is one-shot and we need the result before returning
        _engines[cell] = _executor_for(cell).submit(_create).result()
    return _engines[cell]


def ensure_all_cells() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for strategy, size_model, entry_cap in config.ACCOUNTS:
        cell = config.cell_name(strategy, size_model, entry_cap)
        eng = engine_for(cell)
        # get_balance also has to run on the cell's thread
        out[cell] = _executor_for(cell).submit(eng.get_balance).result()
    return out


async def _run_in_cell(cell: str, fn, *args, **kwargs):
    """Submit `fn(*args, **kwargs)` to the cell's dedicated executor and await."""
    eng = engine_for(cell)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor_for(cell), lambda: fn(eng, *args, **kwargs))


async def buy(cell: str, slug: str, outcome: str, amount_usd: float, order_type: str = "fok"):
    return await _run_in_cell(cell,
                              lambda eng, *a, **k: eng.buy(*a, **k),
                              slug, outcome, amount_usd, order_type)


async def get_balance(cell: str) -> dict:
    return await _run_in_cell(cell, lambda eng: eng.get_balance())


async def get_portfolio(cell: str) -> dict:
    return await _run_in_cell(cell, lambda eng: eng.get_portfolio())


async def get_history(cell: str) -> list:
    return await _run_in_cell(cell, lambda eng: eng.get_history())


async def resolve_all(cell: str):
    return await _run_in_cell(cell, lambda eng: eng.resolve_all())


# --- sync helpers for non-async call sites (risk.py) ---

def get_balance_sync(cell: str) -> dict:
    eng = engine_for(cell)
    return _executor_for(cell).submit(eng.get_balance).result()


def get_history_sync(cell: str) -> list:
    eng = engine_for(cell)
    return _executor_for(cell).submit(eng.get_history).result()
