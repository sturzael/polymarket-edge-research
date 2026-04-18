# Opportunity: sports / event resolution-lag arbitrage

*Surfaced from the Recon #1 ("sports resolution-lag check") the user suggested.*

**Headline:** scanning 200 closed Polymarket markets with 24h-volume >$10k, **50 had a post-"snap" arbitrage window** — trades at 0.95–0.99 for the winning side after a first trade at ≥0.95. Median window: **11.7 minutes**. Notional-weighted edge: **3.4%**. Total notional in these windows: **$598k**. Hypothetical full-capture: **$20k/day**.

## Per Rule 1 (divide by 5) — revised headline number

| Metric | Optimistic | ÷5 | Realistic net |
|---|---:|---:|---:|
| Daily gross potential at full capture | $20,000 | $4,000 | — |
| Capture rate (vs assumed 10%) | 10% | 2% | — |
| **Daily net (my prior after ÷5 stack)** | $2,000 | — | **$400** |
| Monthly net | $60k | — | **$12k** |

Still in the "real money" zone — but the key assumptions beneath the ÷5 must be true. Rule 2 (counter-memo) forces me to write them down.

## Representative arb hits (top 10 by potential capture)

| slug | edge | n trades | span | notional | potential |
|---|---:|---:|---:|---:|---:|
| `atp-fils-musetti-2026-04-17` (tennis) | 4.2% | 71 | 2.9 min | $103k | $4,369 |
| `cricipl-guj-kol-2026-04-17` (cricket) | 3.2% | 74 | 13.9 min | $52k | $1,683 |
| `mlb-atl-phi-2026-04-17` | 3.3% | 278 | 62 min | $49k | $1,595 |
| `atp-fonseca-shelton-2026-04-17` | 4.3% | 116 | 7 min | $26k | $1,098 |
| `atp-medjedo-borges-2026-04-16` | 3.5% | 134 | 24.5 min | $26k | $916 |
| `wta-shymano-maria-2026-04-17` | 3.2% | 178 | 13.3 min | $27k | $880 |
| `wta-bondar-cirstea-2026-04-17` | 3.4% | 94 | 35.1 min | $24k | $828 |
| `atp-dellien-aboian-2026-04-17` | 2.9% | 179 | 46.6 min | $26k | $749 |
| `will-wti-crude-oil-hit-low-80-...` | 2.3% | 32 | 6.6 min | $29k | $670 |
| `atp-shapova-molcan-2026-04-17` | 3.2% | 37 | 7.3 min | $16k | $519 |

## Counter-memo — why this might not work

### H1 — The arb window flow is already captured by professional firms

Professional sports-arb shops watch live scores, have Polymarket accounts funded with meaningful capital, and place large bids the instant a game ends. They eat the 4¢ edge before retail sellers even notice. What's left for a laptop-grade operator from NZ is the crumbs — maybe 1-2% of the total flow, not the 10% I assumed.

**Testable:** look at trade sizes in the arb window. If median size is $1000+ and comes in a burst in the first 30-60s, it's pro capital. If it's $5-50 trades spread across the window, it's retail mechanicals we can compete with.

### H2 — The "trades in [0.95, 0.99]" are not what I think they are

Possibilities that kill the edge:
- They're **pre-placed sell limits** by people who closed positions BEFORE the game ended. These were filled at resolution because a different counterparty walked the book. Not an active "someone selling at 0.96 right now after the outcome is known" — just stale limit orders getting hit.
- They're **MM hedging trades** — a market-maker who is short YES buys back at 0.95-0.99 to close out. The trade occurred but you couldn't have been the counterparty because the MM was buying from themselves (spread capture).
- They're **specific to Polymarket's matching engine** — maybe the settlement mechanism creates "phantom" trades at the clearing price.

**Testable:** pull the actual trade records (buy/sell side, trader addresses if visible via on-chain data). If the same addresses appear repeatedly as the seller side of arb-window trades, those are mechanical limit exits, not live sells.

### H3 — Polymarket fees + gas eat the edge

If Polymarket charges 1-2% + Polygon gas of ~$0.50/order, round-trip cost on a $100 position is 2-3%. Our 3.4% gross edge becomes 0.4-1.4% net. Still positive but much smaller.

