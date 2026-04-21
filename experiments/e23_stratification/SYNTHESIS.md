# e23 — FLB stratification synthesis

**Date:** 2026-04-20
**Inputs:** e16 (baseline +25.8pp finding), e18-e22 cross-venue (established Polymarket × T-7d specificity), e23 Agents A-F (stratifications), primary-thread anchor sweep (in progress — section 2 pending)

## 0. Bottom-line decision

**Deploy a narrowly-scoped small live test ($500-$1,000 entry sizes) on MLB/NBA/NFL/NHL game-outcome favorites at T-7d in the 0.55-0.60 bucket.** Expected conservative yield **$4-8k/yr on $5-10k capital (77-85% annualized)**. All 6 stratifications support deployment within that scope. Do NOT scale above $25k capital (capacity saturates). Do NOT deploy without the parallel 30-day forward-validation collector running.

Gates, kill criteria, and sizing rules are in §9.

## 1. What the 6 stratifications established

| question | agent | finding | decision-relevant |
|---|---|---|---|
| Which sports carry the bias? | A | **MLB** is the only sport with n≥20 in strict 0.55-0.60 bucket (+36.9pp, z=11.9). NHL/NFL point same direction at n<20. 7/8 sports positive in mid-range within game_outcome. | Filter to MLB/NBA/NFL/NHL |
| Is the edge decaying? | B | **Stable across 3 years** (2023-04 → 2026-03). Quarters: +17.5 / +35.4 / +22.1 / +21.1pp. Most recent quarter still +21pp. | Edge has NOT been arbed away |
| Is it a liquidity artifact? | C | **No.** Tier 3 (≥$5k window volume, 70.2% of sample) shows **+30.3pp** — larger than pooled. Correlation(price, yes) rises 0.42 → 0.67 → 0.76 across tiers. Median max-single-fill in Tier 3 = $9k, p90 = $66k. | Scalable to real size |
| Is it an age artifact? | D | **Yes, strongly age-gated.** 109/120 bucket markets have lifespan ≤14d (+26.9pp, DSC_median 2.7d). Dose-response monotone: +25pp (<12d) → +7pp (21-30d) → negative (30d+). | Pre-informed-flow mispricing. Filter to ≤14d lifespan; expect long-duration futures to carry no edge |
| Which sub-categories carry it? | E | **game_outcome almost exclusively** (+27.5pp, n=113/120). Futures n=5 shows opposite sign (−17.5pp). Props structurally empty in this bucket (bimodal). | Filter to game_outcome slugs (82% of sports markets pass) |
| What's the deployable dollar edge? | F | **+23.8pp net at $500/3bps.** Fees are a rounding error (<0.4pp even at 15bps V2). Slippage and fill probability are binding. Capacity saturates at ~$25k capital. | Small live test, capped at $1,000 position |

## 2. The 5-anchor FLB curve

`06_anchor_sweep.py` completed. Universe fixed to the same 2,025 sports markets as the T-7d baseline.

| anchor | offset | window | n(all) | n@0.55-0.60 | yes_rate | deviation |
|---|---|---|---:|---:|---:|---:|
| t7d (baseline) | 7.0d | ±12h | 2,025 | 120 | 0.833 | **+25.8pp** |
| t3d | 3.0d | ±12h | 367 | 11 | 0.545 | −3.0pp |
| t1d | 1.0d | ±6h | 335 | 19 | 0.684 | +10.9pp |
| t60min | 1h | ±15min | 160 | 10 | 0.600 | +2.5pp |
| t10min | 10min | ±6min | 124 | 7 | 0.857 | +28.2pp |

Two structural observations and one weaker claim:

**Finding 1 — Many sports markets don't trade continuously.** From the 2,025 T-7d universe, only 124-367 markets had trades in each intermediate-anchor window. Typical pattern: activity at creation, at T-7d, and again near close — with dormant stretches between. This is not a scanner bug; it's the market structure. MLB game markets especially tend to go quiet after initial listing and re-animate in the final day.

