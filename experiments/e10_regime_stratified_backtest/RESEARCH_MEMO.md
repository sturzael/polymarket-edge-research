# Research memo: is the Polymarket barrier tail-insurance strategy regime-dependent?

**Commissioned:** 2026-04-19, in response to LM critique that the Respectful-Clan strategy evidence came from a single favorable regime and the "buy NO at 0.95 on reach-upside barriers" pattern might collapse when BTC reverses.

**Frame:** this is a research exercise, not a gate to capital deployment. The user is learning what's actually there.

## Method

1. Gathered 1,081 unique `condition_id`s for Polymarket crypto barrier markets from the wallet-intelligence dataset (Respectful-Clan + barrier_trades.jsonl). Covers Jun 2025 – Apr 2026.
2. Fetched each market's resolution outcome via CLOB `/markets/<cid>`. 714 resolved cleanly (YES/NO), 33 unresolved, rest had unparseable metadata.
3. Fetched hourly BTC/ETH/SOL OHLCV from Binance for the same period (7,724 hourly bars per asset).
4. For each resolved market, computed:
   - **Spot at T-30min** (entry decision proxy)
   - **Distance from strike**, signed in NO-favoring direction (reach: `(strike − spot)/spot`; dip: `(spot − strike)/spot`)
   - **Regime at T-12h**: trailing 24h log return of the underlying. `UP > +1%`, `DOWN < −1%`, else `FLAT`.
5. Applied threshold sweep on the entry rule. For each threshold, measured win rate stratified by regime.

## Finding 1 — The rule IS regime-resilient in our sample

| Distance threshold | Rule fires (n) | NO wins | YES losses | Win rate |
|---:|---:|---:|---:|---:|
| 3% | 541 | 536 | 5 | 99.1% |
| 5% | 446 | 443 | 3 | 99.3% |
| 7% | 332 | 329 | 3 | 99.1% |
| 10% | 179 | 178 | 1 | 99.4% |
| 12% | 109 | 108 | 1 | 99.1% |
| **15%** | **57** | **57** | **0** | **100.0%** |
| 20% | 19 | 19 | 0 | 100.0% |
| 30% | 4 | 4 | 0 | 100.0% |

**At 15% distance threshold, 57 markets over 4 months fired the rule; 0 resolved YES. Across 3 regimes.**

| Regime at T-12h | n | NO wins | YES losses | Win rate |
|---|---:|---:|---:|---:|
| UP (+1%+) | 16 | 16 | 0 | **100%** |
| FLAT (±1%) | 22 | 22 | 0 | **100%** |
| DOWN (−1%−) | 19 | 19 | 0 | **100%** |

The UP regime is the one the critique flagged as the concern — "what if BTC is rallying?" Our 16 UP-regime trades all won. That's the evidence the critique asked for, inside our sample.

## Finding 2 — The critique was right about unfiltered markets

All 34 YES-winning markets had **distance from strike < 15%** at T-30min. The rule correctly filtered every one out.

