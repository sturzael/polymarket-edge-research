# e18 — Drift Protocol (Solana) prediction market calibration

**Status:** TIER 3 — venue too thin for statistical FLB analysis. Drift's B.E.T prediction market program is effectively dormant.
**Date:** 2026-04-20

> Report body captured from the background sub-agent (which didn't write this file itself). Scripts, raw data, and calibration tables were written directly by the agent under `scripts/` and `data/`.

## Venue profile

- **15 total prediction markets in Drift's entire history** (identified by `-BET` suffix; Drift's Data API does not expose a `contract_type` field, so suffix is the only discriminator).
- **Market launches have stopped:** 7 in 2024Q3, 6 in 2024Q4, 2 in 2025Q1, **0 in 2025Q2 → 2026Q2** (most recent 5 quarters).
- **Volume is extremely concentrated:** KAMALA-POPULAR-VOTE-2024-BET ($23.7M) and TRUMP-WIN-2024-BET ($8.2M) alone = **94% of lifetime volume** ($31.8M of $33.75M). Without the 2024 US election, venue is essentially empty.
- **Median lifetime volume per market:** $72.7k; only 2/15 markets cleared $1M lifetime volume.
- **Median hourly trading depth:** $10 (p50 hourly volume, median across markets). p90 median: $936. Max hourly median: $16k. You cannot trade meaningful size on any non-election market without significant slippage.
- **Category breakdown:** politics (n=4, $32.0M, 95% of volume), sports (n=8, $1.48M), economics (n=1, $223k), crypto_events (n=2, $8.5k).
- **Not deep enough to trade on** except during major political events with advance notice.

## Calibration (T-7d anchor, all 14 resolved markets)

- **n_markets_with_outcome:** 14 (WLF-5B-1W-BET marked YES; LNDO-WIN-F1-24-US-GP-BET not classifiable — duration too short for T-7d anchor before event).
- **n_markets_with_T-7d_anchor:** 13.
- **Price-outcome correlation at T-7d:** +0.48 (n=14 pooled with midpoint fallback). Directionally well-calibrated.
- **Per-bucket z-scores:** all |z| ≤ 1 except **0.10-0.15 bucket (n=1, FED-CUT-50-SEPT, z=+2.65)** — single datapoint (Drift massively underpriced Fed 50bp cut at T-7d, traded ~0.11, resolved YES). Anecdotal, not statistical.
- **Sports-only subset (n=6):** too small for any claim. Distribution: 0-0.05 → NO, 0.20-0.25 → NO, 0.50-0.55 → NO, 0.55-0.60 → YES (WARWICK), 0.90-0.95 → YES, 0.95-1.00 → YES. Directionally calibrated; no evidence for the e16 Polymarket 0.55-0.60 sports favorite-underpricing (just 1 sample in that bucket).

## Cross-venue sanity check

- Drift **TRUMP-WIN-2024-BET T-7d = 0.66** (2024-10-29, ±12h VWAP over $121k of trades). Matches Polymarket's widely-reported T-7d of ~0.63-0.66 for the same contract. Drift prices were **not dislocated** from Polymarket during the high-liquidity election period.

## Methodology decisions

- Drift's `/stats/markets/prices` endpoint returns `marketType = perp | spot`; prediction markets live under `perp` with a `-BET` suffix naming convention (no machine-readable flag).
- Drift candles API has an undocumented param-naming inversion: **`startTs` is the NEWER boundary, `endTs` is the OLDER**; error message "Start timestamp must be after end timestamp" is the giveaway.
- Resolution detection: used the last candle with `quoteVolume > 0` as `resolution_ts` (Drift zero-fills post-settlement indefinitely). Outcome inferred from mean of `fillClose` over the last 5 traded candles: ≥0.85 → YES, ≤0.15 → NO, otherwise ambiguous. Three markets required manual override (DEMOCRATS-MICHIGAN, BREAKPOINT-IGGYERIC, WARWICK-FIGHT) because trading froze above 0.15 / below 0.85 of final settlement.
- Data fetched via `data.api.drift.trade` Data API only (S3 archive deprecated per Drift docs since Jan 2025). No `driftpy` SDK needed — REST API suffices.

## Implication for the research question

Drift is **not a useful venue for testing the Polymarket FLB hypothesis** with current data: 15 markets total, dominated by 2 election markets, no new listings in 5 quarters. The venue is a scouting dead-end for calibration studies — future agents investigating "is the FLB effect prediction-market-general?" should deprioritize Drift and focus sample power on Polymarket, Kalshi, Betfair, or PMXT.

## Artifacts (all under `experiments/e18_drift_solana/`)

- `scripts/fetch_candles.py` — pulls hourly candles for all -BET markets
- `scripts/calibrate.py` — resolves outcomes + computes T-7d/T-3d/T-1d/midpoint calibration
- `scripts/venue_profile.py` — volume/depth/category distribution
- `data/all_markets.json` — full Drift market listing (149 markets)
- `data/openapi.json` — Drift Data API OpenAPI spec (snapshot for reproducibility)
- `data/candles/*.json` — 1h OHLCV for each of the 15 -BET markets
- `data/market_level.json` — per-market resolution + 4 anchor prices
- `data/calibration_table.json` — bucket aggregations for all 4 anchors
- `data/venue_profile.json` — venue-viability metrics

Sources: [Drift prediction-markets intro](https://docs.drift.trade/prediction-markets/prediction-markets-intro), [Historical Data V2](https://docs.drift.trade/historical-data/historical-data-v2), [Drift Data API Playground](https://data.api.drift.trade/playground), [Drift launches PM (The Block)](https://www.theblock.co/post/311888/solana-based-drift-protocol-launches-prediction-market).
