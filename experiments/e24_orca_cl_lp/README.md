# e24 — Orca USDC/SOL concentrated-liquidity LP feasibility

**Date:** 2026-04-21
**Status:** Clean null. Closed out as NULL_RESULTS.md candidate.
**Headline:** Per-position data is architecturally gated behind paid indexers. Pool-level simulation calibrated against the Heimbach 49.5% loser-rate prior returns a clean null for the operating cell the requester was looking for (median net APR >5% at n≥200). Not worth a 3-day deeper investigation.

## One-line finding

At conservative concentration (conc_mult=1, matches the Heimbach prior within a few pp), narrow and medium CL ranges lost **−96% to −121% APR** in the observed 90-day window (SOL −31% drawdown). Only very wide (±40%) ranges survived at ~+14% opportunity-cost-adjusted APR. Sliding-window bootstrap produces some positive cells but all at n<30 — none reach the pre-committed n≥200 threshold.

## Brief

This was a parallel-to-e25 recon investigating whether the e23-style stratification methodology (sport × time × volume × lifespan × sub-category for Polymarket FLB) could be transferred to Solana CL LP on Orca Whirlpools / Raydium CLMM / Meteora DLMM to identify a systematically-profitable {range width × rebalance frequency × vol regime} operating cell.

Pre-committed decision gate: keep if any cell has median net APR >5% at n>200. Kill otherwise.

## Methodology

Pool studied: **Orca Whirlpool `Czfq3xZZDmsdGdUyrNLtRhGc47cXcZtLG4crryfu44zE`** — SOL/USDC, tick_spacing=4, **0.04% fee tier** (canonical deep pool).

Two models:
1. **Single 90-day window.** 5 range widths (±2.5%, ±5%, ±10%, ±20%, ±40%). CL V3 closed-form math for principal-at-exit, fees as `pool_gross_apr × conc_mult × time_in_range × duration`.
2. **Sliding-window bootstrap.** 24h / 7d / 30d durations × width buckets × volatility regime terciles. ~45 cells each at conc_mult=1 and 2.

Calibration check: at conc_mult=1, 7d sliding, ±10% width, loser rate = **41.6%** — close to the published Uniswap V3 49.5% prior (Bancor/IntoTheBlock). This validates using the pool-share model. Higher conc_mults substantially under-predict loser rate.

## Key numbers

**Single 90-day window (SOL −31%), conc_mult=1:**

| width | fee earned | principal PnL | IL vs HODL | net APR |
|---|---:|---:|---:|---:|
| ±2.5% | 0.59% | −30.4% | −15.0% | **−120.9%** |
| ±5% | 0.87% | −29.9% | −14.5% | **−117.9%** |
| ±10% | 1.46% | −28.9% | −13.5% | **−111.1%** |
| ±20% | 2.66% | −26.4% | −10.9% | **−96.2%** |
| ±40% | 25.0% | −20.0% | −4.6% | **+20.4%** (raw) |

Opportunity-cost adjustment: blended 50/50 (SOL staking 7% + USDC lending 5%) over 90 days = **−13.95%** baseline. Only ±40% clears this. After ÷5 discipline on the raw +20% APR → **~+14% opp-cost-adjusted**.

**Sliding-window bootstrap:** 19 cells pass the n≥20 + median>5% threshold at conc_mult=1; 0 pass n≥200 at any conc_mult (largest cell n=28 from 83-day observation span × 24h stride).

**No cell meets the pre-committed decision gate.**

## Why per-position data is gated

All four free-access paths failed within the first hour:

| Option | Blocker |
|---|---|
| `orca-so/profitability-analysis` | Requires knowing wallet/position addresses; `find` returns only currently-open positions; also needs `COINGECKO_PRO_API_KEY` |
| Top Ledger | SaaS; no free tier for Whirlpool decoded tables |
| Shyft Whirlpool positions API | "Unauthorized: Invalid API key"; no demo/open tier |
| Public Solana RPC | `getProgramAccounts` on Whirlpool program returns `-32010 excluded from account secondary indexes`. Signatures on pool address: ~900k/day = 81M sigs over 90d, infeasible via rate-limited free endpoint |
| Dune | Dashboards exist but JS-rendered; API requires paid key (~$390/mo analyst plan) |

Cheapest path to real per-position data: **Helius free tier (1M credits/mo) + snapshot → signature trace**, but only exposes live positions. Historical close-to-open cohort requires Dune analyst / Shyft paid ($49+/mo) / self-hosted archive node.

## Verdict

**Option C (close out, record the null).** Three reasons:

1. The 90-day single-window simulation is already directionally conclusive: in a hostile regime (31% drawdown), narrow ranges lose catastrophically and only extreme widths clear opportunity-cost.
2. The n≥200 target is architecturally infeasible without paid indexer access for a 90-day window on a single pool.
3. Orca is a price-taker to CEX BTC/SOL feeds — there's no analogous informational asymmetry to the +25pp Polymarket sports retail mispricing. Reference class is wrong.

## When to revisit

- If opportunity-cost math changes (e.g., SOL staking yield drops below 3% and USDC lending near zero, making any LP yield relatively attractive).
- If Kamino Liquidity Vaults publish audited active-vs-passive delta showing a retail-accessible edge.
- If the study pivots to JIT liquidity provisioning around predictable Jupiter swaps — that's a different thesis (microstructure alpha, not range-width stratification) and requires real-time mempool access.

## Reproducibility

- `scripts/fetch_and_simulate.py` — single-file reproducible script (no API keys required)
- `data/pool_meta.json` — Orca v2 API snapshot
- `data/pool_level_stats.json` — 90d SOL stats, vol, gross APR
- `data/sol_usdc_{hourly,daily}_90d.json` — raw OHLCV
- `data/single_window_90d.json` — single 90d simulation across widths + conc assumptions
- `data/stratification_poolmodel.json` — full 90-cell stratification table
- `data/vol_stratification.json` — vol-regime-split 7d and 30d tables
- `data/pool_level_bootstrap.json` — sliding-window bootstrap summary

## Related experiments

- [`../e25_hyperliquid_forensics/`](../e25_hyperliquid_forensics/) — parallel Solana/HL recon; the live follow-up
- [`../e23_stratification/`](../e23_stratification/) — the Polymarket FLB stratification that motivated this methodology transfer
- [`../../docs/NULL_RESULTS.md`](../../docs/NULL_RESULTS.md) — where this sits as a registered falsification
