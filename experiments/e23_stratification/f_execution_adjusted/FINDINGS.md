# Agent F — Execution-adjusted edge + deployment math

**Status:** Complete. Sandbox blocked FINDINGS.md; VERDICT.md and DECISIONS.md wrote fine. Parent persisted this file.
**Date:** 2026-04-20

## TL;DR

Applying realistic execution friction to the e16-measured **+25.8pp raw edge** at the 0.55-0.60 T-7d sports bucket leaves:
- **+23.8pp net edge at the expected operating cell** ($500, 3 bps, one-sided fee model)
- Fill probability at $500: ~71% → expected edge per qualifying bet **+16.9pp**
- At 17.5 bets/month × $500: **$17-21k/yr net-adjusted P&L on $5-10k capital**
- Conservative ÷5 planning scenario: **$4.3k/yr on $5k (85% annualized)**

**Fees are a rounding error** (<0.4pp even at 15bps V2-worst-case). Binding frictions are **slippage** and **fill probability**.

**Recommendation: small live test ($500-$1000 sanity), NOT full deployment** — pending Agent A/E filtering and the e16-prescribed 30-day forward validation.

## Measured inputs (e16 sports-deep parquet, n=120 in 0.55-0.60)

- raw edge **+25.8pp**, yes_rate 0.833, z=7.6
- median_trade_usd p50 = **$20** (typical single print)
- max_single_trade_usd p50 = **$9,086**, p25 = $1,993
- total_usd_window p50 = **$60,791**
- fraction with max_single ≥ $200 / $500 / $1000 / $2000: **86.7% / 83.3% / 80.0% / 74.2%**

### Per-category breakdown inside 0.55-0.60 bucket

| category | n | yes_rate | median max-single-trade |
|---|---:|---:|---:|
| sports_mlb | 54 | 0.944 | $12,949 |
| sports_nba | 19 | 0.737 | $13,304 |
| sports_nfl | 8 | 0.875 | $2,116 |
| sports_nhl | 11 | 0.909 | $8,821 |
| sports_ufc_boxing | 9 | 0.667 | $791 |
| sports_soccer | 6 | 0.667 | $95 |
| sports_tennis | 11 | 0.636 | $377 |
| sports_f1 | 2 | 0.500 | $82,224 |

**MLB / NBA / NFL / NHL** combine strong yes_rate with usable depth. **Tennis, UFC, soccer, F1** are thin + lower yes_rate — gate OFF until Agent A confirms significance.

## Matrix 1 — Net edge after all friction (one-sided fees, buy-and-hold)

| order size | 0 bps | **3 bps (sports)** | 7.2 bps | 15 bps (V2 worst) |
|---:|---:|---:|---:|---:|
| $200 | +24.44 | **+24.43** | +24.42 | +24.40 |
| $500 | +23.84 | **+23.83** (operating cell) | +23.82 | +23.80 |
| $1,000 | +22.84 | **+22.83** | +22.82 | +22.80 |
| $2,000 | +20.84 | **+20.83** | +20.82 | +20.80 |

- **V2 fee hike is a non-issue** — 15bps worst-case costs only 0.04pp more than 3bps
- **Slippage dominates**: 4pp swing between $200 and $2,000 sizes
- Two-sided fee model (exit before resolution) drops net edge by <0.1pp more

Spread sensitivity at $500/3bps: tight book (0.5pp half-spread) +24.3pp / central +23.8pp / wide (1.5pp) +23.3pp.

## Matrix 2 — Capital deployment (annualized $)

Sizing: `pos = clip($200, capital/(concurrent×2), $2000)`, concurrent=4.08.

| capital | pos size | fill prob | net edge | Raw | Net-adj | ÷2 | ÷3 | **÷5 (plan)** |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| $5k | $610 | 0.706 | +23.68pp | $23.3k (466%) | $21.3k (426%) | $10.7k (213%) | $7.1k (142%) | **$4.3k (85%)** |
| $10k | $1,220 | 0.668 | +22.46pp | $44.4k (444%) | $38.5k (385%) | $19.3k (193%) | $12.8k (128%) | **$7.7k (77%)** |
| $25k | $2,000 | 0.630 | +20.83pp | $68.3k (273%) | $55.2k (221%) | $27.6k (110%) | $18.4k (74%) | **$11.0k (44%)** |
| $50k | $2,000 | 0.630 | +20.83pp | $68.3k (137%) | $55.2k (110%) | $27.6k (55%) | $18.4k (37%) | **$11.0k (22%)** |

**Capacity saturates at ~$25k** — above that, adding capital doesn't add P&L (position size caps at $2,000 to avoid runaway slippage).

## Matrix 3 — Fill probability × size (at 3 bps, expected operating fees)

| order size | ceiling (empirical) | fill prob (×0.85) | net edge pp | **E[P&L per bet] $** | pct of notional |
|---:|---:|---:|---:|---:|---:|
| $200 | 86.7% | 0.737 | +24.43pp | **+$36.00** | +18.0% |
| $500 | 83.3% | 0.708 | +23.83pp | **+$84.41** | +16.9% |
| $1,000 | 80.0% | 0.680 | +22.83pp | **+$155.26** | +15.5% |
| $2,000 | 74.2% | 0.630 | +20.83pp | **+$262.67** | +13.1% |

Per-notional efficiency drops from 18.0% → 13.1% across size range; absolute $ P&L per bet grows monotonically (7× from $200 to $2,000).

## Final recommendation — Small live test ($500-$1000), NOT full deployment

### Constraints

1. **Sports filter: MLB / NBA / NFL / NHL only.** Gate OFF tennis, UFC, soccer, F1 pending Agent A.
2. **Sub-category filter:** game_outcome only per Agent E. Don't enable sub-categories with n<20 in-bucket.
3. **Order-size cap: $500 entry, $1,000 max position.** Above $1k slippage dominates and fill prob drops <68%.
4. **No fee gating needed.** Even 15bps V2-worst is 0.37pp — immaterial.
5. **Capital: $5k-$15k initial.** Scale past $25k only after 30+ live trades confirm edge persists. Do NOT scale past $50k — capacity saturates.
6. **Kill gates:**
   - Realized yes_rate <0.72 over rolling 30-bet window → halt
   - Realized slippage >3pp per $500 → halt, re-measure
   - V2 cutover (2026-04-22) causing structural shift → halt until 20 post-cutover samples
7. **Forward validation still required.** Small live test is not a substitute for e16's 30-day passive observe.

### Honest decision numbers

- Best plausible (net-adjusted, no correction): $21k/yr on $5k
- Moderate discount (÷3): $7k/yr on $5k
- Conservative (÷5, the planning number): **$4.3k/yr on $5k (85% annualized)**
- Only breaks even at >6× discount (edge is artifact)

## What this does NOT claim

- Does not claim +25.8pp persists forward (historical only; forward validation unresolved)
- Does not claim per-sport breakdown inside 0.55-0.60 is statistically robust (Agent A's job — confirmed MLB passes, others too thin)
- Does not claim slippage model is validated — 1pp/$500 heuristic needs real order-book sampling
- Does not claim capacity extends above $50k

## Reference files

- `compute.py` — full pipeline (reproduces everything)
- `data/net_edge_matrix.json` — Matrix 1, both fee models
- `data/capital_deployment.json` — Matrix 2 with correction factors
- `data/fill_probability_matrix.json` — Matrix 3
- `data/bucket_depth_stats.json` — per-category + depth stats
- `data/fee_model_comparison.json` — one-sided vs two-sided sensitivity