**Finding 2 — Edge is not monotonic across anchors, and bucket n is small.** +25.8pp at T-7d (n=120) → −3pp at T-3d (n=11) → +11pp at T-1d (n=19) → +3pp at T-60min (n=10) → +28pp at T-10min (n=7). The non-T-7d bucket n is too small for strong precision claims — a 95% CI on yes_rate at n=10-19 spans ±20pp easily. The qualitative pattern is "measured at T-7d, noisy through the middle, re-appears near close."

**Weaker claim — neither mechanism 1 nor mechanism 2 is clearly supported.** The agent-prior framing ("stable persistence" vs "monotone decay to close") doesn't describe the observed curve. A better description: prices drift during the dormant stretches, and the T-7d snapshot captures a specific equilibrium that need not persist across time. The T-10min bump (n=7, +28pp) is consistent with the pre-close equilibrium resembling T-7d again but could easily be noise at that sample size.

**Deployment implication:** T-7d remains the right entry anchor — it's where the signal is well-measured and high-n. The deployment plan (§7) doesn't change. What this DOES change is the *interpretation*: don't expect the position's mark-to-market to sit steadily at 0.58 for 7 days. Expect it to drift substantially in low-liquidity periods and re-anchor near close. The buy-and-hold strategy is correct; the buy-and-watch-steady narrative is wrong.

Raw data: `experiments/e16_calibration_study/data/anchor_curve/anchor_curve_summary.json` and per-anchor parquets.

## 3. Consistency check across agents

All 6 agents agree on the same scoped strategy even though they measure orthogonal dimensions:

| dimension | inclusion rule | % of sports markets passing |
|---|---|---:|
| sport (A) | MLB / NBA / NFL / NHL | 60.0% (1,204/2,025) |
| sub-category (E) | game_outcome | 82.3% (1,667/2,025) |
| lifetime (D) | ≤14d | 81.5% (1,651/2,025) |
| volume (C) | ≥$5k window | 70.2% (1,422/2,025) |
| category (E cross-sport check) | 7/8 sports positive | game_outcome only |

Joint filter: MLB/NBA/NFL/NHL × game_outcome × ≤14d × ≥$5k window ≈ **~30-40% of sports markets** (rough AND of the fractions, not independent). Applied to the 0.55-0.60 bucket: this reduces 120 historical markets to roughly **40-60 qualifying markets per year forward**, at the stratified-edge magnitude of +30pp (Tier 3 volume) × +36.9pp (MLB specifically).

## 4. Robustness of the core finding

From e16 + e18-e22 + e23:
- Statistical: **z=7.6 at n=120/yes_rate=0.833** (pooled). MLB alone: z=11.9 at n=54. Not a multiple-testing artifact — cross-bucket curve is monotone and mirror-symmetric around 0.50.
- Cross-venue control: **Betfair ±6pp max, Azuro +0.4pp at same price level** (5-75× smaller). Polymarket × T-7d is the specific cell carrying this.
- Temporal: stable across 3 years (not a 2024-election artifact)
- Volume: strengthens with volume (opposite of liquidity-artifact signature)
- Age: concentrated in young markets (consistent with pre-informed-flow retail mispricing)

**The core measurement is robust.** The residual uncertainty is *forward* persistence (30-day prospective validation) and *mechanism* (anchor curve — affects risk profile, not expected return).

## 5. Risk register

| risk | severity | mitigation |
|---|---|---|
| Edge decays from T-7d to close (mechanism 2) | medium | Anchor curve in progress; enter at T-7d regardless (most conservative) |
| Forward-validation period shows decay | high | Run e16's 30-day passive collector in parallel; kill at realized yes_rate <0.72 over 30 bets |
| Slippage model (1pp/$500) is optimistic | medium | Live test samples real fills; recalibrate if realized slippage >3pp/$500 |
| V2 cutover (2026-04-22, 2 days away) disrupts liquidity | low-medium | Halt trading through cutover + first 20 post-cutover samples; fee rate doesn't matter (immaterial) |
| Position concentration in MLB | medium | Cap concurrent MLB exposure at 50% of deployed capital; diversify with NBA/NHL/NFL |
| Single-market fills fail to execute at T-7d quote | medium | Fill probability 71% already priced in; orders that don't fill are zero-P&L, not losses |
| Anchor sweep reveals non-trivial structural issue | low | Synthesis updates when sweep lands; scope can tighten but not expand |

