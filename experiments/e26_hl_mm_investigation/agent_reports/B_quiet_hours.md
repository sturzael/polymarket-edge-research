# Agent B — HL BTC quiet-hours empirical characterization

**Returned:** 2026-04-21

## Sample

HL `candleSnapshot` 15m (52d) + 1h (60d), ending 2026-04-21 06:10 UTC. **HL 1m capped at ~3.5 days** regardless of `startTime`.

## 1. Hour-of-day realized vol (bps, sqrt(Σ log(c/o)²) per hour, 15m bars)

| UTC hr | p25 | med | p75 |   | UTC hr | p25 | med | p75 |
|---|---|---|---|---|---|---|---|---|
| 00 | 22.6 | 34.9 | 50.0 |   | 12 | 22.9 | 30.0 | 55.4 |
| 01 | 19.5 | 35.8 | 57.9 |   | **13** | 29.7 | **46.7** | 75.8 |
| 02 | 24.4 | 33.9 | 48.0 |   | **14** | 34.2 | **60.2** | 91.1 |
| **03** | 17.5 | **25.5** | 38.8 |   | **15** | 29.9 | **49.4** | 81.3 |
| 04 | 20.2 | 31.4 | 40.8 |   | 16 | 26.7 | 39.1 | 54.0 |
| **05** | 20.3 | **27.9** | 42.1 |   | 17 | 30.1 | 44.6 | 66.6 |
| **06** | 18.7 | **26.8** | 42.4 |   | 18 | 25.5 | 36.7 | 56.3 |
| 07 | 22.9 | 33.3 | 49.2 |   | 19 | 22.2 | 35.1 | 51.8 |
| 08 | 22.1 | 32.2 | 57.5 |   | 20 | 26.1 | 32.5 | 47.4 |
| **09** | 21.1 | **30.2** | 49.8 |   | 21 | 23.3 | 33.2 | 41.7 |
| **10** | 21.2 | **29.8** | 43.6 |   | 22 | 21.8 | 42.9 | 61.9 |
| 11 | 20.0 | 34.3 | 46.0 |   | 23 | 20.1 | 36.4 | 47.7 |

## 2. Quiet window

**Bottom-quartile hours (by median): {03, 05, 06, 09, 10, 12} UTC** — a **03–12 UTC band** (Asia late / Europe open). Peak vol is **13–17 UTC**, median 46–60 bps, ~2× quiet-hour median.

## 3. 4h |ret| flat-regime check

- Quiet hours: **48.3%** of 4h windows with |ret|<0.5% (n=358)
- Active hours: **53.9%** (n=1079)

Counter to expectation — active hours tied/higher because 4h smears across the day and the 60d window drifted in Asia. **Signal is in 1h realized vol, not in 4h ret flatness at this sample size. Don't rely on the 4h test.**

## 4. Rank-2 wallet overlap — CRITICAL CAVEAT

The fills file (`0xecb63caa…`) contains a **single 2026-04-21 session, 00:53–03:50 UTC, 876 BTC fills in ~3 hours**. HL `userFillsByTime` returned only the most recent batch. A 24-hour preference profile cannot be computed from this sample; the literal "82% at hour 02" is a window artifact.

What IS testable: was the wallet's 3-hour window objectively quiet?

| UTC hr | rv_today (bps) | 60d median (bps) | below median? | wallet BTC fills |
|---|---|---|---|---|
| 00 | 27.4 | 34.9 | yes | 26 |
| 01 | 22.5 | 35.8 | yes | 152 |
| 02 | 31.1 | 33.9 | yes | 606 |
| 03 | 25.5 | 25.5 | tie | 92 |

|4h ret| centered on window (22→02 UTC) = **0.511%**; (02→06 UTC) = **0.234%**. Fill composition: **719 Open Long, 14 Open Short, 100 Close Long, 37 Close Short, 6 flip** — classic passive-resting-quote MM, not directional taking.

**Verdict: directionally consistent with the MM-in-flat hypothesis** (session was in an overnight quiet band with below-median vol and sub-threshold 4h drift), but **single-session evidence only**. Cannot confirm the wallet *avoids* active hours from this data.

## 5. Spread snapshot (5 samples, 06:09–06:10 UTC = quiet band)

- Top-of-book spread: **0.13 bps (1 tick = $1 @ $75,732)** on every sample
- 5-level ask depth: 21–34 BTC; 5-level bid depth: 0.02–2.8 BTC (asymmetric — bids thin, asks fat; consistent with short-term downward pressure)
- Could not snapshot an active hour today; HL info endpoint doesn't expose historical L2.

## 6. Caveats

- HL 1m candles return ≤3.5d of history; used 15m/1h instead.
- Wallet fills cover only 3 hours of one day → cannot test hour-of-day selectivity. **A proper 60d pull via paginated `userFillsByTime(startTime)` is required before claiming the wallet actively avoids active hours.**
- HL timestamps are UTC-native; verified.
- ÷5 discipline: quiet hours ≈ 25% of day. Observed 1-tick (0.13 bps) spread + maker rebate (~0.3 bps on BTC) gives razor-thin gross edge before toxic-flow drag. **Do not extrapolate P&L from a 3-hour wallet window.**

## Bottom line

HL BTC-PERP does have a real low-vol band (03–12 UTC, ~1-tick spreads during 06 UTC). The rank-2 wallet's observable trading today sat squarely inside a below-median-vol window, with fill composition matching passive MM — consistent with the hypothesis. But the fills sample is 3 hours, not 60 days, so the hour-of-day selectivity claim is not yet validated. **Re-run with paginated wallet fills before building on this.**

## Artifacts

All in `../data/`:
- `btc_hourly_vol.json` — hour-of-day table + 4h flat-regime test
- `rank2_hour_distribution.json` — wallet hour distribution + today_window_analysis + caveat
- `l2_snapshots.json` — 5 BTC book snapshots @ 06:09 UTC
- `btc_{1m,5m,15m,1h,4h}_candles.json` — raw candles
- `fetch_candles*.py`, `analyze.py`, `l2_snapshots.py` — pipeline scripts
