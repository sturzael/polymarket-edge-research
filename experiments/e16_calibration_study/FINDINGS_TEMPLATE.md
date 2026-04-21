# e16 — Category calibration + weather viability

**Status:** TEMPLATE. Fill in from `03_calibration_table.json` + `weather_viability.json` once streams finish.

## 1. Weather market viability — SKIP

**Verdict: SKIP** (fails thresholds).

47 genuinely-weather active markets (v2 tight filter); overall median volume $1,987 (below $10k threshold). Cadence 100% "one-off" after excluding false-positive sport/politics matches containing "hurricane"/"storm". Resolved markets close on median 2.3 days after creation — fast resolution, but total active weather pool is ~$1M, dominated by 3 hurricane-season markets ($132k–$332k).

No daily-cadence weather vertical exists at scale on Polymarket right now. Weather is a small niche with a handful of deep one-off bets; doesn't unlock the bankroll-scale math for a $5k operator.

**Not reopenable without** a structural change in Polymarket offerings (e.g., daily NYC/LA temperature-bucket markets at $10k+ each).

## 2. Category calibration study

**Method.** For 581,240 resolved markets in SII's `markets.parquet`:
1. Derived category from slug/question pattern matching (20 heuristic categories)
2. Streamed all 954M orderfilled rows across 4 parquet parts (parallel)
3. For each market, computed 7-day-pre-close VWAP as "implied probability at resolution"
4. Filtered to markets with ≥3 trades in that window (stable VWAP)
5. Aggregated by (category × 5pp bucket) — computed empirical YES rate vs bucket midpoint

### Summary table

*To fill from `03_calibration_table.json`.*

```
bucket      n      mid    yes_rate   deviation
0.00-0.05   ?      0.025  ?          ?
0.05-0.10   ?      0.075  ?          ?
...
```

### Actionable signals (n≥30, |deviation| > 5pp)

*To fill from `top_actionable_cells` in the JSON.* For each cell:
- category
- bucket (price range)
- n (observations)
- yes_rate (empirical)
- deviation (empirical − midpoint)
- total_volume (liquidity in this cell)
- interpretation (over/under-priced, by how much, tradeable size)

### Category-level YES-rate vs mean-price summary

*To fill.* Categories where `yes_rate_overall ≠ mean_price_overall` indicate systematic category-level miscalibration.

## 3. Interpretation & recommendations

### Are there exploitable miscalibrations?

*To answer:*

- If any (category × bucket) cell has |deviation| > 5pp with n ≥ 30 AND total_volume > $100k, that's a candidate trading signal.
- Signals that persist across many buckets within a category (not just one) are more robust.
- Signals concentrated in one outlier bucket may be artifacts (small n, selection effects, bucket-boundary noise).

### Structural caveats (read before trading)

1. **7-day VWAP ≠ entry price at trade time.** If a signal says "5-10% priced markets resolve YES 12% of the time," you need to verify you can actually BUY at ≤10% — real-time bid/ask may be narrower than the 7-day mean.
2. **Category-level YES rates are dominated by market structure**, not pricing. F1 markets are 10.5% YES because they're "will driver X win this race?" with 20 drivers — 19 markets lose for each race. Not mispricing.
3. **Bucketing by pre-close VWAP anchors the signal to "market just before it resolves"** — that's when the market is most confident. Earlier-market calibration may differ.

### Recommended next step

*Based on findings:*

- **If strong signal found** (|dev| > 10pp, n > 100, cross-bucket): build a scanner that finds live markets within the identified category × bucket, enter positions, track forward resolution. Compare live performance to historical calibration.
- **If mild signals only** (|dev| 5-10pp): document and move on. Not enough edge at $5k sizing.
- **If no signal found**: matches the efficient-market null from the project postscript. Confirms Polymarket is well-calibrated in the aggregate.

## 4. Deliverables

- `data/01_markets_audit.parquet` — 581k resolved markets with category + resolution
- `data/02_prices_part{1..4}.parquet` — per-market 7-day pre-close VWAP
- `data/03_calibration.parquet` — joined (market, category, VWAP, bucket, resolution)
- `data/03_calibration_table.json` — aggregated table for reporting
- `data/weather_viability.json` — weather market scan
