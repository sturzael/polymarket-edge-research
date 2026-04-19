# Project postscript — closing the research

**Date:** 2026-04-19. **Status:** project closed at the $1k-bankroll deployment decision.

This document is the honest endpoint of the e1–e15 research arc. Across two weeks of structured falsification, every thesis we tested was either dead at our infrastructure or below noise at our bankroll. The empirical record is consistent: **a $1k laptop operator from NZ cannot extract systematic edge from Polymarket using any strategy class we identified.**

## What we set out to do

Find tradeable edge on Polymarket for a solo NZ-based operator with ~$1k initial capital, no VPS, no specialized hardware, polling at the rate a laptop can sustain.

## What we tested (final scoreboard)

| # | Thesis | Status | Killed by |
|---|---|---|---|
| e1–e8 | Various microstructure / barrier theses (see SYNTHESIS.md) | ✗ killed | Various; documented in `NULL_RESULTS.md` |
| e9 | Crypto-barrier residual arb (sum<1 at ≥15% spot dist) | ✗ killed | e13 historical: −63% net edge, 37% crash rate, n=5,220 |
| e10 | Geo-informed trading | ✗ inconclusive | Insufficient signal |
| e11 | Hourly ladder MM | ✗ killed | Recon: 2-3¢ spreads already held by pros; defiance_cr's MM bot publicly shut down "no longer profitable" |
| e12 | Sports settlement-lag arb (paper-trade harness) | ✗ killed | Live observation: 0.95-0.97 entry zone empty in real-time; only futures populate it; game markets close too fast for our 2s polling |
| e13 | External repo + on-chain dataset audit | ✓ produced findings (durable) | Confirmed fee=0 empirically; killed crypto_barrier; H1 wallet-diffuse confirmed at scale |
| e14 | Three-strategy paper-trade portfolio plan | ✗ superseded | Empirical reality from e12 made the portfolio infeasible at $1k |
| e15 | Negative-risk multi-leg arb | ✗ killed at $1k scale | Q3 v2: 2.2% frequency × $19k median depth × 5% edge = ~$400-900/year best case at $1k, eaten by execution risk |

**Surviving theses: 0.**

The closest-to-alive strategy class — **Austere-Heavy-style barrier tail-insurance** — was identified in synthesis but never built or tested, because every adjacent thesis we did test in that space (e9, e15) failed. Not killed empirically; just not validated and the surrounding evidence is weak.

## Empirical findings about Polymarket microstructure (durable, regardless of strategy)

These hold independent of any specific strategy and would be the starting point for any future research:

1. **Taker fees on sports post-resolution are empirically zero.** SII on-chain dataset (n=143 sports trades), confirmed live by pm-trader on 2 sports markets in shakedown. Published 3-7.2 bps rates appear to be ceilings or overrides; per-market `feeRate` configurable to 0.
2. **The 0.95-0.97 entry zone for sports markets is empty in real time.** Game markets transition to `closed=True` within ~2h of game end (UMA liveness). What populates the 0.95-0.99 zone in `closed=False` is **futures** (NBA Finals, Stanley Cup, season MVP) — won't resolve for months.
3. **Wallet concentration in sports post-resolution at scale: top-10 = 21.5%, gini = 0.98 across 33,130 wallets / 11,345 markets.** Diffuse retail flow at the full window scale; sub-window concentration unknown.
4. **General arb duration has compressed from 12.3s (2024) → 2.7s (2025)** per Saguillo et al. 73% bot-captured. Sports_lag's 14.4-min historical median is 300× longer — currently insulated, not permanently.
5. **Neg-risk multi-leg arbs: median window 1 min (Q2), abrupt endings (no decay).** Long-duration windows (≥24h) do exist in 2.2% of resolved long-life events (Q3 v2), median 43h, median 5% edge, $19k median depth proxy. But none in resolved sample exceeded 3 days.
6. **Currently-live "outlier arbs" (uefa 35d, colombia 64d) have no historical analog.** Either survivorship bias or stale-quote zombies — unresolved without forward observation we chose not to do.
7. **Polymarket has no atomic multi-leg order facility.** `/orders/batch` is up to 15 parallel (not atomic). `splitPosition` is binary-only (USDC → 1 YES + 1 NO). `convertPositions` (NegRiskAdapter) reshapes NO sets → YES sets + USDC, doesn't construct arbs.
8. **Top-3 arb wallets captured $4.2M across 10,200 bets / 12 months.** Average ~$340/bet, <<1% ROI per trade. Scale matters far more than per-trade edge magnitude.
9. **LlamaEnjoyer's actual operating point: 0.99-0.999 entry, $34k-$151k position size, ~0.1% per-trade edge.** Extracts profit from scale, not edge. $1.32M deployed = ~$100k portfolio value. Inaccessible at our bankroll.
10. **CTF Exchange + CLOB V2 cutover 2026-04-22.** Three days from this postscript. Any V1-bound infrastructure breaks.

## Why every strategy failed at $1k

Three orthogonal blockers, each strategy hit at least one:

