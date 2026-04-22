# e17 — Real-time neg-risk arb observer

**Status:** running (launchd agent `com.elliot.polymarket-arb-observer`). No capital at risk — passive measurement only.

## Purpose

Answer **"are neg-risk arbs capturable at our latency tier?"** before spending on VPS or execution infrastructure.

The e15 paper-trader polls gamma-api hourly. That's far too slow to see real arb dynamics — Saguillo 2025 reports median arb duration of 2.7s for general Polymarket arbs. We need millisecond-level observation to know:

1. How many distinct arb events per hour/day on the current Polymarket universe?
2. Median duration (from first tick below 1.0 to first tick back above 1.0)?
3. What fraction are phantoms (sum_asks < 0.05, usually stale-cache artifacts)?
4. What fraction last long enough to be realistically capturable at each latency tier:
   - >10s (easy, even from NZ laptop)
   - 1-10s (VPS territory)
   - 200ms-1s (VPS+basket-execute)
   - <200ms (colocated only — not us)

## How it works

1. **Enumerate universe** via gamma-api: all active GUARANTEED neg-risk events (scanner's classification). Extract YES-token asset_ids.
2. **Subscribe** via `wss://ws-subscriptions-clob.polymarket.com/ws/market` to all those asset_ids.
3. **Receive** initial book snapshots, then streaming `price_changes` deltas.
4. **Maintain** in-memory best-ask per asset. On every delta, recompute sum_asks for each affected event.
5. **Log** to SQLite whenever sum_asks crosses below 1.0 (arb open) and back above (arb close).

Refresh every 30 minutes: exit the process; launchd restarts and re-enumerates the universe to pick up new events.

## Data

`data/observer.db` — SQLite with three tables:

- **`scans`** — one row per universe enumeration. Confirms the collector is alive and shows the size of the tracked universe.
- **`arbs`** — one row per contiguous arb period. Fields: `event_slug`, `started_at`, `ended_at`, `duration_ms`, `min_sum_asks`, `avg_sum_asks`, `max_edge_pct`, `n_legs`, `phantom`.
- **`ticks`** — one row per tick DURING a live arb (for intra-arb dynamics). Skipped outside arb periods to keep DB size modest.

## Quick commands

```bash
# Status
sqlite3 experiments/e17_realtime_arb_observer/data/observer.db "
SELECT
  (SELECT COUNT(*) FROM scans)    AS scans,
  (SELECT COUNT(*) FROM arbs)     AS total_arbs,
  (SELECT COUNT(*) FROM arbs WHERE phantom=0) AS real_arbs,
  (SELECT COUNT(*) FROM arbs WHERE phantom=1) AS phantom_arbs,
  (SELECT ROUND(AVG(duration_ms)) FROM arbs WHERE ended_at IS NOT NULL AND phantom=0) AS avg_duration_ms,
  (SELECT ROUND(MAX(duration_ms)) FROM arbs WHERE phantom=0) AS max_duration_ms;
"

# Duration distribution by latency bucket
sqlite3 experiments/e17_realtime_arb_observer/data/observer.db "
SELECT
  CASE
    WHEN duration_ms < 200 THEN '<200ms (colo-only)'
    WHEN duration_ms < 1000 THEN '200ms-1s (VPS+basket)'
    WHEN duration_ms < 10000 THEN '1-10s (VPS)'
    ELSE '>10s (laptop-ok)'
  END AS bucket,
  COUNT(*) AS n,
  ROUND(AVG(max_edge_pct), 2) AS avg_edge_pct
FROM arbs
WHERE phantom=0 AND ended_at IS NOT NULL
GROUP BY bucket;
"

# Recent arbs (live tail)
tail -f experiments/e17_realtime_arb_observer/data/observer.log
```

## Decision gate

After 24-48 hours of data:

| finding | next step |
|---|---|
| >50% of real arbs last >1s | VPS is worth $6/mo — go to Phase 3 of [PLAN_FAST_BOT](../../docs/PLAN_FAST_BOT.md) |
| 10-50% last >1s | VPS marginal; focus on Q3 long-duration (>1h) arbs only |
| <10% last >1s | Skip bot entirely — all the edge goes to colo bots; pursue the e16 calibration strategy instead |

## Relation to PLAN_FAST_BOT.md

This is Phase 2 of the 5-phase plan. Phase 1 (phantom filter) is complete. Phase 3-5 only proceed if Phase 2 data justifies it.

## Known limitations

1. **Best-ask approximation.** `observer.py` tracks `best_ask` as a scalar per asset, not a full ask-level ladder. When a best-ask level clears to 0 size, we drop that asset's best-ask to None until the next book snapshot. This can miss brief arbs (<1s) during book-refresh gaps. For macro shape it's fine; for full precision we'd need full-depth tracking.
2. **1000-asset subscription cap.** Polymarket may have limits on WSS subscription list size. `--max-assets 1000` is defensive; if we see no data we'd lower. Currently: 111 GUARANTEED events × ~9 children each = 1000+ assets, so the cap sometimes bites.
3. **Universe refresh every 30min.** If a new hot event appears between refreshes, we miss it. Could drop to 5-10min refresh; costs are tiny, just more universe-enumeration calls to gamma.