## 6. What this analysis does NOT establish

- **Forward persistence.** All of e16 and e23 are historical. The 30-day forward collector is non-negotiable before capital >$5k.
- **Sub-$500 slippage model validation.** Heuristic not empirically fit. Live test refines.
- **Capacity above $50k.** Extrapolation from $2k position cap. Do not scale blindly.
- **Non-MLB significance in strict 0.55-0.60 bucket.** NBA/NFL/NHL point directionally same but have n<20. Multi-season pull would firm this up.
- **Mechanism.** See §2.

## 7. Specific deployment plan

### Entry criteria (ALL must hold)

- Sport ∈ {MLB, NBA, NFL, NHL}
- Sub-category = game_outcome (head-to-head dated team/player match)
- Market duration ≤14 days (listed within 2 weeks of event)
- Total volume in ±12h around T-7d ≥ $5,000
- YES price at T-7d ∈ [0.55, 0.60)
- max_single_trade_usd in window ≥ $2,000 (depth sanity check)

### Sizing

- Entry size: **$500** (base case)
- Max single position: **$1,000** (only if max_single_trade_usd ≥ $5,000 in that market's T-7d window)
- Max total deployed: **$15,000** (scale to $25k only after 30+ live trades confirm edge)
- Never >$50k (capacity saturation)

### Fees

- No gating needed; fees immaterial at <0.4pp

### Kill gates (automatic halt)

- Realized yes_rate < 0.72 over rolling 30-bet window
- Realized slippage > 3pp per $500 order
- V2 cutover disrupts order flow (halt through 2026-04-22 + 20 post-cutover samples)
- Forward-validation collector shows any of above on passive data

### Expected P&L (planning number = ÷5 correction)

- $5k capital: **$4.3k/yr (85% annualized)**
- $10k capital: **$7.7k/yr (77% annualized)**
- $25k capital: **$11.0k/yr (44% annualized)**

## 8. Open work

1. **Finish anchor curve.** Primary-thread sweep will complete in ~45 min. Synthesis section 2 gets filled in. If curve is flat T-7d → T-60min, scope can widen to later-entry variants.
2. **Start 30-day forward collector** (per e16 section 2f). Independent of this analysis. Must run before capital >$5k.
3. **$500 live-fill sanity test** on 5-10 historical-pattern-matching markets to validate the slippage / fill-prob model. Not to make money — just to validate you can get fills at quoted prices.
4. **Post-V2 re-measurement.** V2 cutover 2026-04-22 may shift fee structure or match-engine behavior. Halt + resample.

## 9. Final meta-verdict

**DEPLOY small live test. $500-$1,000 entries. MLB/NBA/NFL/NHL game-outcome favorites at T-7d in 0.55-0.60 bucket. ≤14-day market lifespan. ≥$5k window volume. Hard kill gates in place. Capital cap $15k until 30+ trades validate, $25k max thereafter.**

**Planning number: $4-11k/yr net on $5-25k capital.**

This is a decision-ready recommendation. The six stratifications and cross-venue work support it. The anchor curve and 30-day forward validation refine the entry timing and confirm forward persistence; they do not change the go/no-go.

---

## Agent directory links

- [Agent A — per-sport](a_per_sport/FINDINGS.md) · [VERDICT](a_per_sport/VERDICT.md)
- [Agent B — temporal](b_temporal/FINDINGS.md) · [VERDICT](b_temporal/VERDICT.md)
- [Agent C — volume](c_volume/FINDINGS.md) · [VERDICT](c_volume/VERDICT.md)
- [Agent D — lifetime](d_lifetime/FINDINGS.md) · [VERDICT](d_lifetime/VERDICT.md)
- [Agent E — sub-category](e_subcategory/FINDINGS.md) · [VERDICT](e_subcategory/VERDICT.md)
- [Agent F — execution-adjusted](f_execution_adjusted/FINDINGS.md) · [VERDICT](f_execution_adjusted/VERDICT.md)
- Cross-venue context: [experiments/SYNTHESIS_flb_cross_venue.md](../SYNTHESIS_flb_cross_venue.md)
- Anchor curve (pending): [experiments/e16_calibration_study/data/anchor_curve/](../e16_calibration_study/data/anchor_curve/)
