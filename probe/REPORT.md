# Polymarket Short-Duration Crypto Probe — Report

- **Probe window:** 2026-04-18 14:31:37 → 2026-04-19 07:26:13
- **Elapsed:** 16.91h (target 24.00h)

## What exists

- Crypto markets discovered: **2347**
- Of those, with nominal expiry inside probe window: **2171**

### Duration breakdown (discovered)
| Duration | Count | Share |
|---|---:|---:|
| 5m | 1283 | 54.7% |
| 15m | 428 | 18.2% |
| 1h | 6 | 0.3% |
| 4h | 384 | 16.4% |
| 1d | 40 | 1.7% |
| 1w | 194 | 8.3% |
| >1w | 12 | 0.5% |

### Underlyings
| Underlying | Count |
|---|---:|
| ETH | 513 |
| BTC | 512 |
| SOL | 354 |
| XRP | 338 |
| DOGE | 310 |
| BNB | 309 |
| TRX | 8 |
| ADA | 3 |

## Resolutions during probe

- Resolution rows written: **2183**
- Cleanly resolved (outcome populated, within watch window): **1316**
- UNRESOLVED (timed out or API never reported outcome): **867**

### Outcome distribution
| Outcome | Count |
|---|---:|
| UNRESOLVED | 867 |
| DOWN | 719 |
| UP | 594 |
| TEAM REY | 3 |

### Resolution lag (seconds after nominal expiry)
- mean: **502.0s**
- median: **387.9s**
- p90: **858.8s**
- max: **1493.2s**

## Price data sufficiency near expiry

- Resolved markets with **≥5 samples in final 60s**: 859 / 2183
- Resolved markets with **≥10 samples in final 60s**: 755 / 2183
- Resolved markets with **≥30 samples in final 5min**: 673 / 2183
- Resolved markets with any sample within final 15s: **841** / 2183
- Of those, markets where final-stretch book was thin (ask-bid > 0.20): **24**

## Recommendation

### ✅ PROCEED — full Expiry Microstructure Mode on 5m markets

- 1283 five-minute crypto markets discovered (plenty of throughput).
- 1316 clean resolutions observed within the probe window.
- 859 of those had ≥5 price samples in the final 60 seconds (demonstrates final-stretch sampling is feasible at 5s cadence).
- Next step: build the full expiry sampler on 5m markets, switching to CLOB websockets for sub-second resolution, and match the spot feed exactly to each market's resolution source (critical for validity).

### Unresolved design blockers (must fix before full build)

- **Reference feed matching:** each market resolves against a specific oracle (Chainlink / Coinbase / Binance). Until we match our spot feed exactly, any observed 'mispricing' may be venue-latency artifact.
- **Analytical metric:** `|poly - outcome|` (err_H) rewards certainty, not accuracy. Replace with calibration curves, Brier score vs. spot-implied benchmark, and lead-lag cross-correlation.
- **Hindsight-biased flags:** "market underestimated the move" flags will fire whenever spot moves, because spot movement *is* the outcome for up/down markets. Lead-lag τ>0 is the real question.
- **REST+midpoint is too coarse for final 10s.** Full build needs CLOB websocket with separate bid/ask, not 1Hz REST midpoint.

## Sample resolved markets (up to 12)
| end | underlying | duration | outcome | lag (s) | slug |
|---|---|---|---|---:|---|
| 2026-04-18 14:25:00 | ETH | 5m | DOWN | 397.8 | eth-updown-5m-1776478800 |
| 2026-04-18 14:25:00 | BNB | 5m | UP | 398.1 | bnb-updown-5m-1776478800 |
| 2026-04-18 14:25:00 | BTC | 5m | DOWN | 398.4 | btc-updown-5m-1776478800 |
| 2026-04-18 14:25:00 | DOGE | 5m | UP | 398.9 | doge-updown-5m-1776478800 |
| 2026-04-18 14:25:00 | SOL | 5m | DOWN | 399.2 | sol-updown-5m-1776478800 |
| 2026-04-18 14:25:00 | XRP | 5m | UP | 399.5 | xrp-updown-5m-1776478800 |
| 2026-04-18 14:30:00 | BTC | 5m | DOWN | 293.9 | btc-updown-5m-1776479100 |
| 2026-04-18 14:30:00 | XRP | 15m | UP | 307.6 | xrp-updown-15m-1776478500 |
| 2026-04-18 14:30:00 | BNB | 5m | DOWN | 323.2 | bnb-updown-5m-1776479100 |
| 2026-04-18 14:30:00 | SOL | 5m | UP | 325.9 | sol-updown-5m-1776479100 |
| 2026-04-18 14:30:00 | DOGE | 5m | DOWN | 326.4 | doge-updown-5m-1776479100 |
| 2026-04-18 14:30:00 | SOL | 15m | UP | 340.5 | sol-updown-15m-1776478500 |