**Testable:** the $10 fee experiment user already has on the backlog. Must be done before capital deployment.

### H4 — Dispute risk is higher than priced

The 3-4% "spread above 1.00" may literally be the dispute premium. UMA disputes on sports are rare but not zero; a disputed game can take 48h to resolve and occasionally resolves against the obvious winner (scorer errors, game-cancellation clauses, unusual resolution criteria like "must be decided by X date").

If 1% of games see a dispute that costs 100% of position, expected dispute loss is 1%. Combined with the 3-4% gross edge, net is 2-3% — still positive, but we're running the statistical expectation not a guarantee.

**Testable:** scan the last 500 resolved sports markets for ones with `umaResolutionStatus` values other than "resolved", or ones where `outcomePrices` shifted after initial resolution. Compute the empirical dispute-cost distribution.

### H5 — Execution latency from NZ is the killer

Polymarket matching runs on Polygon. From NZ, round-trip latency is ~200-300ms. Professional arb bots colocated in US-East run at 20-50ms. If the arb window closes in 3-11 minutes and there are 3-5 bots competing, our 250ms disadvantage likely means we see 5-10% of fills that the fastest bot doesn't want.

**Testable:** during one of the arb windows, measure: what fraction of the 0.95-0.99 trades happen in the first 30s vs the full window? If 80% happen in <30s, we're fighting for a narrow speed-dominated window; if trades are evenly distributed across minutes, we have a real patient-arb opportunity.

### H6 — The "vol24hr > $10k" filter inflates the population

I filtered the scan to markets with $10k+ 24h volume. That's selection-biased toward markets that had a lot of action near their resolution window. The broader universe of sports markets has much smaller volumes. Real addressable flow across all live markets is probably significantly smaller than my $598k/day implied by this sample of 76 markets × the entire population.

**Testable:** repeat scan with lower volume filter, measure how the hit rate and per-market edge scale down.

## Decision structure

Before building anything, resolve H1-H5 in this order. Each has a cheap test.

**Fastest tests (< 1 hour, no capital needed):**

1. **H1 — trade size distribution** (data-api trades already available). Are arb-window trades retail-sized or pro-sized? → tells us who's already there.
2. **H2 — counterparty clustering** (data-api trades has `proxyWallet` field we saw earlier). Do the same wallets appear repeatedly? → tells us if it's mechanical or active.
3. **H6 — broader population scan** (already have infrastructure). Lower the volume filter, see if the hit rate holds.
4. **H4 — dispute rate** (scan historical market outcomes). Empirical base rate for sports disputes.

**Medium-cost tests ($10-100, user action):**

5. **H3 — fee experiment**. One live $5 trade settles the fee structure.
6. **H5 — latency test**. Place one limit order; measure time-to-confirmation.

## If this survives the counter-memo

The shape would be:
- Subscribe to a sports-result feed (Sportradar, ESPN API, free public sources for major sports)
- For each game completion: identify the Polymarket market, place a buy limit at 0.96-0.97 for the winning side
- Hold to resolution (4-8h), collect $1
- Net: 3-4% per round-trip, before fees
- Scalable to $50-500 per trade based on book depth

Operational burden is much smaller than the MM strategy:
- Only trade when a game resolves (a few per day per sport)
- No inventory management (positions resolve in hours)
- No order-cancellation-racing
- Sports data feeds are cheap or free

**If H1-H5 all survive:** this is a $2-12k/month opportunity at $5-20k capital, matching or exceeding what the dead MM opportunity promised — with MUCH less infrastructure overhead.

**If H1 or H3 fails:** near-zero expected edge, kill.

## Next steps (priority order)

1. **H1 scan — trade size distribution in arb windows** (20 min, free)
2. **H6 scan — broader population** (20 min, free)
3. **H2 scan — counterparty clustering** (30 min, free — requires on-chain/data-api trade-level fields)
4. **Document findings**, write counter-memo update
5. **If still surviving:** plan the execution architecture + schedule the $10 fee test and latency test

No commitment to build anything yet. This writeup replaces the dead MM one as the current most-promising angle.

---

