"""Polymarket short-duration crypto reconnaissance probe.

24-hour reconnaissance. Answers: do short-duration crypto markets exist often
enough to justify building the full Expiry Microstructure Mode?

Run: `uv run python -m probe.main [--hours 24] [--db probe/probe.db]`

Architecture: two bulk samplers rather than per-market tasks, so HTTP load stays
constant as tracked-market count grows.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal

import aiohttp
import ccxt.async_support as ccxt

from .api import (
    PolymarketAPI,
    detect_crypto,
    normalize_market,
    now_utc_ms,
)
from .db import ProbeDB, now_ms

log = logging.getLogger("probe")

# --- tuning knobs ---
DISCOVERY_INTERVAL_S = 45
DISCOVERY_MAX_PAGES = 20
MARKET_HORIZON_S = 25 * 3600  # track crypto markets whose end_ts is within this window

NORMAL_SAMPLE_INTERVAL_S = 15  # markets with time_to_end > final-stretch window
FINAL_STRETCH_WINDOW_S = 120    # within this of expiry: fast cadence
FINAL_SAMPLE_INTERVAL_S = 5
RESOLUTION_CHECK_INTERVAL_S = 10  # how often to poll CLOB for past-expiry markets
POST_EXPIRY_WATCH_S = 15 * 60   # give up if market not resolved this long after nominal end

BULK_BATCH_SIZE = 50            # condition_ids per bulk request
SPOT_POLL_S = 10
SPOT_TICKERS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "DOGE/USDT"]


class Probe:
    def __init__(self, db: ProbeDB, session: aiohttp.ClientSession, exchange: ccxt.Exchange):
        self.db = db
        self.api = PolymarketAPI(session)
        self.exchange = exchange
        self._stop = asyncio.Event()
        self._latest_spot: dict[str, tuple[int, float]] = {}
        self._resolved_ids: set[str] = set()   # short-circuit to avoid re-polling settled markets

    # ---- spot ----

    async def spot_loop(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                tickers = await self.exchange.fetch_tickers(SPOT_TICKERS)
                for sym, tick in tickers.items():
                    price = tick.get("last") or tick.get("close")
                    if price is None:
                        bid, ask = tick.get("bid"), tick.get("ask")
                        if bid and ask:
                            price = (bid + ask) / 2
                    if price is not None:
                        self._latest_spot[sym.split("/")[0]] = (now_ms(), float(price))
                backoff = 1.0
            except asyncio.CancelledError:
                return
            except Exception as e:
                log.warning("spot error: %s (backoff %.1fs)", e, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
                continue
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=SPOT_POLL_S)
            except asyncio.TimeoutError:
                pass

    def _spot_for(self, underlying: str | None) -> float | None:
        if not underlying:
            return None
        entry = self._latest_spot.get(underlying)
        return entry[1] if entry else None

    # ---- discovery ----

    async def discovery_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self._run_discovery()
            except asyncio.CancelledError:
                return
            except Exception as e:
                log.exception("discovery error: %s", e)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=DISCOVERY_INTERVAL_S)
            except asyncio.TimeoutError:
                pass

    async def _run_discovery(self) -> None:
        horizon_ms = now_utc_ms() + MARKET_HORIZON_S * 1000
        new_crypto = 0
        crypto_total = 0
        non_crypto = 0
        for page in range(DISCOVERY_MAX_PAGES):
            raw = await self.api.list_active_markets(limit=200, offset=page * 200)
            if not raw:
                break
            for rm in raw:
                n = normalize_market(rm)
                if not n["market_id"]:
                    continue
                is_c, und = detect_crypto(n["slug"], n["question"])
                n["is_crypto"] = is_c
                n["underlying"] = und
                n["first_seen"] = now_ms()
                n["last_seen"] = now_ms()
                n["raw_meta"] = json.dumps({
                    "bestBid": rm.get("bestBid"),
                    "bestAsk": rm.get("bestAsk"),
                    "volume24hr": rm.get("volume24hr"),
                    "umaResolutionStatus": rm.get("umaResolutionStatus"),
                    "negRisk": rm.get("negRisk"),
                })
                if not n["end_ts"]:
                    continue
                if not is_c:
                    non_crypto += 1
                    continue
                if now_utc_ms() <= n["end_ts"] <= horizon_ms:
                    is_new = await self.db.upsert_market(n)
                    crypto_total += 1
                    if is_new:
                        new_crypto += 1
                        log.info(
                            "NEW %s %s  dur=%s  ends_in=%.1fmin",
                            und or "?",
                            n["slug"],
                            _fmt_dur(n.get("duration_s")),
                            (n["end_ts"] - now_utc_ms()) / 60000,
                        )
            if len(raw) < 200:
                break
        log.info("discovery: new_crypto=%d active_crypto_in_horizon=%d non_crypto_skipped=%d",
                 new_crypto, crypto_total, non_crypto)

    # ---- sampler loops ----

    async def _tracked_markets_in_window(
        self, lo_ms: int, hi_ms: int
    ) -> list[tuple[str, int, str | None, str | None]]:
        """Return (market_id, end_ts, underlying, slug) for tracked, unresolved markets
        whose end_ts falls in [lo_ms, hi_ms]."""
        rows = await self.db.fetchall(
            """
            SELECT m.market_id, m.end_ts, m.underlying, m.slug
            FROM markets m
            LEFT JOIN resolutions r ON r.market_id = m.market_id
            WHERE m.is_crypto = 1
              AND m.end_ts BETWEEN ? AND ?
              AND (r.outcome IS NULL OR r.outcome = '')
            ORDER BY m.end_ts ASC
            """,
            (lo_ms, hi_ms),
        )
        return list(rows)

    async def normal_sampler(self) -> None:
        """Bulk-sample tracked markets with time_to_end > FINAL_STRETCH_WINDOW_S."""
        await self._sampler_loop(
            name="normal",
            interval_s=NORMAL_SAMPLE_INTERVAL_S,
            window_fn=lambda now: (now + FINAL_STRETCH_WINDOW_S * 1000 + 1, now + MARKET_HORIZON_S * 1000),
        )

    async def final_sampler(self) -> None:
        """Bulk-sample markets in the final stretch before expiry (gamma-api)."""
        # gamma-api drops markets the moment their endDate passes, so we only use it
        # for markets that are still pre-expiry. Post-expiry resolution uses CLOB below.
        await self._sampler_loop(
            name="final",
            interval_s=FINAL_SAMPLE_INTERVAL_S,
            window_fn=lambda now: (now + 1, now + FINAL_STRETCH_WINDOW_S * 1000),
        )

    async def resolution_checker(self) -> None:
        """Poll CLOB /markets/<cid> for each past-expiry crypto market until it resolves."""
        while not self._stop.is_set():
            try:
                await self._run_resolution_checks()
            except asyncio.CancelledError:
                return
            except Exception as e:
                log.exception("resolution checker error: %s", e)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=RESOLUTION_CHECK_INTERVAL_S)
            except asyncio.TimeoutError:
                pass

    async def _run_resolution_checks(self) -> None:
        now = now_utc_ms()
        lo = now - POST_EXPIRY_WATCH_S * 1000
        hi = now
        markets = await self._tracked_markets_in_window(lo, hi)
        # Filter out already-resolved
        markets = [m for m in markets if m[0] not in self._resolved_ids]
        if not markets:
            return
        newly_resolved = 0
        # Serial per-market to keep rate predictable (~5 req/s at 10s cadence × 50 markets)
        for cid, end_ts, underlying, slug in markets:
            clob = await self.api.get_clob_market(cid)
            if not clob:
                continue
            ts_now = now_ms()
            closed = bool(clob.get("closed"))
            winner_label, up_price, down_price = self.api.extract_clob_outcome(clob)
            # Write a snapshot using CLOB token prices (Up token price = P(YES))
            spot = self._spot_for(underlying)
            snap = {
                "market_id": cid,
                "ts": ts_now,
                "best_bid": None,          # CLOB /markets doesn't return top-of-book
                "best_ask": None,
                "last_trade_price": up_price,   # use the up-outcome price as proxy
                "volume_24hr": None,
                "closed": 1 if closed else 0,
                "active": 1 if clob.get("active") else 0,
                "spot_price": spot,
            }
            await self.db.insert_snapshot(snap)

            if winner_label:
                lag_s = (ts_now - end_ts) / 1000
                log.info(
                    "RESOLVED clob %s  outcome=%s  lag=%.1fs  %s",
                    underlying or "?", winner_label, lag_s, slug,
                )
                await self.db.upsert_resolution({
                    "market_id": cid,
                    "nominal_end_ts": end_ts,
                    "first_closed_ts": ts_now if closed else None,
                    "resolved_ts": ts_now,
                    "resolution_lag_s": lag_s,
                    "outcome": winner_label,
                    "resolved_cleanly": 1,
                    "notes": None,
                })
                self._resolved_ids.add(cid)
                newly_resolved += 1

        # Give-up sweep: mark markets past the watch window as UNRESOLVED.
        cutoff = now_utc_ms() - POST_EXPIRY_WATCH_S * 1000
        stale = await self.db.fetchall(
            """
            SELECT m.market_id, m.end_ts FROM markets m
            LEFT JOIN resolutions r ON r.market_id = m.market_id
            WHERE m.is_crypto = 1 AND m.end_ts < ? AND r.market_id IS NULL
            LIMIT 100
            """,
            (cutoff,),
        )
        for cid, end_ts in stale:
            if cid in self._resolved_ids:
                continue
            log.warning("UNRESOLVED lag>%ds  cid=%s", POST_EXPIRY_WATCH_S, cid[:12])
            await self.db.upsert_resolution({
                "market_id": cid, "nominal_end_ts": end_ts,
                "first_closed_ts": None, "resolved_ts": None,
                "resolution_lag_s": None, "outcome": "UNRESOLVED",
                "resolved_cleanly": 0,
                "notes": f"no resolution within {POST_EXPIRY_WATCH_S}s",
            })
            self._resolved_ids.add(cid)

        if newly_resolved:
            log.info("resolution pass: newly_resolved=%d tracked_past_expiry=%d",
                     newly_resolved, len(markets))

    async def _sampler_loop(self, name: str, interval_s: float, window_fn) -> None:
        while not self._stop.is_set():
            try:
                now = now_utc_ms()
                lo, hi = window_fn(now)
                markets = await self._tracked_markets_in_window(lo, hi)
                # filter out already-resolved in-memory
                markets = [m for m in markets if m[0] not in self._resolved_ids]
                if markets:
                    await self._bulk_sample(name, markets)
            except asyncio.CancelledError:
                return
            except Exception as e:
                log.exception("%s sampler error: %s", name, e)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval_s)
            except asyncio.TimeoutError:
                pass

    async def _bulk_sample(self, sampler_name: str, markets: list[tuple]) -> None:
        condition_ids = [m[0] for m in markets]
        by_id: dict[str, tuple[int, str | None, str | None]] = {
            m[0]: (m[1], m[2], m[3]) for m in markets
        }
        raws = await self.api.get_markets_bulk(condition_ids)
        ts_now = now_ms()
        resolutions_to_record: list[dict] = []
        for raw in raws:
            cid = raw.get("conditionId") or raw.get("id")
            if not cid or cid not in by_id:
                continue
            end_ts, underlying, slug = by_id[cid]
            n = normalize_market(raw)
            spot = self._spot_for(underlying)
            snap = {
                "market_id": cid,
                "ts": ts_now,
                "best_bid": n.get("best_bid"),
                "best_ask": n.get("best_ask"),
                "last_trade_price": n.get("last_trade_price"),
                "volume_24hr": n.get("volume_24hr"),
                "closed": n.get("closed"),
                "active": n.get("active"),
                "spot_price": spot,
            }
            await self.db.insert_snapshot(snap)

            # Resolution detection
            closed = bool(n.get("closed"))
            outcome_label = _extract_outcome(raw)
            if closed and outcome_label:
                lag_s = (ts_now - end_ts) / 1000
                log.info(
                    "RESOLVED %s %s  outcome=%s  lag=%.1fs  %s",
                    sampler_name, underlying or "?", outcome_label, lag_s, slug,
                )
                resolutions_to_record.append({
                    "market_id": cid,
                    "nominal_end_ts": end_ts,
                    "first_closed_ts": ts_now,
                    "resolved_ts": ts_now,
                    "resolution_lag_s": lag_s,
                    "outcome": outcome_label,
                    "resolved_cleanly": 1,
                    "notes": None,
                })
                self._resolved_ids.add(cid)

        # Resolution detection + UNRESOLVED sweep are handled by `resolution_checker`.
        for r in resolutions_to_record:
            # In practice this won't fire often — gamma rarely returns closed=true — but
            # keep it for the edge case where a market is reported closed before being
            # dropped from the gamma listing.
            await self.db.upsert_resolution(r)

    # ---- run ----

    async def run(self, duration_s: float) -> None:
        start_ts = now_ms()
        await self.db.set_meta("probe_started_at_ms", str(start_ts))
        await self.db.set_meta("probe_duration_s", str(int(duration_s)))

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._stop.set)

        tasks = [
            asyncio.create_task(self.discovery_loop(), name="discovery"),
            asyncio.create_task(self.spot_loop(), name="spot"),
            asyncio.create_task(self.normal_sampler(), name="normal"),
            asyncio.create_task(self.final_sampler(), name="final"),
            asyncio.create_task(self.resolution_checker(), name="resolution"),
        ]

        async def deadline():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=duration_s)
            except asyncio.TimeoutError:
                log.info("duration reached (%ds), stopping", int(duration_s))
                self._stop.set()

        tasks.append(asyncio.create_task(deadline(), name="deadline"))

        await self._stop.wait()
        log.info("shutdown signaled")
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self.db.set_meta("probe_stopped_at_ms", str(now_ms()))


def _extract_outcome(raw: dict) -> str | None:
    """Return 'YES' / 'NO' if the market has a definitive outcome, else None."""
    op = raw.get("outcomePrices")
    if not op:
        return None
    try:
        parsed = op if isinstance(op, list) else json.loads(op)
        outcomes = raw.get("outcomes")
        outcomes_list = outcomes if isinstance(outcomes, list) else (json.loads(outcomes) if outcomes else ["Yes", "No"])
        winners = [label for label, p in zip(outcomes_list, parsed) if float(p) > 0.5]
        if winners:
            return winners[0].upper()
    except Exception:
        return None
    return None


def _fmt_dur(secs: int | None) -> str:
    if not secs:
        return "?"
    if secs < 3600:
        return f"{secs//60}m"
    if secs < 86400:
        return f"{secs//3600}h"
    return f"{secs//86400}d"


async def amain(args) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("ccxt").setLevel(logging.WARNING)

    db = ProbeDB(args.db)
    await db.open()

    session = aiohttp.ClientSession(headers={"User-Agent": "event-impact-probe/0.1"})
    exchange = ccxt.binance({"enableRateLimit": True})
    try:
        probe = Probe(db, session, exchange)
        log.info("probe starting: hours=%s db=%s", args.hours, args.db)
        await probe.run(duration_s=args.hours * 3600)
    finally:
        await exchange.close()
        await session.close()
        await db.close()
        log.info("probe finished")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--hours", type=float, default=24.0)
    p.add_argument("--db", default="probe/probe.db")
    args = p.parse_args()
    asyncio.run(amain(args))


if __name__ == "__main__":
    main()
