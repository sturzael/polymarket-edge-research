# Polymarket crypto LP opportunity — refined after methodology critique

*Updated after second LM's critique + additional data pulls.*

## TL;DR

There's a plausible LP/market-making opportunity on Polymarket's crypto prediction markets, but **not where I first pointed**. The real shape:

- **"above-K" digital ladders** (hourly BTC/ETH/SOL): very low real volume (~$80–$200/strike/day steady-state). Not MM-viable alone.
- **Barrier markets** ("will reach X", "will dip to X"): real volume ($50k–$170k/day per market *cumulative*), but most of that volume is the settlement rush in the final hours. Steady-state current flow is much lower.
- **Multi-day "above K" digitals during the balanced-probability phase** (6–24h before expiry, last_trade ∈ [0.3, 0.7]) is the sweet spot — real depth at meaningful prices with >70¢ between bid-depth and ask-depth.

My original $4,500-16,000/mo estimate was **3-10x too high**, driven by three errors flagged by the second LM + the volume-attribution error I found tonight. **Realistic estimate: $300-2,000/month on $10k capital**, maybe $3-10k/month on $50k. Still interesting for an individual; not transformative.

## Three methodology bugs that the original writeup would have propagated

Credit to the second-opinion review. Each is a known class of MM-backtest error:

### Bug 1: "Historical fill at price P = I'd have filled at P" is false

If I had been posting a quote at 0.30 on an ETH-above-2400 market and a retail seller market-sells, the historical trade on the tape would reflect *different* prices than occurred in the actual market — because I wouldn't have been an observer of that fill, I'd have *been* the fill.

**Corrected framing:**
- "Tape-walking trades" (fill far from prevailing best bid/ask, evidence of a market order walking stubs) are the plausibly-interceptable ones.
- "In-the-spread trades" (fill close to the prevailing best b/a at that moment) already had a competing quote — we'd be fighting for queue position.
- This probably cuts the naive backtest's qualifying trade count by 60-80%.

### Bug 2: Adverse selection wasn't modeled — it's the whole game

Retail doesn't randomly trade at bad prices; they trade because they have a view (often informed by a recent spot move). If my bid at 0.30 gets hit, it's disproportionately because spot *just moved down in the last 10-30 seconds*. By T+10s, fair value may already be 0.22, not the 0.71 my model says.

**Corrected framing:** mark fills at `fair_value(fill_ts + 10s)`, not `fair_value(fill_ts)`. Apply a cancel-latency filter: fills only credited when spot hasn't moved >X realized-vol stdevs in the previous Y seconds (approximates the "I'd have canceled this quote before being picked off" behavior a live MM would have).

### Bug 3: Monotonicity arb signals were stale-print mirages

I flagged `P(>77000) = 0.95` vs `P(>76600) = 0.55` as a potential arb. That was `lastTradePrice` — a stale quote from some earlier trade, not executable.

**Executed the corrected sweep tonight:** sampled all above-K strikes for BTC (12 strikes) and ETH (11 strikes) on the 04:00 UTC cohort, at actual best-bid/ask (not lastTradePrice):
- BTC: 0 executable arbitrages
- ETH: 0 executable arbitrages

