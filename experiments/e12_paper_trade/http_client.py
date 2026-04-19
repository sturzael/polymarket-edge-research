"""Shared httpx.AsyncClient + pyrate-limiter for any non-gamma HTTP.

Per docs.polymarket.com/quickstart/introduction/rate-limits:
  /markets:      300 req / 10s
  /events:       500 req / 10s
  general:      4000 req / 10s

We pre-emptively limit at half the published cap.
"""
from __future__ import annotations

import httpx
from pyrate_limiter import Duration, Limiter, RequestRate

from . import config

_client: httpx.AsyncClient | None = None
_limiter_markets = Limiter(
    RequestRate(config.GAMMA_MARKETS_LIMIT_PER_10S // 2, Duration.SECOND * 10)
)
_limiter_events = Limiter(
    RequestRate(config.GAMMA_EVENTS_LIMIT_PER_10S // 2, Duration.SECOND * 10)
)
_limiter_general = Limiter(
    RequestRate(config.GAMMA_GENERAL_LIMIT_PER_10S // 2, Duration.SECOND * 10)
)


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0),
            headers={"User-Agent": "e12-paper-trade/0.1"},
        )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def limiter_for(path: str) -> Limiter:
    if "/markets" in path:
        return _limiter_markets
    if "/events" in path:
        return _limiter_events
    return _limiter_general
