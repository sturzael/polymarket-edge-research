# Null results — what this project has ruled out

A running list of strategy theses that have been empirically disproven with data pulled during this project. Maintained so future-you can see the landscape without re-reading every memo and re-arguing every dead idea.

Each entry links to the primary write-up. Keep it honest. If a thesis is partially surviving, put it in the "survives so far" section at the bottom, not here.

---

## 1. Polymarket barrier-market mechanical tail-scalp (falsified 2026-04-19)

**The claim:** mechanically buy the far-from-money side of crypto barriers and ladders at implied prob ≥ 0.95, hold to expiry, collect near-certain pennies. Claimed P&L: $5-30k/month at $10-20k capital per `FINDINGS.md:272`; also `DEEP_DIVE.md` in `experiments/e9_wallet_competitor_intel/`.

**The test:** counterfactual across two top operators. `Respectful-Clan` (+$99k realized, apparent "successful bot") and `Impressive-Steak` (−$82k realized, same superficial strategy shape). Partition each wallet's barrier positions by `avgPrice` bucket. If the rule is real edge, it fires on Respectful-Clan's winners and filters Impressive-Steak's losers.

**The result:** the rule produces **identical +1.5% cashPnl ROI on the avgPrice ≥ 0.95 bucket for both wallets**, with realized P&L negative for both (−$71k Impressive-Steak, −$38k Respectful-Clan). All of Respectful-Clan's alpha is in two mid-band directional bets on BTC (avgPrice 0.30-0.70, +40.8% ROI on $525k gross), not in a systematic tail-scalp. The rule does not discriminate winners from losers — it is noise, not edge.

**Full write-up:** `experiments/e9_wallet_competitor_intel/COUNTERFACTUAL.md`

**Implication:** the `$5-30k/month` estimate in `FINDINGS.md:272` is unsupported. Do not shadow-copy Respectful-Clan. Do not deploy capital to mechanical tail-insurance on barriers/ladders.

---

## 2. Funding-rate arbitrage at retail scale in current regime (falsified 2026-04-19)

**The claim:** cash-and-carry on BTC/ETH perps pays 10-30% APY historically; "low-skill, low-drama"; "$1-10k/year at $10-50k capital."

**The test:** pull current funding rates + 90-day history from Binance USDM perps via `ccxt`; compute annualized yields against realistic Binance fees (0.25% round-trip across both legs).

**The result:**
- Current BTC funding rate: **−9.1% APY** (shorts pay longs). ETH: −16.1%. SOL: −8.1%.
- 90-day BTC mean funding: **−0.02% APY**. Median: +0.30%. p90: +6.2%. Positive 53% of periods (coin flip).
- 90-day ETH mean funding: **−1.23% APY**. Median −0.08%. Positive only 48.5% of periods.
- At median funding, fees exceed income on any realistic holding period. At p90, net ~4% APY after fees = $400/year on $10k — worse than stablecoin T-bill-backed yields (~4-5%).

**Full write-up:** `experiments/e11_funding_arb_sensecheck/README.md`

**Implication:** do not stand up funding-rate arb infrastructure. Revisit only if a sustained bull trend pushes funding persistently positive (>0.005%/8h on BTC for ≥2 weeks).

---

## 3. Polymarket above-K hourly ladder MM (falsified 2026-04-18)

**The claim:** `OPPORTUNITY_HOURLY_LADDER_MM.md` first-draft: balanced-probability MM in the middle of above-K digitals yields meaningful monthly revenue.

**The test:** Recon A pass against executable bid/ask on BTC + ETH above-K cohorts.

**The result:** 0 arbs across both cohorts at executable quotes. All apparent edge came from comparing against `lastTradePrice` (stale). Real market structure: penny stubs at 0.01/0.99 with high depth, real MM depth at 0.20 and 0.93, nothing in the 73¢ band between — which is "free space" only in the sense that nobody's quoting there because the fills don't come.

**Write-up:** `docs/FINDINGS.md` section "FURTHER UPDATE ~16:35 UTC — Recon A kills the `above-K` MM strategy".

**Implication:** the hourly-ladder MM opportunity as originally framed doesn't exist. A smaller version may exist on multi-day above-K digitals during 6-24h pre-expiry; this remained "survives so far" until superseded by the more recent tail-scalp falsification above.

---

## 4. Long-tail non-crypto LP (killed 2026-04-18)