Result: **the static-arb angle is a mirage, as the reviewer predicted.** All monotonicity holds trivially at bid/ask (because every strike's book has ask=0.999 and bid=0.001 or 0.01 stubs).

## What the real book structure actually looks like

Concrete example: `ethereum-above-2400-on-april-18`, 12.5h to expiry, last_trade 0.71.

```
BIDS:              ASKS:
 0.01 @ $48,040     0.99 @ $48,011
 0.02 @ $13         0.98 @ $2,005
 0.03 @ $19,000     0.97 @ $19,010
 0.06 @ $17,000     0.95 @ $20
 0.07 @ $9          0.94 @ $17,008
 0.20 @ $12,750     0.93 @ $2,875
```

**Key observations:**
- Penny stubs at 0.01 / 0.99 are massive ($48k each) — free-lottery-ticket buyers + offloaders
- Real market-maker depth lives at deeper levels: **$12.7k bid at 0.20** and **$2.9k ask at 0.93**
- Nothing between 0.20 and 0.93 — **73¢ of untouched space at a market whose fair value is 0.71**
- Book changes between-level every 20-80s — MMs ARE active, just not quoting inside the 73¢ band

**This is the LP opportunity.** Post limit orders at say 0.55 bid / 0.80 ask. If retail walks the book, they hit you instead of the 0.20 or 0.93 levels. You capture the gap.

## Revised revenue estimate

With corrected methodology:

**Per-market, per 12h-before-expiry window:**
- Real flow: maybe $500-3000 through the whole book during balanced-probability phase
- Our quotes catch 10-30% of that (if we're faster than other opportunists)
- Gross capture: ~$50-900 on $10k of posted quotes
- Adverse selection cost: 30-60% of gross captured (fills happen more often right before bad moves)
- Net: $20-450 per market per cycle

**Across available markets** (BTC + ETH + SOL + XRP + SOL + DOGE daily/hourly "above K" and barriers, probably 30-60 live cohorts per day with balanced probability):

| Assumption | Monthly net |
|---|---:|
| Conservative (few cycles filled, high AS) | **$300** |
| Base case (mix of filled cycles, moderate AS) | **$800** |
| Upside (we get quick + AS is lower than I estimate) | **$2,000** |

At **$50k capital** this scales to maybe $3-10k/month — the number the reviewer suggested. **Not** the $16k/month my first draft implied.

## Remaining unknowns worth resolving before capital deployment

In the order the reviewer proposed:

### 1. Fee structure — $10 experiment ($5-10 at risk)
Place one $5 limit bid on an hourly "above K" market. Let it fill. Check the on-chain settlement for exact fee charged. Resolves `maker_base_fee: 1000` ambiguity. Cannot be answered any other way.

### 2. Executable-price monotonicity sweep — DONE
Ran tonight. 0 executable arbs across BTC + ETH 12-strike cohorts. Confirmed: no static arb business hidden in the ladder.

### 3. ETH and SOL cohort structure — DONE
Checked. ETH barrier markets show the same pattern (deep stubs at extremes, real depth in the middle at 20-80¢). SOL has fewer active barrier markets at any moment (1-2 balanced cohorts vs 5-10 on BTC).

### 4. Proper backtest methodology (revised)
Plan the full backtest with:
- Split tape-walking vs in-spread fills
- Queue-position modeling (assume we're behind any existing quote)
- Adverse selection penalty: mark fills at `fair_value(t+10s)`
- Cancel-latency filter: no fills during recent spot-volatility periods
- Waterfall P&L reporting: gross spread → minus AS → minus queue → minus fees → net

Budget: 6-10 hours of careful coding (not 4).

### 5. Paper run (2 weeks)
After backtest, live paper simulation against real book updates for 2 weeks. Quotes, fills, adverse selection — all measured against actual subsequent price paths. Gate to real capital: paper P&L within 30% of backtest P&L.

## Honest risks

1. **The edge may not survive when you actually quote.** Other opportunistic MMs show up and compete; spreads tighten to 5-10¢; your edge halves. This is the normal shape of edge decay.
2. **Adverse selection may be worse than modeled.** The $12.7k of depth at 0.20 exists because someone (probably a clever MM) wants to buy fallen knives cheaply. When they get filled, it's because spot just dipped. We'd be competing with informed capital.
3. **Polymarket regulatory / chain risk.** NZ access legal today, could change. Polygon chain halts possible. Cap exposure accordingly.
4. **Operational burden.** 30-60 live cohorts × managing inventory + cancels + fills × 24h = this is a real job, not set-and-forget.
5. **Polymarket fee structure may be unfavorable** until the $10 experiment resolves it.

## The meta-point from the reviewer (incorporated)

The right framing is: **look for boring operationally-heavy Polymarket products that pros skip**. The hourly "above K" ladder has this shape; so does the barrier market in its quiet hours; so do the long-tail political LP opportunities; so does UMA dispute arbitrage. Each is unsexy admin work that creates a moat. That's the lens going forward.

## Recommendation — tonight vs this weekend

**Tonight (sandbox-allowed, minimal effort):** this opportunity doc has been rewritten with the corrections. No code execution needed.

**This weekend, in this order:**
1. **$10 fee experiment** (20 min, $5-10 cost, resolves the biggest single unknown). This is a real trade — needs a funded Polymarket wallet.
2. **Properly-scoped backtest** (6-10h of coding) — all five methodology fixes applied.
3. **Decision point:** if backtest shows >$500/mo at $10k capital after all adjustments, build paper-trading bot.
4. **2-week paper run** before any real capital.

**What I will NOT do without explicit approval:**
- Place any real trade
- Spawn background collector processes
- Scale paper-test to real capital
- Run the naive (optimistic) backtest — the results would be misleading.

## Status

Opportunity downgraded from "$16k/month upside" to "$300-2,000/month realistic on $10k capital." Still interesting, with honest upside at $50k capital. Methodology corrected, executable-arb angle confirmed mirage. Fee experiment is the next step that unblocks everything else.
