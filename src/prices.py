from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import ccxt.async_support as ccxt

from .storage import Storage, now_ms

log = logging.getLogger(__name__)


@dataclass
class PricesConfig:
    exchange: str
    tickers: list[str]
    poll_interval_s: float


class CryptoPriceFeed:
    """Polls Binance (via ccxt) for the configured tickers at fixed cadence.

    Uses fetch_tickers (one request, many symbols) instead of fetch_ticker per symbol
    to stay well below Binance rate limits even at 1s cadence.
    """

    def __init__(self, cfg: PricesConfig, storage: Storage):
        self.cfg = cfg
        self.storage = storage
        self._exchange: ccxt.Exchange | None = None
        self._latest: dict[str, tuple[int, float]] = {}

    async def open(self) -> None:
        cls = getattr(ccxt, self.cfg.exchange)
        self._exchange = cls({"enableRateLimit": True})

    async def close(self) -> None:
        if self._exchange is not None:
            await self._exchange.close()
            self._exchange = None

    def latest_price(self, asset: str) -> float | None:
        entry = self._latest.get(asset)
        return entry[1] if entry else None

    async def run(self) -> None:
        """Forever: fetch_tickers every poll_interval_s, write to prices table."""
        assert self._exchange is not None
        backoff = 1.0
        while True:
            try:
                tickers = await self._exchange.fetch_tickers(self.cfg.tickers)
                ts = now_ms()
                rows: list[tuple[int, str, float]] = []
                for symbol, tick in tickers.items():
                    last = tick.get("last") or tick.get("close")
                    if last is None:
                        # Fall back to mid of bid/ask
                        bid, ask = tick.get("bid"), tick.get("ask")
                        if bid and ask:
                            last = (bid + ask) / 2
                    if last is not None:
                        rows.append((ts, symbol, float(last)))
                        self._latest[symbol] = (ts, float(last))
                if rows:
                    await self.storage.insert_prices(rows)
                backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # broad catch: network, rate-limit, parse
                log.warning("prices fetch error: %s (backoff %.1fs)", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
                continue
            await asyncio.sleep(self.cfg.poll_interval_s)