**Write-up:** `docs/FINDINGS.md` — "Long-tail non-crypto LP — killed". Short entry.

---

## 5. `|poly − outcome_bin|` as a signal-quality metric (falsified a priori 2026-04-18)

The original v2 plan used this as its core metric. User flagged that its expected value on a calibrated market is `2p(1−p)` — maximized at p=0.5, minimized by certainty. So the rubric "high err = strong signal" was inverted. Replaced with calibration curves, Brier score vs GBM benchmark, and lead-lag cross-correlation.

**Write-up:** `docs/FINDINGS.md` — "Analytical issues the user flagged in v2".

---

## 6. Polymarket crypto-barrier residual arb (falsified 2026-04-19)

**The claim:** buy the near-certain side of intraday BTC/ETH barrier markets (e.g. `bitcoin-above-76k-on-april-18`) at 0.95–0.98 when spot is already well past the strike. `experiments/e9_live_arb_scan/README.md` identified $18.3k capturable depth across 4 markets on 2026-04-18 and proposed holding to resolution for ~1% net EV. Strategy was slated for inclusion in the e12 paper-trade harness as a second account pair alongside sports_lag.

**The test:** e13's `04_sii_crypto_barrier_backtest.py` ran the exact entry rule (`last_trade_price > 0.95`, `hoursToResolution < 2`, ask ≤ 0.98) against the SII-WANGZJ on-chain Polymarket dataset (954M rows, 19-day fresh). Joined entries to realized outcomes.

**The result:** **n=5,220 entries. Notional-weighted net edge −63.44% at any fee assumption (fees are noise relative to crash losses). Crash rate 37.34%.** Notional sampled $890,716. Median hours-to-end 1.09.

The mechanism: when a crypto market trades at 0.97 with <2h to expiry, spot is necessarily close enough to the barrier that price isn't at 0.99. Crypto's realized 1–2% hourly volatility is sufficient to flip ~37% of these markets before resolution. The 3-cent "spread above 1.00" is the crash-risk premium, not edge.

**Full write-up:** `experiments/e13_external_repo_audit/findings.md` — Investigation 1d.

**Implication:** the strategy as designed destroys capital at −63% notional-weighted. The `e9_live_arb_scan/README.md` ~1% net EV figure was wildly optimistic. **Dropped from e12 paper-trade plan entirely.** Possible salvage: a much stricter entry filter (only enter when spot is ≥5% from strike, measured against external Binance spot bars) might rescue a subset of these markets. Requires external spot overlay and separate investigation — not on e12's critical path.

---

## Survives so far (as of 2026-04-19)

Not yet falsified; also not yet validated. Lower bar for inclusion than a null result, higher bar than a pitch.

- **Sports settlement-lag arb on Polymarket.** Identified in `docs/OPPORTUNITY_SPORTS_EVENT_LAG_ARB.md`. H3 (fees) empirically resolved: e13 measured zero on-chain taker fees across 143 sports post-resolution trades. Historical backtest (e13, n=47) shows +3.99% notional-weighted net edge, 14.4 min avg hold — directionally confirmed but sample-thin. H1 (flow-diffuse) partially contradicted at low sample (top-10 = 68%); deferred pending deeper rerun. Paper-trade validation via the e12 harness is the next gate; live capital deployment is conditional on positive paper results. See `docs/PLAN_E12_PAPER_TRADE.md`.

- **Stablecoin lending / DeFi-native T-bill-adjacent yield.** 4-8% APY at low operational complexity. Not an alpha strategy — just an alternative to cash. Worth knowing as a default baseline for comparing every other idea against.

---

## Meta: the failure mode to watch for

Every killed thesis above was initially introduced with high confidence (often "surely"). The pattern:

1. Idea proposed with a headline revenue number.
2. The number comes from pattern-matching to prior similar work, not from data pulled for this idea.
3. A data pull or counterfactual test, requested by the user in every case so far, falsifies the headline number.

The prompt that has worked best to break this loop is the user asking "sense-check this" or proposing a specific counterfactual. Absent that prompt, the default mode tends to preserve the headline number with increasingly elaborate scaffolding. See the tail-scalp falsification especially: three memos (`REPORT.md`, `DEEP_DIVE.md`, the master plan) had been written before the counterfactual test, and all three confidently claimed edge that the test immediately disproved.

Rule going forward: any pitch with a revenue number gets a data-pull sense-check *before* being written up, not after.
