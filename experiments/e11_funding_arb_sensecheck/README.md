# e11 — Funding-rate arbitrage sense-check

**TL;DR: funding-rate arb (cash-and-carry on perps) is not viable at retail scale in the current regime. 90-day mean/median funding rates on Binance BTC and ETH perps are near-zero or slightly negative; p90 is 6% APY before fees; round-trip fees are 0.25-0.5% across both legs. Not a strategy to pursue.**

## Why this memo exists

In the wallet-intel thread (see `experiments/e9_wallet_competitor_intel/`) the user asked about alternatives to the falsified Polymarket tail-scalp. The response pitched funding-rate arb as a lower-drama strategy with "historically 10-30% APY on BTC" — a number pulled from 2020-2023 bull-market recall, not verified against current data. The user asked for a sense-check. This memo is that sense-check.

The number was wrong. Current and trailing 90-day data show funding rates near zero in both mean and median.

## What I measured

Ran `probe.py` to pull:
1. Current snapshot of funding rates on BTC, ETH, SOL perps (Binance USDM).
2. 90-day history of funding rates on BTC and ETH perps.
3. Live spot-vs-perp basis.

Source: `ccxt` against `binance` and `binance` (futures mode). All endpoints public, no API key needed.

## What the data showed

### Current funding rates (April 19 2026 snapshot)

| Symbol | Rate / 8h | Annualized APY |
|---|---|---|
| BTC/USDT perp | −0.0083% | **−9.1%** |
| ETH/USDT perp | −0.0147% | **−16.1%** |
| SOL/USDT perp | −0.0074% | **−8.1%** |

All three negative. Classic cash-and-carry (long spot + short perp) would *pay* funding, not receive it. To collect, you'd need short-spot / long-perp — which requires borrowing spot (~4-8% borrow cost on Binance margin) and does not net to a positive trade at these rates.

### 90-day history — BTC/USDT perp (270 periods)

| Statistic | Rate / 8h | Annualized |
|---|---|---|
| Mean | −0.00001% | **−0.02%** |
| Median | 0.00027% | **+0.30%** |
| p10 | −0.00608% | −6.66% |
| p90 | +0.00565% | +6.19% |
| Max | +0.0100% | +10.95% |
| Min | −0.0152% | −16.64% |
| % positive periods | 53.0% | — |

### 90-day history — ETH/USDT perp (270 periods)

| Statistic | Rate / 8h | Annualized |
|---|---|---|
| Mean | −0.00112% | **−1.23%** |
| Median | −0.00007% | −0.08% |
| % positive periods | 48.5% | — |

## The fee math that finishes it off

Binance fees (VIP 0 with BNB discount):
- Spot taker: 0.075%
- USDM perp taker: 0.04%
- One-way both legs: 0.115%
- Round-trip (enter + exit): ~0.25%

Breakeven holding period against realized funding income:
- At **median BTC APY (0.30%)**: need to hold >300 days without rebalancing to recoup fees. Pointless.
- At **mean BTC APY (−0.02%)**: you never break even; the expected trade is slightly negative.
- At **p90 BTC APY (6.19%)**: fees cost 15 days of funding → net ~4% APY after fees = **$400/year on $10k**, excluding liquidation risk and borrow if short-spot.

For context, 0-risk stablecoin lending (USDC on centralized venues, T-bill-backed) is 4-5% APY at the time of writing. The funding-rate trade at p90 beats T-bills by ~0 after fees. At the mean, it loses.

## Capital structure, for completeness

- Long-spot / short-perp carry: **2× notional locked** (spot + perp margin). Capital efficiency is poor vs strategies that recycle the same dollar.
- Binance allows cross-collateral (spot BTC can back perp margin) which improves this, but adds perp-leg liquidation risk during rallies.
- Cross-exchange version (spot on A, perp on B) needs withdrawal on one venue to rebalance when the trade goes against you — adds withdrawal fees and on-chain risk.

## What would make this viable again

- **Sustained bull trend.** Perp demand drives persistent positive funding at 0.02-0.05%/8h (20-50% APY). Historically this has happened for 3-9 month stretches in 2021, 2023, early 2024.
- **Funding-rate dislocation events.** Liquidation cascades briefly push funding to ±0.1%/8h (±100% APY) for hours. Tactical entries possible but requires being ready to deploy capital instantly; not a passive strategy.
- **Altcoin basis (higher-volatility perps).** ETH/SOL often pay higher funding than BTC but also carry more liquidation risk. Not fundamentally different.

None of these are predictable regimes to time. The honest frame is: funding-rate arb is a bull-market strategy that has been dormant in the current flat regime for ~90 days, and there is no signal in this dataset that the regime is about to change.

## Verdict

**Do not stand up funding-rate arb infrastructure.** If a future regime shift produces sustained positive funding (>0.005%/8h on BTC for ≥2 weeks), revisit. Otherwise, ignore.

## What I got wrong, for the record

In the last message before the sense-check I wrote:

> Funding-rate arb on BTC/ETH perps... collect the funding rate (currently 10-30% APY on BTC, occasionally negative which flips you short-spot-long-perp)... At $10-50k capital: $1-10k/year, low-skill, low-drama. This is the thing most retail quant setups should start with.

That was recall, not data. Every number in it is wrong for the current regime:
- "Currently 10-30% APY": actually −9%.
- "Occasionally negative": actually negative 47-51% of the time on a coin-flip basis.
- "$1-10k/year at $10-50k capital": actually break-even-to-negative net of fees.

The user caught it with a single "sense-check this" request. I should run these checks *before* pitching numbers going forward, not after.
