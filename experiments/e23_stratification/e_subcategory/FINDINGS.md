# Agent E — Sports FLB by sub-category (T-7d)

**Status:** Complete. Sandbox blocked direct MD writes; parent persisted.
**Date:** 2026-04-20
**Source:** `experiments/e16_calibration_study/data/05_tm7d_prices_sports_deep.parquet` (n=2,025).

## TL;DR

The +25.8pp sports FLB at 0.55-0.60 lives **essentially entirely inside game_outcome** (head-to-head team/player matches on a single date). In the critical bucket:

| sub-category | n at 0.55-0.60 | yes_rate | deviation | note |
|---|---:|---:|---:|---|
| **game_outcome** | **113** | **0.850** | **+0.275** | drives the sport-level FLB |
| futures | 5 | 0.400 | −0.175 | opposite sign; n too small |
| props | 0 | — | — | structurally empty |
| totals | 0 | — | — | no samples |
| spreads | 2 | 1.000 | +0.425 | n=2, noise |
| uncategorized | 2 | 1.000 | +0.425 | n=2 |

## Sub-category counts

| sub-category | n | % |
|---|---:|---:|
| game_outcome | 1,667 | 82.3% |
| props | 173 | 8.5% |
| futures | 144 | 7.1% |
| totals | 21 | 1.0% |
| spreads | 16 | 0.8% |
| uncategorized | 4 | 0.2% |

## Sport × sub-category cross-tab

| sport | futures | game_outcome | props | spreads | totals | uncat |
|---|---:|---:|---:|---:|---:|---:|
| F1 | 15 | 108 | **133** | 0 | 0 | 0 |
| MLB | 4 | **460** | 1 | 0 | 0 | 0 |
| NBA | 23 | **309** | 1 | 0 | 0 | 3 |
| NFL | 33 | 97 | 26 | 5 | 4 | 1 |
| NHL | 5 | **231** | 0 | 0 | 1 | 0 |
| Soccer | 20 | 95 | 2 | 2 | 7 | 0 |
| Tennis | 44 | **235** | 4 | 9 | 9 | 0 |
| UFC/Boxing | 0 | **132** | 6 | 0 | 0 | 0 |

Notable: F1 is props-heavy (pole/podium/constructor); NFL is futures-heavy (awards/draft/division); MLB/NHL are almost pure game_outcome; tennis has ~15% futures (slam winners) on top of h2h matches.

## game_outcome calibration (n=1,667) — S-curve with classic FLB

| bucket | n | mid | yes_rate | dev |
|---|---:|---:|---:|---:|
| 0.25-0.30 | 118 | 0.275 | 0.068 | −0.207 |
| 0.30-0.35 | 121 | 0.325 | 0.116 | −0.209 |
| 0.35-0.40 | 125 | 0.375 | 0.184 | −0.191 |
| 0.40-0.45 | 124 | 0.425 | 0.250 | −0.175 |
| 0.45-0.50 | 118 | 0.475 | 0.483 | +0.008 |
| 0.50-0.55 | 91 | 0.525 | 0.626 | +0.101 |
| **0.55-0.60** | **113** | **0.575** | **0.850** | **+0.275** |
| 0.60-0.65 | 128 | 0.625 | 0.812 | +0.188 |
| 0.65-0.70 | 95 | 0.675 | 0.937 | +0.262 |
| 0.70-0.75 | 88 | 0.725 | 0.932 | +0.207 |
| 0.75-0.80 | 63 | 0.775 | 0.968 | +0.193 |
| 0.80-0.85 | 58 | 0.825 | 0.983 | +0.158 |
| 0.85-0.90 | 32 | 0.875 | 1.000 | +0.125 |

Continuous, all buckets with n≥10 positive above 0.50, negative below. Classic FLB concentrated here.

## props (n=173) — structurally bimodal

102/173 in 0.00-0.05 (longshot prop lotteries: "will driver X win pole"). Mechanical — with 20 candidate drivers, each trades very low and only one wins. Empty in 0.55-0.60. **Exclude props from any FLB strategy.**

## futures (n=144) — directionally OPPOSITE, n small

Mid-range aggregate (0.40-0.70, n=22): mean p=0.525, yes_rate=0.455, **deviation −0.071**. Directionally opposite to game_outcome. Likely different dynamics (hedging pressure on long-maturity contracts, different participant mix). **Do NOT lump with game outcomes.**

## totals (n=21) / spreads (n=16) — INSUFFICIENT

Mid-range aggregates directionally positive (totals +17.9pp n=10; spreads +28.9pp n=7) but within noise. On Polymarket, totals/spreads are almost entirely an NFL phenomenon — a multi-season NFL pull would be needed to power this.

## Within-game_outcome sport decomposition (0.40-0.70 mid-range)

| sport | n | mean_p | yes_rate | dev |
|---|---:|---:|---:|---:|
| MLB | 268 | 0.538 | 0.679 | **+0.141** |
| NHL | 105 | 0.537 | 0.581 | +0.044 |
| NBA | 90 | 0.559 | 0.722 | **+0.164** |
| Tennis | 83 | 0.563 | 0.675 | +0.112 |
| UFC/Boxing | 63 | 0.546 | 0.476 | **−0.070** |
| NFL | 31 | 0.560 | 0.645 | +0.085 |
| Soccer | 26 | 0.552 | 0.692 | +0.140 |
| F1 | 3 | 0.508 | 0.667 | +0.159 |

**7 of 8 sports show positive mid-range FLB inside game_outcome**; only UFC/boxing is mildly negative (−7pp, n=63). MLB and NBA drive bulk of effect by mass × magnitude. Confirms FLB is a general game-outcome phenomenon, not a one-sport artifact.

## Slug-parsing rules (decision order, first match wins)

1. **uncategorized** early: `global-heat-increase`, `what-is-ther` (scraper garbage).
2. **spreads**: regex `-spread-|-handicap-`.
3. **totals**: `-total-<digit>`, `-match-total-`, `-ou-`, `-over-under-`, `-btts`, trailing `<digit>pt<digit>$`. Explicitly NOT "tot" (avoids Tottenham false-positive).
4. **props**: F1 driver/constructor props, first-X, halftime show, coin toss, attendance, fight-round props, draft picks.
5. **futures**: `win-the-YYYY-<league-event>`, `reach-the-(quarter|semi)finals`, `world-cup`, `nfl-playoffs`, `championship`, `mvp`, `super-bowl`, `drivers-champion`, `constructors-championship`, multi-round tournaments.
6. **game_outcome**: fallback for dated h2h, `a-vs-b`, single-race winner, etc.
7. **uncategorized**: 4 remain (all scraper noise).

## Implication for strategy design

**Gate the candidate universe on game_outcome slugs only.** Expect ~82% of sports T-7d candidates to pass. The other 18% carry different (or opposite-sign, for futures) FLB signal and should not be traded with the same parameters.

Reference artifacts: `analyze.py` (classifier + calibration), `data/subcategory_calibration.json` (structured), `data/uncategorized_slugs.txt` (4 scraper-noise slugs).
