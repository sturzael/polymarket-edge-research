# e8 — Week-long passive book-watcher

**Purpose:** answer the "is there room to quote at all" question without deploying capital or a backtest. Cheap-to-run prerequisite before the properly-scoped MM backtest.

## What it does

- Every 30 minutes, discovers up to 10 balanced-probability crypto `above-K` markets (last_trade ∈ [0.2, 0.8], end in 6-48h).
- Every 15 seconds, snapshots each target's book (via CLOB `/book`) + BTC/ETH/SOL spot (via ccxt Binance).
- For each snapshot records: `best_bid/ask, rational_bid/ask (ignoring penny stubs), depth_notional, spot, ttm, GBM fair value, mm_present` flag (1 if some rational quote is within ±5¢ of fair value).
- Hourly prints a summary: `% of snapshots with MM inside ±5¢ of fair value` — this answers the density question directly.

## The question it's designed to kill

If 95%+ of snapshots show an MM already quoting within ±5¢ of fair value, the "we'd be the tight quote" premise is wrong and the backtest is moot. If 30-60% of snapshots have no rational quote near fair value, there's real room for us to be first.

## How to run

Requires user approval for the week-long background spawn. Not launched autonomously.

```
cd ~/dev/event-impact-mvp
nohup uv run python experiments/e8_week_watcher/watcher.py --hours 168 > experiments/e8_week_watcher/watcher.log 2>&1 & disown
```

Shorter smoke first (24h) recommended:
```
nohup uv run python experiments/e8_week_watcher/watcher.py --hours 24 > experiments/e8_week_watcher/watcher.log 2>&1 & disown
```

Status check: `tail -f experiments/e8_week_watcher/watcher.log` or query `watcher.db` directly.

## Expected output

By end of 1 week:
- ~40,320 snapshots × 10 markets = ~400k rows in `snapshots`
- Hour-bucketed summary: what % of time did we have a "room to quote" window?
- Distribution of `rational_ask - rational_bid` over time
- Coverage pattern: some markets may have persistent MM presence, others never

## Decision rule post-watcher

- If `mm_present` rate averages >80% → **kill the MM strategy**; the niche is already covered
- If `mm_present` rate averages 20-50% → **proceed to backtest**; there's real room at least half the time
- If `mm_present` rate averages <20% → **strong signal, accelerate backtest**

## Resource cost

~5 req/s HTTP load (well under limits). ~50 MB/week of SQLite. Runs on a laptop or cheap VPS. No monitoring required.

## Known limits (intentional)

- Only BTC/ETH/SOL — skips XRP/DOGE/BNB to keep target count low
- Only `above-K` (digitals) — skips barrier markets (they're a separate strategy)
- GBM fair value uses hard-coded 50% annualized vol — noisy but OK for detecting "is there an MM near fair value at all"; a better version would pull IV from Deribit hourly
- No execution simulation — this is density measurement, not backtest
