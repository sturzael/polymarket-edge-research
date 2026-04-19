"""Dual-path entry detector for sports_lag.

Path A — feed-triggered: GameEndEvent fires → look up Polymarket market → check ask
Path B — book-state poll: every POLL_INTERVAL_S, scan active sports markets

Both paths emit Candidate(market_slug, side, best_ask, best_bid, ask_size, event_id, detection_path).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Iterable

from . import config, gamma_client


@dataclass
class Candidate:
    market_slug: str
    condition_id: str
    side: str                 # 'YES' | 'NO'
    best_ask: float
    best_bid: float | None
    ask_size: float
    event_id: str | None
    last_trade: float
    detection_path: str       # 'feed' | 'book_poll'


def _winning_side_from_last_trade(last_trade_price: float) -> str | None:
    if last_trade_price > 0.95:
        return "YES"
    if last_trade_price < 0.05:
        return "NO"
    return None


async def find_entries_book_poll(max_to_check: int = 200) -> list[Candidate]:
    """Path B — scan all active sports markets at the broadest cap."""
    markets = await gamma_client.fetch_active_sports_markets(limit=max_to_check)
    out: list[Candidate] = []
    max_cap = max(config.ENTRY_TARGET_CAPS)
    for m in markets:
        # zombie filter is enforced by the gamma query (closed=False, active=True)
        ltp = getattr(m, "last_trade_price", None)
        ba = getattr(m, "best_ask", None)
        if ltp is None or ba is None:
            continue
        ltp, ba = float(ltp), float(ba)
        side = _winning_side_from_last_trade(ltp)
        if side is None:
            continue
        # If NO is winning, the meaningful ask is the NO-side ask (= 1 - YES_bid roughly).
        # gamma's `best_ask` is for the YES token; we approximate the NO-side ask as
        # 1 - best_bid (best YES bid → NO ask). Skip markets where we can't infer it.
        if side == "YES":
            ask_for_buy = ba
        else:
            bb = getattr(m, "best_bid", None)
            if bb is None:
                continue
            ask_for_buy = 1 - float(bb)
        if ask_for_buy > max_cap or ask_for_buy < config.PRICE_LO_FOR_DETECTION:
            continue
        # Approximate ask size: gamma model has best_ask_size sometimes
        ask_size = float(getattr(m, "best_ask_size", None) or 0)
        out.append(Candidate(
            market_slug=m.slug or "",
            condition_id=m.condition_id or "",
            side=side,
            best_ask=ask_for_buy,
            best_bid=float(getattr(m, "best_bid", 0) or 0),
            ask_size=ask_size,
            event_id=str(getattr(m, "event_id", None) or "") or None,
            last_trade=ltp,
            detection_path="book_poll",
        ))
    return out


async def check_entry_from_feed(home: str, away: str, winner: str) -> Candidate | None:
    """Path A — find a Polymarket market for (home, away) and check ask depth.

    For v1 we use a simple slug-substring search. The polymarket-apis client
    doesn't have a free-text search; we fall back to scanning active sports
    markets and matching team names. Reasonable for a daily-volume of games.
    """
    home_lc = home.lower().replace(" ", "-")
    away_lc = away.lower().replace(" ", "-")
    candidates = await find_entries_book_poll(max_to_check=400)
    for c in candidates:
        s = c.market_slug.lower()
        if home_lc in s and away_lc in s:
            return c
    return None


def compute_size_usd(c: Candidate, size_model: str) -> float:
    """fixed_100 → $100; depth_scaled → 25% of $-value of available ask depth."""
    if size_model == "fixed_100":
        return min(config.FIXED_USD_SIZE, 1000.0)
    if size_model == "depth_scaled":
        depth_usd = c.ask_size * c.best_ask
        return max(min(depth_usd * config.DEPTH_SCALED_FRAC, 1000.0), 10.0)
    raise ValueError(f"unknown size_model: {size_model}")
