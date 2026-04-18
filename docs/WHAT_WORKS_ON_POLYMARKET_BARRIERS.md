# What actually works on Polymarket barrier markets (and what doesn't)

*Last updated: 2026-04-19. Consolidates findings from e1–e10 experiments and wallet-intelligence deep-dives. Supersedes the deployment-oriented master plan as the primary reference; the plan can be re-derived from this once a direction is chosen.*

## One-paragraph summary

Three distinct edges exist on Polymarket crypto barrier markets, with very different risk profiles, scale, and replicability. Only one is genuinely a "strategy we could copy cleanly." The others are either regime-dependent wrapped in arb costume, or speed-dependent in ways that favor incumbent bots. No other opportunity (MM, updown HFT, long-tail LP, sports resolution-lag at NZ latency) survives close scrutiny.

## The three edges, ranked by how honest the label "arbitrage" is

### Edge 1 — Tail-insurance: buy NO at 0.95+ on barriers where spot is ≥15% from strike

**What it is:** Polymarket lists barriers like "Will BTC reach $90k in April?" When BTC is $77k with days to expiry, the NO outcome is mechanically near-certain. The NO-side book has a few asks at 0.94-0.98 (retail liquidating, mechanical hedging exits). Lift those asks, hold to UMA resolution, collect $1.

**Who runs it, at what scale:**

| Wallet | Tail-insurance notional | Other activity | Net result |
|---|---:|---|---:|
| **Austere-Heavy** | **$324k** | $40k lottery tickets | +$25k over 28 days |
| Respectful-Clan | $30k | $240k+ momentum overlay | +$334k* (overlay-driven) |
| Impressive-Steak | large but at wrong entry | — | **−$82k** |

*Respectful-Clan's P&L is dominated by the momentum overlay, not the tail-insurance part.

**Evidence it's genuinely regime-resilient (e10 backtest):**
- Tested on 641 historical resolved barrier markets (Oct 2025 - Apr 2026)
- At 15% distance threshold (spot ≥15% from strike at T-30min), rule fires on 57 markets
- **0 of 57 resolved YES (100% win rate)** — across UP (16), FLAT (22), DOWN (19) regimes
- Every one of the 34 YES-winners in the broader sample was <15% from strike — the distance filter cleanly excluded all flip cases

**Gross edge:** 5.3% per trade at 0.95 entry, 7.5% at 0.93, 3.1% at 0.97. After plausible 1-2% round-trip fees: 3-5% net per trade.

**Frequency:** 0.5 qualifying markets/day in our backtest sample; probably 2-10/day in the live universe.

**Realistic monthly income for a clean copy at $10k capital:**
- Impressive-Steak shows this strategy can lose $80k+ if threshold is wrong (they buy at 0.80 median)
- Scaling Austere-Heavy's numbers: they made $58k realized on ~$300k deployed over 28 days = 6.7%/month gross
- At $10k: 6.7% = $670/month. After fees, maybe $400-600/month net.
- ÷5 discipline rule says probably less. Realistic: **$200-800/month on $10k**.

**Key risks not in the backtest:**
- True bull-market stress test (Jun-Oct 2025 data missing from our sample)
- Current fee structure on Polymarket (unresolved)
- Fill feasibility at 0.95 in live markets (our backtest assumed we could fill)

**Is it replicable?** Yes, the simplest of the three edges. Requires Polymarket account, USDC on Polygon, order-placement bot, and a rule engine that computes spot-distance-from-strike every minute.

### Edge 2 — Momentum-directional: buy YES on "reach X" barriers after BTC rallies +0.5% in 4h

**What it is:** Respectful-Clan's biggest P&L driver. When BTC just rallied, buy YES tokens on barriers asking "will BTC reach [higher strike]?" at market prices of 0.35-0.50. Ride momentum continuation.

**Evidence from Respectful-Clan's 223 reach-YES trades:**
- 215 (96%) happened after BTC rallied +0.5%+ in the preceding 4 hours
- Median entry price: 0.46
- Total notional: $141,654
- This represents 40%+ of their total capital deployed

**Reaction latency (p50 24s, p90 54s):** Bot is fast but not HFT-fast. A VPS-hosted bot with sub-second Binance feed could beat Respectful-Clan to the same trades.

**Is it an arbitrage?** No. It's a **directional bet on BTC continuation**. If BTC rallies and then reverses, Respectful-Clan's $141k of "reach" YES positions collectively lose. They just happen to have been right recently.

**Regime dependence:** Extreme. The same strategy in a sustained bear rally would look spectacular; in a rangebound market it bleeds.

**Would we copy it?** No, because:
1. It's not an edge, it's a view
2. Copying requires having the same BTC view Respectful-Clan has
3. $99k realized in 38h includes this plus tail-insurance and we can't decompose cleanly
4. Austere-Heavy doesn't run this strategy and their book behaves differently

**But front-running it might be an edge.** If Respectful-Clan reliably buys reach-YES 24s after +0.5% BTC rally:
- Detect BTC cross at T
- Place YES buy at T+0.1s (before them)
- They arrive at T+24s, their buy presence pushes price up
- Sell to them at the inflated price, capturing 2-5¢ per share

This is genuinely new but untested. Feasibility depends on:
- Whether their trades actually move the market (need trade-sequence analysis)
- Whether other bots already do this (likely yes for the most obvious cases)
- How much capital Respectful-Clan commits per trade (they trade at $37 median, not huge)

