# Agent C — Volume stratification of Polymarket sports FLB

**Status:** Complete. Sandbox blocked direct MD writes by the agent; parent session persisted.
**Date:** 2026-04-20

## Bottom line

**The sports FLB is NOT a liquidity artifact. It is concentrated in — and *larger* in — the highest-volume tier.** Tradable subject to Agent F's execution-quality check.

## Key numbers (2,025-market sports T-7d sample, ±12h window)

Sample-wide 0.55-0.60 bucket: **n=120, yes_rate 0.833, deviation +0.258.**

| tier | window $ | n markets | share | n in 0.55-0.60 | % of bucket | yes_rate | deviation | sufficient? |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | <$500 | 398 | 19.7% | 16 | 13.3% | 0.688 | +0.112 | **insufficient** |
| 2 | $500-$5k | 205 | 10.1% | 6 | 5.0% | 0.500 | −0.075 | **insufficient** |
| 3 | ≥$5k | 1,422 | 70.2% | **98** | **81.7%** | **0.878** | **+0.303** | yes |

## Tradability percentiles per tier (`max_single_trade_usd`)

| tier | p50 | p75 | p90 | p99 |
|---|---:|---:|---:|---:|
| 1 <$500 | $44 | $113 | $194 | $405 |
| 2 $500-$5k | $570 | $1,124 | $2,019 | $3,996 |
| 3 ≥$5k | $9,040 | $22,862 | $65,997 | $205,023 |

`median_trade_usd` is small across all tiers ($5-$15 p50) — Tier 3's capacity comes from occasional large taker prints inside dense retail flow. Marketable limits should be able to fill real size without being the only taker.

## Calibration tables

### Tier 1 — <$500 (n=398)
```
bucket        n   mid  yes_rate     dev
0.00-0.05   106 0.025   0.019   -0.006
0.05-0.10    22 0.075   0.045   -0.030
0.10-0.15    21 0.125   0.048   -0.077
0.15-0.20    16 0.175   0.250   +0.075
0.20-0.25    24 0.225   0.208   -0.017
0.25-0.30    28 0.275   0.107   -0.168
0.30-0.35    17 0.325   0.294   -0.031
0.35-0.40    27 0.375   0.481   +0.106
0.40-0.45    15 0.425   0.333   -0.092
0.45-0.50    17 0.475   0.529   +0.054
0.50-0.55    14 0.525   0.571   +0.046
0.55-0.60    16 0.575   0.688   +0.112   <-- FOCUS (insufficient)
0.60-0.65    17 0.625   0.588   -0.037
0.65-0.70    14 0.675   0.786   +0.111
0.70-0.75    13 0.725   0.769   +0.044
0.75-0.80     8 0.775   0.875   +0.100
0.80-0.85     9 0.825   1.000   +0.175
```

### Tier 2 — $500-$5k (n=205)
```
bucket        n   mid  yes_rate     dev
0.00-0.05    49 0.025   0.000   -0.025
0.05-0.10     9 0.075   0.000   -0.075
0.25-0.30    16 0.275   0.250   -0.025
0.30-0.35    12 0.325   0.083   -0.242
0.40-0.45    12 0.425   0.333   -0.092
0.45-0.50     9 0.475   0.444   -0.031
0.50-0.55    16 0.525   0.625   +0.100
0.55-0.60     6 0.575   0.500   -0.075   <-- FOCUS (insufficient)
0.60-0.65     5 0.625   0.600   -0.025
0.65-0.70     7 0.675   0.714   +0.039
0.70-0.75     9 0.725   0.778   +0.053
0.75-0.80     8 0.775   1.000   +0.225
```

### Tier 3 — ≥$5k (n=1,422)
```
bucket        n   mid  yes_rate     dev
0.00-0.05   100 0.025   0.000   -0.025
0.05-0.10    35 0.075   0.000   -0.075
0.10-0.15    46 0.125   0.000   -0.125
0.15-0.20    67 0.175   0.015   -0.160
0.20-0.25    71 0.225   0.056   -0.169
0.25-0.30    86 0.275   0.023   -0.252
0.30-0.35   102 0.325   0.098   -0.227
0.35-0.40    98 0.375   0.102   -0.273
0.40-0.45   107 0.425   0.252   -0.173
0.45-0.50   105 0.475   0.476   +0.001
0.50-0.55    70 0.525   0.657   +0.132
0.55-0.60    98 0.575   0.878   +0.303   <-- FOCUS (sufficient, Wilson 95% ~[0.80, 0.93])
0.60-0.65   112 0.625   0.839   +0.214
0.65-0.70    81 0.675   0.963   +0.288
0.70-0.75    69 0.725   0.971   +0.246
0.75-0.80    53 0.775   0.981   +0.206
0.80-0.85    51 0.825   1.000   +0.175
0.85-0.90    34 0.875   1.000   +0.125
```

## Cross-tier interpretation

1. **Headline FLB does not come from illiquid markets.** <$500 tier holds 16/120 (13.3%) of focus-bucket markets and shows +11.2pp — *smaller* than pooled +25.8pp. Removing Tier 1 entirely would widen, not shrink, the bias.
2. **FLB is largest in the highest-volume tier.** ≥$5k tier holds 81.7% of focus-bucket markets and shows **+30.3pp**, above the pooled figure. Opposite of a liquidity-artifact signature.
3. **Tier 3 absorbs real size.** Median max_single_trade_usd $9,040; p90 $66k. The FLB is observable in markets where $5-50k clips have actually transacted at T-7d ±12h.
4. **Tier 2 is statistical noise** (n=6 in focus bucket). The apparent −7.5pp reversal is not interpretable.

**Correlation(price_tm7d, yes) per tier:** Tier 1 = 0.42, Tier 2 = 0.67, Tier 3 = 0.76. Signal strengthens with volume — inconsistent with liquidity-artifact hypothesis.

## Methodology notes

- **Stratification variable: `total_usd_window`** (the ±12h window around T-7d), not lifetime `volume`. Lifetime conflates closing-window settle flow with T-7d order flow; window-volume is the correct proxy for "can this be entered at T-7d?".
- **Tier cutoffs at $500 and $5k** per brief. These map to roughly p25 and p50-55 of `total_usd_window` (p25 ≈ $1.9k, p50 ≈ $23k).
- **Insufficient-sample flag at n<20** applied to focus bucket.
- **Tradability metrics as percentiles of `max_single_trade_usd`** (distribution is right-skewed; mean would mislead).
- **Fractions sum to 100%** across tiers (13.3 + 5.0 + 81.7 = 100.0) — no markets lost.

Analysis script: `analyze_volume.py`. Structured output: `data/volume_calibration.json`.