Distance distribution of YES-winners (markets where our rule said "skip"):
- min: −7.9% (spot had already crossed strike)
- median: 0.3% (spot right at strike)
- max: 14.0% (a near-miss; at 15% we'd include it)

In other words: **everything that flipped was close to the strike at decision time**. Deep-OTM tail positions (15%+ away) never flipped in our 4-month sample. The critique's worry about "informed sellers" sitting at 0.95 on markets that genuinely still have 5-15% crash risk appears to be *exactly correctly captured* by the 15% distance filter.

## Finding 3 — Gross edge is material, but fees eat into it

Edge per $ invested (pre-fees, gross), by entry price:

| Entry price | Threshold 15% | Threshold 10% |
|---:|---:|---:|
| 0.90 | +11.1% | +10.5% |
| 0.93 | +7.5% | +6.9% |
| 0.95 | **+5.3%** | **+4.7%** |
| 0.97 | +3.1% | +2.5% |

At a realistic 0.95 buy price with 15% distance filter: **+5.3% gross per trade**. At 1% round-trip fee: +4.3% net. At 2%: +3.3% net.

## Finding 4 — The 15% threshold is frequency-limited

57 qualifying markets over ~4 months ≈ **0.5 markets per day** that fit our strictest rule.

At 10% threshold: 1.5/day. At 5%: 3.7/day. At 3%: 4.5/day.

But our sample only counts markets that appeared in Respectful-Clan's and related wallets' histories, not the full Polymarket universe. Live observation (e9 live-arb scan) saw 4 simultaneous qualifying arbs at one moment, so the actual addressable universe is larger than our 0.5/day backtest implies.

Still: **the safe 15% threshold is a low-frequency strategy**. Earning $1000/month at $100/trade requires hitting 10+ trades/week, which means either (a) relaxing the threshold (accepting ~1% loss rate at 10%) or (b) the live universe containing more markets than our backtest sample implies.

## Finding 5 — Important sample limitations (the part that could change everything)

The data is biased toward the recent BTC downtrend. What we actually tested:
- **Spot range covered:** BTC ~$105k (Jun 2025) → $77k (Apr 2026). Mostly a declining trend with fluctuations.
- **Markets actually in sample:** 641 of 714 are from Jan-Apr 2026. Only ~30 markets from Oct-Dec 2025.
- **UP regime markets (16 at threshold 15%):** from Jan-Apr 2026, not from a 2025 bull-market rally.

The "UP regime" we tested is *a weak uptick within a broader downtrend*, not a sustained multi-day rally that could push spot toward previously-safe strikes. Specifically:
- We did not observe what happens during a +10% 24h rally against a "reach" barrier that was 15% OTM at the start
- We did not observe what happens in a bear-market capitulation against a "dip-to" barrier

**The 100% win rate is real for the conditions sampled but should be treated as an upper bound, not a guarantee.** A fully bull-market-tested version of this study would require barrier markets from Jun-Oct 2025 (when BTC was rallying), which we don't have in the wallet-intelligence dataset.

## What this means for the strategy's framing

**It's not regime-dependent in the sense the critique worried about** — the rule's distance filter appears to correctly exclude markets where the outcome is close-to-strike and therefore regime-sensitive. The remaining 15%+ cases are genuinely mechanical.

**But it's frequency-limited** and the sample doesn't cover the strongest stress tests (true bull-market rallies).

**Honest estimate with all this considered:**
- Expected per-trade net edge: **3-5%** after fees
- Expected loss rate at 15% threshold: **0-3%** (our 0/57 is likely optimistic; real distribution probably 1-3 per 100)
- Qualifying opportunity count: uncertain. 0.5/day from backtest, possibly 5-20/day from live universe scan.
- Monthly expected return at $100/trade, 10 trades/day, 4% avg net edge, 25 days: **~$1,000** if addressable flow exists
- Risk: a rare outlier event (1 loss in 100) costs 95¢ per share vs 3-5¢ edge → 19-30 trades to recover from one loss

## What the critique got right and what it got wrong

**Right:** The evidence base was thin. 38 hours of one operator in a favorable window is not validation.

**Wrong (at least in our sample):** "a buy-NO-on-reach-upside strategy eats the inverse loss when regime flips." It didn't, at the 15% distance threshold. The distance filter appears to do real work decoupling the strategy from regime direction.

**Still open:** we haven't tested a true bull rally scenario. If the strategy has a hidden regime-dependence in extreme regimes, this sample wouldn't catch it.

## What I'd actually conclude

1. The strategy is **more robust than the critique suggested** but **less conclusive than a full validation would require**.
2. **Deploying capital based on this alone is still not warranted.** The sample limitations mean the 100% win rate is likely optimistic.
3. **If you were going to deploy** (not the stated goal), you'd want (a) additional wallet shadowing across the next 4-8 weeks covering actual regime shifts, (b) a live paper run to measure adverse selection and fill rate, (c) a hard stop-loss rule that triggers if any 15%+ distance position goes against you within 30 min of entry.
4. **As research:** the finding that the 15% distance filter cleanly decouples the rule from regime direction is genuinely informative. It explains *why* Respectful-Clan's strategy isn't trivially regime-dependent even though it superficially looks like a trend-conditional bet.

## Appendix: raw numbers

- Total cids gathered: 1,081
- Resolved cleanly: 714
- With parseable metadata + spot data: 641
- Crypto: BTC 422, ETH 140, SOL 79
- Kinds: reach 302, dip 339
- Regimes observed: UP 248, FLAT 216, DOWN 177
- Rule-firing markets at 15% threshold: 57 (16 UP / 22 FLAT / 19 DOWN)
- Rule-firing losses: **0 / 57**

Database: `experiments/e10_regime_stratified_backtest/data.db`

## Suggested next research steps (if user wants to go deeper)

1. **Stretch regime coverage to mid-2025** by fetching barrier markets from gamma-api for Q2-Q3 2025 directly (not via the wallet dataset which under-sampled that period).
2. **Stress test by shifting spots +20%** and re-running — simulate an inverted-trend scenario.
3. **Measure actual fill feasibility** by checking whether the 15%+ distance markets had best-ask at 0.95 (our assumed entry) at T-30min, or whether asks were deeper.
4. **Compare our rule's output to Respectful-Clan's actual trades** — what fraction of their buys do we explain, and are their "non-rule" trades systematically losers?
