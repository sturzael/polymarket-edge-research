"""Produce venue-viability metrics for Drift prediction markets.

Outputs printed to stdout + saved to data/venue_profile.json.

Metrics:
- total markets by category
- volume distribution (total, median, p90 per market)
- average trading activity (trades/day during active life)
- depth: hourly $ traded median/max
- market duration distribution
- fraction of markets with >$10k volume, >$100k, >$1M
- time-series: new markets per quarter
"""
from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).parent.parent
DATA = HERE / "data"
CDIR = DATA / "candles"


def classify_category(symbol: str) -> str:
    s = symbol.upper()
    if any(x in s for x in ("F1", "SUPERBOWL", "NBAFINALS", "FIGHT")):
        return "sports"
    if any(x in s for x in ("TRUMP", "KAMALA", "REPUBLICAN", "DEMOCRATS", "MICHIGAN")):
        return "politics"
    if "FED" in s:
        return "economics"
    if "WLF" in s or "BREAKPOINT" in s:
        return "crypto_events"
    return "other"


def main() -> None:
    all_markets = json.load(open(DATA / "all_markets.json"))["markets"]
    bets = [m for m in all_markets if m["symbol"].endswith("-BET")]
    ml = {r["symbol"]: r for r in json.load(open(DATA / "market_level.json"))}

    rows = []
    for m in bets:
        sym = m["symbol"]
        recs = json.load(open(CDIR / f"{sym}.json"))
        mlrec = ml.get(sym, {})

        with_vol = [r for r in recs if float(r.get("quoteVolume") or 0) > 0]
        if not with_vol:
            continue

        hour_vols = [float(r.get("quoteVolume") or 0) for r in with_vol]
        total_qv = sum(hour_vols)
        n_active_hours = len(with_vol)
        first_ts = with_vol[0]["ts"]
        last_ts = with_vol[-1]["ts"]
        duration_days = (last_ts - first_ts) / 86400.0
        avg_qv_per_active_hour = total_qv / n_active_hours if n_active_hours else 0
        avg_qv_per_day = total_qv / duration_days if duration_days > 0 else 0

        # Hourly volume percentiles
        hour_vols_sorted = sorted(hour_vols)
        p50 = hour_vols_sorted[len(hour_vols_sorted) // 2]
        p90 = hour_vols_sorted[int(len(hour_vols_sorted) * 0.9)]
        p99 = hour_vols_sorted[int(len(hour_vols_sorted) * 0.99)] if len(hour_vols_sorted) >= 100 else max(hour_vols_sorted)
        p_max = max(hour_vols_sorted)

        # Did it actually get listed well before the event? (we care about
        # whether bettors have multi-day arrival)
        rows.append({
            "symbol": sym,
            "category": classify_category(sym),
            "outcome": mlrec.get("outcome"),
            "first_trade": datetime.fromtimestamp(first_ts, tz=timezone.utc).strftime("%Y-%m-%d"),
            "last_trade": datetime.fromtimestamp(last_ts, tz=timezone.utc).strftime("%Y-%m-%d"),
            "trading_days": round(duration_days, 1),
            "total_volume_usd": round(total_qv, 2),
            "active_hours": n_active_hours,
            "avg_hourly_vol_active": round(avg_qv_per_active_hour, 2),
            "avg_daily_vol": round(avg_qv_per_day, 2),
            "hourly_vol_p50": round(p50, 4),
            "hourly_vol_p90": round(p90, 2),
            "hourly_vol_p99": round(p99, 2),
            "hourly_vol_max": round(p_max, 2),
        })

    # Sort by total volume desc
    rows.sort(key=lambda r: -r["total_volume_usd"])

    print("=== DRIFT PREDICTION MARKET VENUE PROFILE ===\n")
    print(f"Total -BET markets: {len(rows)}")

    # Category breakdown
    cats: dict[str, list] = {}
    for r in rows:
        cats.setdefault(r["category"], []).append(r)
    print("\nBy category:")
    for c, rs in sorted(cats.items(), key=lambda x: -sum(r["total_volume_usd"] for r in x[1])):
        tv = sum(r["total_volume_usd"] for r in rs)
        print(f"  {c:<15} n={len(rs)}  total_vol=${tv:,.0f}  median_vol=${statistics.median([r['total_volume_usd'] for r in rs]):,.0f}")

    # Volume distribution thresholds
    vols = [r["total_volume_usd"] for r in rows]
    n_10k = sum(1 for v in vols if v >= 10_000)
    n_100k = sum(1 for v in vols if v >= 100_000)
    n_1m = sum(1 for v in vols if v >= 1_000_000)
    print(f"\nVolume thresholds (per-market lifetime):")
    print(f"  >=$10k:   {n_10k}/{len(rows)} ({100*n_10k/len(rows):.0f}%)")
    print(f"  >=$100k:  {n_100k}/{len(rows)} ({100*n_100k/len(rows):.0f}%)")
    print(f"  >=$1M:    {n_1m}/{len(rows)} ({100*n_1m/len(rows):.0f}%)")
    print(f"  total:    ${sum(vols):,.0f}")
    print(f"  median:   ${statistics.median(vols):,.0f}")
    print(f"  mean:     ${statistics.mean(vols):,.0f}")

    # Hourly-depth distribution (median-of-medians & p90-of-p90s)
    all_p50s = [r["hourly_vol_p50"] for r in rows]
    all_p90s = [r["hourly_vol_p90"] for r in rows]
    all_maxes = [r["hourly_vol_max"] for r in rows]
    print(f"\nHourly-volume depth (across markets):")
    print(f"  median of per-market p50 hourly volume: ${statistics.median(all_p50s):.2f}")
    print(f"  median of per-market p90 hourly volume: ${statistics.median(all_p90s):.2f}")
    print(f"  median of per-market max hourly volume: ${statistics.median(all_maxes):,.0f}")

    # Full per-market table
    print("\nPer-market:")
    print(f"  {'symbol':<36} {'cat':<14} {'days':>5} {'total_qv':>12} {'avg_daily':>10} {'max_hr':>10}  outcome")
    for r in rows:
        print(f"  {r['symbol']:<36} {r['category']:<14} {r['trading_days']:>5.1f} "
              f"${r['total_volume_usd']:>11,.0f} ${r['avg_daily_vol']:>9,.0f} "
              f"${r['hourly_vol_max']:>9,.0f}  {r['outcome']}")

    # New markets per quarter
    buckets: dict[str, int] = {}
    for r in rows:
        dt = datetime.strptime(r["first_trade"], "%Y-%m-%d")
        q = f"{dt.year}Q{(dt.month-1)//3 + 1}"
        buckets[q] = buckets.get(q, 0) + 1
    print("\nNew -BET markets by quarter:")
    for q in sorted(buckets):
        print(f"  {q}: {buckets[q]}")

    json.dump({
        "n_total": len(rows),
        "by_category": {c: len(rs) for c, rs in cats.items()},
        "total_lifetime_volume_usd": round(sum(vols), 2),
        "markets_over_10k": n_10k,
        "markets_over_100k": n_100k,
        "markets_over_1m": n_1m,
        "new_by_quarter": buckets,
        "markets": rows,
    }, open(DATA / "venue_profile.json", "w"), indent=2)
    print(f"\nWrote {DATA / 'venue_profile.json'}")


if __name__ == "__main__":
    main()
