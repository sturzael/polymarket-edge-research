"""Wraps polymarket_apis.PolymarketGammaClient with the calls e12 needs.

The wrapper exists for two reasons:
  1. Make the gamma client async-friendly via asyncio.to_thread (the upstream
     client is sync; we don't want to block the daemon loop)
  2. Centralize the few specific queries we make so the V2 cutover migration
     script can swap one place
"""
from __future__ import annotations

import asyncio
from typing import Iterable

from polymarket_apis import PolymarketGammaClient, PolymarketReadOnlyClobClient
from polymarket_apis.types.gamma_types import GammaMarket

from . import config

_gamma: PolymarketGammaClient | None = None
_clob: PolymarketReadOnlyClobClient | None = None


def gamma() -> PolymarketGammaClient:
    global _gamma
    if _gamma is None:
        _gamma = PolymarketGammaClient()
    return _gamma


def clob() -> PolymarketReadOnlyClobClient:
    global _clob
    if _clob is None:
        _clob = PolymarketReadOnlyClobClient()
    return _clob


def _matches_sports_slug(slug: str) -> bool:
    s = (slug or "").lower()
    return any(p in s for p in config.SPORTS_SLUG_PATTERNS)


async def fetch_active_sports_markets(limit: int = 200) -> list[GammaMarket]:
    """Active, not-closed markets that look like sports (slug-substring filter)."""
    out: list[GammaMarket] = []
    offset = 0
    while True:
        batch = await asyncio.to_thread(
            gamma().get_markets, closed=False, active=True, limit=limit, offset=offset,
        )
        if not batch:
            break
        out.extend(m for m in batch if _matches_sports_slug(m.slug or ""))
        if len(batch) < limit:
            break
        offset += limit
        if offset > 4000:  # safety cap
            break
    return out


async def fetch_recently_resolved_sports_markets(limit: int = 200) -> list[GammaMarket]:
    """Recently-closed sports markets — used by slug_audit and missed_scanner."""
    batch = await asyncio.to_thread(
        gamma().get_markets, closed=True, limit=limit,
        order="closed_time", ascending=False,
    )
    return [m for m in (batch or []) if _matches_sports_slug(m.slug or "")]


async def fetch_market_by_slug(slug: str) -> GammaMarket | None:
    return await asyncio.to_thread(gamma().get_market_by_slug, slug)


async def fetch_clob_market(condition_id: str):
    return await asyncio.to_thread(clob().get_market, condition_id)


async def fetch_order_book(token_id: str):
    return await asyncio.to_thread(clob().get_order_book, token_id)
