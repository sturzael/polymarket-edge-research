"""Sense-check funding-rate arbitrage viability at retail scale.

Pulls (a) current funding rates for BTC/ETH/SOL perps on Binance, (b) 90-day
funding-rate history for BTC and ETH, (c) live spot vs perp basis.

Purpose: before pitching funding-rate arb as a viable strategy, verify that
current funding rates + historical distribution actually support a profitable
cash-and-carry after realistic fees. See README.md for the negative result.

Run: uv run python experiments/e11_funding_arb_sensecheck/probe.py
"""
from __future__ import annotations

import asyncio
import statistics
from datetime import datetime, timedelta, timezone

import ccxt.async_support as ccxt


async def probe() -> None:
    perp = ccxt.binance({"enableRateLimit": True, "options": {"defaultType": "future"}})
    spot = ccxt.binance({"enableRateLimit": True})
    try:
        await perp.load_markets()
        await spot.load_markets()

        # --- current snapshot ---
        print("=" * 90)
        print("CURRENT funding rate (snapshot):")
        print(f"{'symbol':<18} {'next_funding':<22} {'rate_8h':>10} {'ann_APY':>10} {'mark':>12}")
        for s in ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]:
            fr = await perp.fetch_funding_rate(s)
            ts = datetime.fromtimestamp(fr["fundingTimestamp"] / 1000, tz=timezone.utc)
            rate = fr["fundingRate"]
            apy = rate * 3 * 365 * 100  # 3 funding periods/day
            print(f"{s:<18} {str(ts):<22} {rate * 100:>9.4f}% {apy:>8.1f}% {fr['markPrice']:>11,.2f}")

        # --- historical 90-day ---
        for symbol in ["BTC/USDT:USDT", "ETH/USDT:USDT"]:
            print(f"\n{'=' * 90}\nHISTORICAL funding rate (90 days, Binance {symbol}):")
            since_ms = int((datetime.now(tz=timezone.utc) - timedelta(days=90)).timestamp() * 1000)
            history: list[dict] = []
            cursor = since_ms
            for _ in range(20):
                batch = await perp.fetch_funding_rate_history(symbol, since=cursor, limit=1000)
                if not batch:
                    break
                history.extend(batch)
                cursor = batch[-1]["timestamp"] + 1
                if len(batch) < 1000:
                    break

            rates = [h["fundingRate"] for h in history if h.get("fundingRate") is not None]
            if not rates:
                print("  no data")
                continue

            pos = sum(1 for r in rates if r > 0)
            neg = sum(1 for r in rates if r < 0)
            mean_r = statistics.mean(rates)
            median_r = statistics.median(rates)
            srates = sorted(rates)
            p10 = srates[len(srates) // 10]
            p90 = srates[9 * len(srates) // 10]

            print(f"  n={len(rates)} funding periods (8h each, expect ~270 over 90d)")
            print(f"  positive: {pos}/{len(rates)} ({100 * pos / len(rates):.1f}%)  "
                  f"negative: {neg}/{len(rates)} ({100 * neg / len(rates):.1f}%)")
            print(f"  mean:    {mean_r * 100:>9.5f}% /8h  → ann APY {mean_r * 3 * 365 * 100:>+6.2f}%")
            print(f"  median:  {median_r * 100:>9.5f}% /8h  → ann APY {median_r * 3 * 365 * 100:>+6.2f}%")
            print(f"  p10:     {p10 * 100:>9.5f}% /8h  → ann APY {p10 * 3 * 365 * 100:>+6.2f}%")
            print(f"  p90:     {p90 * 100:>9.5f}% /8h  → ann APY {p90 * 3 * 365 * 100:>+6.2f}%")
            print(f"  max/min: {max(rates) * 100:.4f}% / {min(rates) * 100:.4f}%")

        # --- spot-perp basis live ---
        print(f"\n{'=' * 90}\nSPOT vs PERP basis (live snapshot):")
        for base in ["BTC/USDT", "ETH/USDT", "SOL/USDT"]:
            spot_t = await spot.fetch_ticker(base)
            perp_t = await perp.fetch_ticker(f"{base}:USDT")
            # some tickers have None bid/ask during thin moments — fall back to last
            def mid(t: dict) -> float | None:
                b, a = t.get("bid"), t.get("ask")
                if b and a:
                    return (b + a) / 2
                return t.get("last") or t.get("close")

            s_mid, p_mid = mid(spot_t), mid(perp_t)
            if s_mid and p_mid:
                basis_pct = 100 * (p_mid - s_mid) / s_mid
                print(f"  {base:<12} spot={s_mid:>12,.2f}  perp={p_mid:>12,.2f}  basis={basis_pct:+.4f}%")
            else:
                print(f"  {base:<12} no mid available")

    finally:
        await perp.close()
        await spot.close()


if __name__ == "__main__":
    asyncio.run(probe())