### Edge 3 — Deep-OTM lottery tickets: buy YES at 0.05-0.20 on barriers

**What it is:** Austere-Heavy's side strategy. Barriers with tiny implied probability (e.g., "will BTC reach $100k this week" at 0.08) occasionally pay off. Buy cheap, diversify across many, accept that most expire worthless.

**Austere-Heavy's sample:**
- 916 BUY YES trades, median price **0.18**
- 80%+ on barrier markets
- P&L contribution: mostly unrealized; currently **−$33k** MTM on their open book

**Is it an edge?** Unclear. At 18¢ entry:
- If realized probability is 20%+: expected profit
- If realized probability is 10-15%: expected loss

Historical data suggests realized probabilities on deep-OTM barriers are 5-10% — so Austere-Heavy's entries at 18¢ are probably slightly negative EV on average, with occasional big winners.

**Is it replicable?** Technically yes but not advisable:
- High variance (most positions lose 100%, a few win 5x)
- Requires large diversified book ($300k+) for the distribution to smooth out
- At $10k capital, would be gambling, not investing

## What doesn't work (explicitly killed)

1. **Market-making balanced-probability barriers.** Pro MMs already quote inside 2-3¢ with 30s reaction. No room for laptop/VPS competitor. (Confirmed in Recon A: e9.)
2. **5m updown speed-arb.** 44% of arb flow captured in first 10s. Only US-East-colocated HFT can compete. (Confirmed in e1, e4, e8.)
3. **Hourly `above-K` ladder MM.** Volume is $82/strike/day steady-state, not the $233k I initially misread. Wrong scale. (Confirmed in e9 live-scan corrections.)
4. **Long-tail non-crypto LP.** Median spread 3¢ (pros already there); wide-spread markets have $0 volume. (Confirmed in e9 broader scan.)
5. **Post-certainty barrier arb** (buy winning side after nominal end). Arb is fully taken; winning side has no asks at <0.99 by the time market passes end_ts.
6. **Sports resolution-lag arb from laptop/NZ.** Real opportunity exists ($600k/day flow, 3.4% edge, 11.7min windows) but requires game-end detector + matching-to-Polymarket infrastructure. Shelved for Phase 4.
7. **UMA dispute arb.** 0 disputes in a 1000-market sample. Extremely rare; not worth dedicated infrastructure.

## What we'd still need to validate before deploying capital

Even the cleanest edge (Edge 1 — tail-insurance) has unknowns that would matter for live trading:

1. **Polymarket fee structure.** `maker_base_fee: 1000` and `taker_base_fee: 1000` in unknown units. Could be zero, could be 1%. Must resolve via one $5 live trade.
2. **Realistic fill price.** Our backtest assumed 0.95 entries. Live markets may rarely show 0.95 asks for more than a few seconds. Live paper-trading would measure this.
3. **True bull-market regime behavior.** Our e10 sample only covers Oct 2025 - Apr 2026, mostly declining BTC. Need Jun-Oct 2025 barrier data to stress-test.
4. **Adverse selection.** Who is selling at 0.95 when the outcome is mechanically determined? If it's informed sellers (know something we don't about resolution criteria or oracle timing), the 100% win rate collapses.

## What this conversation has produced, as artifacts

**Living research:**
- `probe/probe.db` — 17h of market-structure reconnaissance, 1,316 resolved markets with final-minute trade data, 7,724 hourly bars × 3 assets
- `experiments/e10_regime_stratified_backtest/data.db` — 714 resolved barriers + 2,101 minute bars + Austere-Heavy's 3,500 trades
- `experiments/e9_wallet_competitor_intel/data/` — Respectful-Clan's 2,000 trades, Austere-Heavy's 3,500 trades, 750-wallet barrier participation table

**Methodology (saved in persistent memory):**
- Rule 1 — ÷5 all monthly revenue estimates before decision
- Rule 2 — Write the counter-memo from the same data before acting
- Applied: first estimate was $5-30k/mo, got corrected to $200-800/mo after controlling for regime and decomposing strategies

**Opportunities documented:**
- 7 edges investigated, 6 killed, 1 surviving
- The 1 surviving edge is ~10× smaller than initial estimates

## The honest meta-finding

**What actually works on Polymarket barriers:** a narrow, low-frequency, operationally-intensive tail-insurance strategy at $200-800/month expected income on $10k capital, conditional on unresolved fee/regime/fill unknowns. Everything flashier is either someone else's directional bet being mistaken for arbitrage, or a speed game we can't win.

**What this means for the user:** the conversation's journey from "find massive returns" to "maybe $400/month after methodology rules" is the *correct* trajectory. The optimistic first-pass estimates were produced by undisciplined analysis and corrected by repeated counter-memo discipline. That process is the actual value of the work, not the strategy itself.

**If the user deploys capital:** do the fee test, run the Austere-Heavy-shape strategy at $500-1000, measure for 3-4 weeks against a regime shift, scale only if numbers match.

**If the user doesn't deploy capital:** the accumulated research is reusable as a methodology template for future opportunity analysis in adjacent spaces (other prediction markets, different venue structures, equivalent strategies on Kalshi/Limitless/etc).

**Either way:** the synthesis holds. Further analysis of the same data won't reveal a materially better edge; it'd just refine the numbers on Edge 1.
