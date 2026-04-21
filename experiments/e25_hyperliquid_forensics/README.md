# e25 — Hyperliquid top-wallet structural-vs-momentum decomposition

**Date:** 2026-04-21
**Status:** v1 complete. Descriptive study. No capital deployed.
**Headline:** the Polymarket "top wallets are mostly momentum-lucky" finding **did NOT replicate** on Hyperliquid. HL top-wallet distribution is heavily left-skewed toward structural signatures — opposite shape. 10 of 24 top wallets don't trade BTC/ETH/SOL at all; the real HL top-PnL book lives in synthetics (xyz:CL, BRENTOIL, SILVER, MSTR), HYPE, TAO, XMR.

## One-line finding

On HL's core BTC/ETH/SOL slice, 9 of 14 analyzable top wallets classify STRUCTURAL (<30% momentum-coincident). The highest-PnL analyzable wallet, `0xecb63caa` ($203M allTime), enters 84% of BTC trades in flat-regime windows — the statistical fingerprint of market-making in quiet hours.

## Methodology

Direct port of the wallet-decomposition used in `e9_wallet_competitor_intel` on Polymarket. For each wallet's directional entry fill on BTC/ETH/SOL perps:

- Compute the 4-hour pre-entry return of the underlying (Binance 1m klines as reference).
- Classify the entry:
  - **Momentum-coincident:** entry follows a >0.5% move in the 4h lookback, *same direction* as entry.
  - **Contrarian:** entry follows a >0.5% move, *opposite direction*.
  - **Flat-regime:** `|4h ret| < 0.5%` at entry time.
- Per-wallet metric: `momentum_pct = momentum_coincident / total_entries`.
  - `>80%` → MOMENTUM-LUCKY (regime-dependent, fade candidate)
  - `<30%` → STRUCTURAL CANDIDATE (regime-independent)
  - middle → MIXED

Sample: 24 wallets from HL all-time top-50 PnL; 14 had ≥20 BTC/ETH/SOL entries in the 30-day window; 21,648 total entries analyzed.

## Key results

| classification | n wallets | note |
|---|---:|---|
| STRUCTURAL | 10 | 9 below 20% momentum — much of this is flat-regime quiet trading |
| MIXED | 3 | ranks 4, 21, 27 |
| MOMENTUM-LUCKY | 1 | rank 38, losing the month — as the fade thesis predicts |
| UNDERPOWERED | 10 | no BTC/ETH/SOL entries — trade synthetics/HYPE/alts |

Distribution is heavily left-skewed, not bimodal. See `FINDINGS.md` for the ranked 24-wallet table, distribution histogram, and caveats.

## Three wallets worth a deeper look

- **`0xecb63caa`** — rank 2, $203M allTime, 0.1% momentum, 84% flat-regime (BTC 84%). MM-like fingerprint.
- **`0x7fdafde5`** — rank 5, $159M allTime, 72% contrarian on ETH, n=4,413. Cleanest heavy fader.
- **`0x856c3503`** — rank 42, $39M allTime, 95% contrarian on ETH, n=81 (underpowered but striking).

## Critical caveat on rank-2 (added post-e26 quiet-hours analysis)

The `0xecb63caa` fills sample used here covers only a **3-hour session (2026-04-21 00:53–03:50 UTC)**, not 60 days. HL's `userFillsByTime` returned the most recent batch without pagination. The "84% flat-regime" statistic is real for that window but cannot be read as a 60-day hour-of-day preference profile.

What's actually established:
- During the 3 observed hours, 1h realized vol was below the 60-day median for that hour (see `../e26_hl_mm_investigation/`).
- Fill composition (719 Open Long, 14 Open Short, 100 Close Long, 37 Close Short) is classic passive-resting-quote MM, not directional taking.

What's NOT established:
- Whether the wallet actively avoids high-volatility hours over long windows.
- Whether the "MM in quiet hours" hypothesis holds outside this one overnight session.

**A paginated 60-day pull via `userFillsByTime(startTime=...)` is required before building deployment on this signature.**

## Why this matters

Two monetizable angles beyond any direct trading signal:

1. **The inverted distribution is publishable.** No prior public work decomposes HL top-wallet PnL into structural-vs-regime components. Content artifact in its own right.
2. **The rank-2 wallet's MM signature motivates experiment e26** (`../e26_hl_mm_investigation/`) — scoping whether a solo-operator MM bot can target HL BTC in quiet hours. Spoiler from the 4 recon agents: **classical spread capture is dead for retail; niche inventory-management in quiet hours is the only realistic residual path, capped at HLP-like ~15–20% APR gross.**

## Honest caveats

- **24-wallet case study, not a population.** Do not conclude "HL has/lacks alpha."
- **BTC/ETH/SOL only.** HL top operators make money in synthetics/HYPE/alts that this study cannot classify (no off-exchange price reference available).
- **30-day window.** Subsample regime effects dominate; labels are not long-horizon style claims.
- **Entries = `dir ∈ {Open Long, Open Short}`.** Flips and reduces dropped — under-samples pure-flip styles.
- **Rank-2 wallet is a 3-hour snapshot, not 60 days.** See critical caveat above.
- **No return projections made.** Descriptive study.

## Reproducibility

Data on disk (all regenerable):
- `data/leaderboard.json` — raw HL leaderboard pull
- `data/top50.json` — selected wallets + metadata
- `data/fills/` — 24 per-wallet `userFillsByTime` JSON files (public HL `/info` endpoint)
- `data/prices/{BTC,ETH,SOL}.json` — Binance 1m klines for the 30-day window
- `data/wallet_summary.json`, `data/classification_results.json` — final classification
- `scripts/classify.py` — classifier script

To reproduce: point `scripts/classify.py` at a populated `data/prices/*`; classifier threshold = ±0.5% / 4h lookback; momentum bucket weights flat-regime as non-momentum.

## Related experiments

- [`../e9_wallet_competitor_intel/`](../e9_wallet_competitor_intel/) — Polymarket wallet-forensics that produced the methodology
- [`../e14_polymarket_leaderboard_intel/`](../e14_polymarket_leaderboard_intel/) — Polymarket top-wallets dataset
- [`../e26_hl_mm_investigation/`](../e26_hl_mm_investigation/) — deployment-side follow-up (HL MM bot viability)
- [`../e24_orca_cl_lp/`](../e24_orca_cl_lp/) — sibling Solana DeFi null-result study (parallel recon)

## Open work

1. **Paginated 60-day wallet fills pull.** Mandatory before acting on any wallet-specific hypothesis. Rate-limited at HL's 60 req/min, ~3 hours work.
2. **Longer window for classification (90–180d)** to reduce sample-regime bias.
3. **Synthetics slice.** 10 wallets unanalyzed; this is where actual top-PnL lives.
4. **Publish the inverted-distribution finding** — Substack / X thread, 1 day.
