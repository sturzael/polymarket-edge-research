"""Minimal Polymarket gamma-api wrapper for the probe.

Important: the `duration_s` we compute from `endDate - startDate` is often the
duration of the *market series* (e.g. 1 day), not the individual contract. For
the up/down family we parse duration from the slug itself (e.g. `btc-updown-5m-...`)
since that's the authoritative signal.

Docs (unofficial): gamma-api.polymarket.com returns JSON arrays from /markets.
Fields we use per market: conditionId (id), slug, question, outcomes,
clobTokenIds (stringified JSON array), endDate, startDate, active, closed,
bestBid, bestAsk, lastTradePrice, volume24hr, umaResolutionStatus.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone

import aiohttp

log = logging.getLogger(__name__)

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"


def _iso_to_ms(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except Exception:
        return None


SLUG_DURATION_RE = re.compile(r"-updown-(\d+)(m|h|d)-")
_UNIT_TO_S = {"m": 60, "h": 3600, "d": 86400}


def parse_slug_duration_s(slug: str | None) -> int | None:
    """Parse `-updown-<N><unit>-` from the slug. Returns duration in seconds or None."""
    if not slug:
        return None
    m = SLUG_DURATION_RE.search(slug)
    if not m:
        return None
    return int(m.group(1)) * _UNIT_TO_S[m.group(2)]


def normalize_market(raw: dict) -> dict:
    """Turn a gamma-api market object into the flat dict we store."""
    end_ms = _iso_to_ms(raw.get("endDate"))
    start_ms = _iso_to_ms(raw.get("startDate")) or _iso_to_ms(raw.get("createdAt"))
    slug = raw.get("slug")
    # Prefer slug-derived duration for up/down series (authoritative).
    slug_dur = parse_slug_duration_s(slug)
    duration = slug_dur
    if duration is None and end_ms and start_ms:
        duration = (end_ms - start_ms) // 1000
    # outcomes and clobTokenIds come back as stringified JSON in gamma-api
    def _maybe_parse(v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return v
        return v
    return {
        "market_id": raw.get("conditionId") or raw.get("id"),
        "slug": slug,
        "question": raw.get("question"),
        "outcomes": json.dumps(_maybe_parse(raw.get("outcomes"))) if raw.get("outcomes") else None,
        "clob_token_ids": json.dumps(_maybe_parse(raw.get("clobTokenIds"))) if raw.get("clobTokenIds") else None,
        "start_ts": start_ms,
        "end_ts": end_ms,
        "duration_s": duration,
        "resolution_source": raw.get("resolutionSource") or raw.get("umaResolutionStatus"),
        "best_bid": raw.get("bestBid"),
        "best_ask": raw.get("bestAsk"),
        "last_trade_price": raw.get("lastTradePrice"),
        "volume_24hr": raw.get("volume24hr"),
        "closed": raw.get("closed"),
        "active": raw.get("active"),
        "umadata": json.dumps({
            "status": raw.get("umaResolutionStatus"),
            "negRisk": raw.get("negRisk"),
        }) if raw.get("umaResolutionStatus") else None,
    }


class PolymarketAPI:
    def __init__(self, session: aiohttp.ClientSession, base: str = GAMMA_BASE):
        self.session = session
        self.base = base

    async def list_active_markets(
        self,
        limit: int = 200,
        offset: int = 0,
        ascending_end: bool = True,
    ) -> list[dict]:
        """Fetch a page of active, non-closed markets sorted by endDate ascending."""
        params = {
            "closed": "false",
            "active": "true",
            "limit": str(limit),
            "offset": str(offset),
            "order": "endDate",
            "ascending": "true" if ascending_end else "false",
        }
        return await self._get_json("/markets", params)

    async def get_market(self, condition_id: str) -> dict | None:
        """Fetch a specific market by conditionId.

        gamma-api's /markets/{id} expects a numeric primary key, not a hex
        conditionId, so we use the filtered list endpoint instead.
        """
        data = await self._get_json("/markets", {"condition_ids": condition_id, "limit": "1"})
        if isinstance(data, list) and data:
            return data[0]
        return None

    async def get_clob_market(self, condition_id: str) -> dict | None:
        """Fetch a market from the CLOB. CLOB keeps markets visible after expiry
        (gamma-api drops them), and exposes `tokens[].winner` for resolution."""
        url = f"{CLOB_BASE}/markets/{condition_id}"
        backoff = 1.0
        for _ in range(3):
            try:
                async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status == 404:
                        return None
                    if r.status == 429:
                        await asyncio.sleep(backoff)
                        backoff = min(backoff * 2, 30.0)
                        continue
                    if r.status >= 400:
                        return None
                    return await r.json()
            except (aiohttp.ClientError, asyncio.TimeoutError):
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
        return None

    @staticmethod
    def extract_clob_outcome(clob_market: dict) -> tuple[str | None, float | None, float | None]:
        """From a CLOB market dict, return (winner_label_upper, up_price, down_price).

        If no token has winner=True, winner_label_upper is None (unresolved).
        """
        if not clob_market:
            return None, None, None
        tokens = clob_market.get("tokens") or []
        up_price = down_price = None
        winner_label: str | None = None
        for t in tokens:
            outcome = (t.get("outcome") or "").lower()
            if outcome in ("up", "yes"):
                up_price = t.get("price")
            elif outcome in ("down", "no"):
                down_price = t.get("price")
            if t.get("winner"):
                winner_label = (t.get("outcome") or "").upper()
        return winner_label, up_price, down_price

    async def get_markets_bulk(self, condition_ids: list[str], batch_size: int = 50) -> list[dict]:
        """Fetch multiple markets at once.

        gamma-api wants repeated `condition_ids` query parameters — not a
        comma-separated value (which silently returns 0 rows).
        """
        if not condition_ids:
            return []
        out: list[dict] = []
        for i in range(0, len(condition_ids), batch_size):
            batch = condition_ids[i:i + batch_size]
            params: list[tuple[str, str]] = [("condition_ids", cid) for cid in batch]
            params.append(("limit", str(batch_size)))
            data = await self._get_json("/markets", params)
            if isinstance(data, list):
                out.extend(data)
        return out

    async def _get_json(
        self,
        path: str,
        params: dict | list[tuple[str, str]] | None = None,
    ) -> list | dict | None:
        url = f"{self.base}{path}"
        backoff = 1.0
        for attempt in range(5):
            try:
                async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as r:
                    if r.status == 429:
                        log.warning("429 from %s; backing off %.1fs", path, backoff)
                        await asyncio.sleep(backoff)
                        backoff = min(backoff * 2, 30.0)
                        continue
                    r.raise_for_status()
                    return await r.json()
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                log.warning("http error %s on %s (attempt %d): %s", type(e).__name__, path, attempt, e)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
        return None


# --- crypto detection ---

CRYPTO_KEYWORDS: dict[str, str | None] = {
    # Specific assets mapped to underlying symbols
    "bitcoin": "BTC", "btc": "BTC",
    "ethereum": "ETH", "eth": "ETH",
    "solana": "SOL", "sol": "SOL",
    "ripple": "XRP", "xrp": "XRP",
    "bnb": "BNB",
    "dogecoin": "DOGE", "doge": "DOGE",
    "cardano": "ADA", "ada": "ADA",
    "avalanche": "AVAX", "avax": "AVAX",
    "chainlink": "LINK", "link": "LINK",
    "polkadot": "DOT",
    "polygon": "MATIC", "matic": "MATIC",
    "tron": "TRX", "trx": "TRX",
    "shiba": "SHIB",
    "pepe": "PEPE",
    # Generic crypto mention (underlying not derivable)
    "crypto": None,
    "altcoin": None,
}

PRICE_PATTERNS = (
    "up or down", "up/down", "close above", "close below", "close at",
    "reach $", "hit $", "dip to", "drop to", "rise to", "break",
    "hourly", "daily close", "end of day", "price on", "price at",
)


def detect_crypto(slug: str | None, question: str | None) -> tuple[bool, str | None]:
    """Return (is_crypto, underlying_symbol_or_None)."""
    text = f"{slug or ''} {question or ''}".lower()
    underlying: str | None = None
    hit = False
    for kw, sym in CRYPTO_KEYWORDS.items():
        if kw in text:
            hit = True
            if sym and underlying is None:
                underlying = sym
    # boost on price patterns
    if hit:
        return True, underlying
    # also flag if price pattern present alongside $-amounts (weaker)
    if any(p in text for p in PRICE_PATTERNS) and "$" in text:
        # Probably still not crypto if no crypto word found
        return False, None
    return False, None


def now_utc_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)