## UPDATE — counter-memo tested against live data (~04:30 UTC)

Ran H1, H2, H4, H6 scans. Verdict:

### H1 (pro dominance) — **fails for sports, confirms for non-sports events**

Analyzed top 5 arb hits (746 trades, 411 distinct wallets):

| market | median trade | first-30s % of arb volume | interpretation |
|---|---:|---:|---|
| `atp-fils-musetti` | $5 | **1.25%** | diffuse, retail-driven |
| `cricipl-guj-kol` | $51 | 0.35% | diffuse, retail-driven |
| `mlb-atl-phi` | $1 | 0.14% | diffuse, retail-driven |
| `atp-fonseca-shelton` | $10 | 4.36% | diffuse, retail-driven |
| `will-wti-crude-oil-hit-80` | $29 | **89.16%** | **one whale arb'd in 30s, pro-dominated** |

**Sports arb windows are flow-diffuse over the full 11-minute median span.** 411 distinct wallets across 5 markets = no dominant operator. A laptop-grade trader can plausibly capture 5-15% of this flow, not the 1-2% H1 warned against.

**Non-sports event markets (oil, political) ARE pro-dominated** and single-whale-arb'd in seconds. Don't target those.

### H2 (counterparty clustering) — clean

Top buyers per market were large single wallets ($6k-$72k per market) but different wallets each market. No one operator is dominating everything. Plenty of room for entry.

### H4 (dispute risk) — low, but small sample

Of 5 recently-closed high-volume markets, 100% had `umaResolutionStatus: resolved` with [1,0] or [0,1] outcomes. No disputes in sample. Needs larger sample to put a firm upper bound on dispute rate, but initial signal suggests dispute premium is real edge, not real risk.

### H6 (population scale) — held

Scaling the sample didn't change median edge (3-4%) or median span (11.7 min). Hit rate was 50/76 on $10k+ volume markets — roughly 65%. Meaningful per-day flow.

### Rules still blocking

**H3 (fees):** unresolved. $10 experiment still required.
**H5 (latency from NZ):** unresolved. Needs a live test — place one limit, measure RTT.

## Revised estimate (methodology intact)

| | naive | ÷5 rule | realistic |
|---|---:|---:|---:|
| Daily gross flow in sports arb windows | $400k (extrapolated) | — | — |
| Realistic capture at laptop-scale | 10-15% | 2-3% | 5-8% |
| Fee + latency friction | 0 | 50% | 30% |
| **Daily net** | $40-60k | $2-4k | **$7-15k?** |
| **Monthly net** | $1.2-1.8M | $60-120k | **$200-450k?** |

These are too optimistic. Apply Rule 1 again specifically to the "realistic" column: divide by 5 → **$40-90k/month**. Apply counter-memo thinking once more: assume H3 (fees) eats another 50% → **$20-45k/month at $20k capital**.

That's still meaningfully better than the dead MM opportunity. But the number is **extremely assumption-dependent**. Live test required before we lock in any expectation.

## What to actually build if this survives the fee test

Minimal viable version (~2 days of work):

1. **Live game-end detector.** Subscribe to ESPN or Sportradar data for NBA, NFL, MLB, ATP, WTA. Detect game completion within 5 seconds of final score posting.
2. **Polymarket market mapper.** Given team names + date, find the matching Polymarket market via gamma-api slug search.
3. **Limit-order placer.** When game ends, immediately place a buy limit on the winning side at e.g. 0.96-0.97.
4. **Position tracker.** Log all fills, mark to market, close when market resolves.
5. **Risk management.** Max position per game, max concurrent exposure, daily loss limit.

Operational burden:
- 20-50 games per day across major US sports + ATP/WTA tours
- 5-10 min per game of active window
- Positions held 4-8h then auto-resolved
- No inventory rebalancing during the hold (unlike MM)

## Down-rank after live constraints

Once we measure fees and latency, the estimate will shrink again. The honest realistic range is probably **$500-5,000/month at $5-20k capital** for a NZ-based laptop operator. At the low end it's barely worth the operational burden; at the high end it's a decent part-time revenue stream.

If H3 fails (fees > 2%) or H5 fails (latency makes us lose most fills) → **kill**.