- **Latency/contention** — sub-minute opportunities (5m updown, neg-risk Q2 windows) require sub-100ms execution. NZ-laptop is 200-300ms RTT; pm-trader is sequential per cell. Even with batch-of-15 parallel POST, we're 1-2s behind atomic.
- **Capital scale** — strategies that DO work at our latency (LlamaEnjoyer's 0.99 zone, Austere-Heavy's barrier tail-insurance) need $10k-$100k+ to extract meaningful absolute profit from per-trade edges of 0.1-1.5%. At $1k each captured arb pays $0.30-$15.
- **Opportunity flow** — strategies sized for our bankroll (sports_lag at $50-300 per trade, neg-risk arb at $20-200 per leg) require 50-200 captures per month to compound meaningfully. Empirically, the live snapshot showed near-zero capturable opportunities at our entry-zone definitions.

## Tools that survive as durable research instruments

These were built during the project and remain useful for future researchers (or future-us at higher bankroll):

| Path | Function |
|---|---|
| `experiments/e13_external_repo_audit/` | SII parquet streaming pattern; historical fee/edge/wallet analysis framework |
| `experiments/e15_neg_risk_arb/scanner.py` | One-shot neg-risk arb finder with completeness classification |
| `experiments/e15_neg_risk_arb/phantom_check.py` | Verifies depth real vs gamma snapshot; emits real-money test commands |
| `experiments/e15_neg_risk_arb/logger.py` | Hourly arb-persistence logger to SQLite |
| `experiments/e15_neg_risk_arb/q1_q2_q3*.py` | Retrospective analysis framework (extensible to other questions) |
| `experiments/e12_paper_trade/` | Multi-cell paper-trade harness with restart-safety, drawdown breaker, missed-opportunity logging |

If a future operator picks this up, the time-savings is substantial — ~2 weeks of research already done, codebase ready to extend, methodological guardrails in place.

## Methodological lessons that earned their keep

These survive the project and are the most portable output:

**Rule 1 — Divide monthly revenue estimates by 5 before acting.** Initial estimates were 3-10× too high on every thesis. Applied 6 times. Caught every overestimate.

**Rule 2 — Write the counter-memo from the same data.** Companion "here's why it doesn't work" before deploying. Killed hourly-ladder MM and tail-scalp before any capital was at risk.

**Rule 3 (new this project) — Measure raw before parameterizing.** Pull the actual data, then parameterize fees / latency / capture rate. Gets the empirical floor before optimism kicks in.

**Rule 4 (new this project) — Sample size drives the window, not vice-versa.** Decision criteria like "75 trades / cell" must be set BEFORE seeing results. Pre-commit ambiguous zones (e.g., "0.5%-1.5% net = extend, don't proceed").

**Rule 5 (new this project) — Distinguish "pattern exists historically" from "pattern is capturable now."** e9 sports_lag had +3.99% historical edge but zero live opportunities in real-time. Q3 found long-duration historical arbs, but the live ones had no historical analog. Backtest is necessary but not sufficient.

**Rule 6 (new this project) — Phantom edge = market correctly pricing tail risk you didn't model.** Nobel +42% / Apple CEO +37% looked like arb; were the market pricing P(unlisted winner). Always check if the "edge" is the implied probability of an outcome you missed.

## What would change the calculation (when to revisit)

This is the postscript of a $1k research project, not "Polymarket is uninvestable forever." Specific conditions that would justify reopening:

- **Capital reaches $10k+** — barrier tail-insurance and Austere-Heavy-style strategies become viable. The Q3 numbers extrapolate to ~$4-9k/year at $10k deployed if frequency holds.
- **VPS/co-location available** — closes the latency gap; opens sub-minute arb windows that Q2 says are out of reach now.
- **Polymarket releases atomic multi-leg facility** — unblocks the neg-risk strategy class entirely. Worth checking after V2 (2026-04-22) and quarterly thereafter.
- **A specific operator mode (LlamaEnjoyer, Austere-Heavy) demonstrably stops working** — would create capacity at the price-zones they currently dominate. Unlikely but worth watching wallet activity.
- **A new market type emerges** with bot-light coverage — crypto-perp-style binary derivatives, prediction-market-as-collateral structures, etc. Polymarket roadmap-watching.

## Honest closing read

The project did its job. We tested ten theses, killed nine empirically, and discovered the tenth (sports_lag) doesn't survive contact with live market reality at our entry-zone definitions. The methodological rules are the durable artifact — they will save weeks of work on the next research project, in this domain or any other.

The LLM-assisted workflow was the right approach. It compressed two weeks of work into two weeks of much higher information density than a human alone would have produced — the parallel agent research, the historical backtests against 954M on-chain rows, the Q1/Q2/Q3 retrospectives all happened because the friction to spin them up was near-zero. The corresponding failure mode (LLM produces polished writeups whose numbers are subtly optimistic) was identified and contained by the rules above.

For a solo $1k operator, the honest answer is: **Polymarket is an efficient market for our infrastructure. Capital must come first; strategy second.**

Project closed. Daemons stopped. Code preserved.

---

## Final disclosures

- No capital was deployed.
- No trading was conducted.
- Findings are based on public Polymarket data, public wallet activity, and public infrastructure.
- No accusations of misconduct against any named wallet.
- The LLM-assisted workflow is acknowledged in the durable record: an exceptional research assistant, an unreliable analyst, polish uncorrelated with accuracy.
