# Counter-memo: "here's why the MM opportunity doesn't work"

Companion to `OPPORTUNITY_HOURLY_LADDER_MM.md`. Required by the research-methodology rule: before acting on a "this works" finding, write the counter-memo from the same data.

**Claim being counter-argued:** Polymarket hourly "above-K" / daily "above-K" ladders and balanced-probability windows offer a $300-$2,000/month LP opportunity on $10k capital.

## ⚠️ Update after Recon A (4-min book + spot observation): H1 CONFIRMED. Strategy killed as written.

Observed on ETH-above-2400 (11.5h to expiry, last=0.65) over 4 min 2026-04-18 16:32 UTC:

| time | ETH spot | rational bid | rational ask |
|---|---:|---:|---:|
| t+0s | 2401.25 | 0.51 | 0.52 |
| t+30s | 2401.27 | 0.51 | 0.52 |
| t+60s | 2401.76 | 0.50 | 0.52 |
| t+90s | 2401.86 | 0.51 | 0.54 |
| t+150s | 2402.56 | 0.51 | 0.54 |
| t+180s | 2403.75 | 0.53 | 0.56 |
| t+240s | 2404.87 | **0.55** | 0.57 |

ETH moved +0.15%; the rational inside bid moved from **0.50 → 0.55** (tracking spot, ~30s lag). That's an **active MM** with sub-minute reaction time, not a retail quoter.

Also: **I was misreading the CLOB `/book` output.** It returns bids sorted ascending (lowest first), so `bids[0] = 0.01` is the *worst* bid, not the best. Gamma-api's `bestBid` was the true inside all along. The "73¢ gap" I claimed earlier doesn't exist — the real inside quote is a **2-3¢ spread** being actively managed.

**Strategy implications:**
- The MM opportunity as written **does not exist for a laptop-grade operator**. The spread we'd have been "the first rational quote inside" is already 2-3¢ wide and owned by someone who reacts to spot within 30 seconds.
- To compete we'd need (a) sub-second reaction time to spot, (b) inventory management across 30+ concurrent markets, (c) proper vol modeling. All three are infrastructure problems where professional MMs have decisive advantages.
- Expected net edge: **near zero or negative** after adverse selection. We'd be a slower, less-informed participant in a market already served.

**Revised monthly revenue estimate on $10k: $0 net.** Gross revenue from occasional lucky fills maybe $50-200/mo; adverse selection on the rest wipes it out.

**Where the MM opportunity might still exist:**
- **Not on `above-K` digitals that professionals already cover.**
- Possibly on very-long-tail markets (niche politics, obscure sports) where pro MMs genuinely aren't present.
- Possibly on newly-listed cohorts in the first 30 seconds before MMs connect.
- Possibly in weird conditions (spot moves faster than MMs adjust, creating momentary gaps) — but this is a latency strategy, not an LP strategy.

**Down-rank from "strongest current opportunity" to "likely dead without stronger infra."**

## Hypothesis 1 (original, now confirmed) — The $12.7k bid at 0.20 isn't retail; it's a sophisticated MM running exactly our strategy

**Specifically:** the ETH-above-2400 market at last=0.71 showed a $12.7k bid at 0.20 and $2.9k ask at 0.93. I interpreted this as "the MM opportunity is real — no one is quoting rationally inside 73¢, we'd be the tight quote."

But the same data fits an alternative narrative: someone is running a **barbell quoting strategy** — cheap lottery-ticket buys + inventory-dump sells, both sized to capture the occasional informed-flow spike at the extremes. In that model, the middle of the book is *deliberately* empty because posting inside competes with their barbell without adding expected value. If that's the game, our tighter quotes would:
- Get filled only when the barbell quoter wouldn't have filled (selection bias against us)
- Compete with the barbell quoter for the occasional extreme-flow event (we'd lose because they have bigger capital and better modeling)
- Reduce the barbell quoter's edge, making them post wider or exit entirely — leaving us alone with a book that has different (worse) flow properties

**Testable:** observe whether the $12.7k/0.20 bid cancels within seconds of spot moves. If yes → sophisticated, they'd adjust faster than us. If no → retail-ish, we can compete.

**If hypothesis is true:** the strategy returns less than zero; we'd be adverse-selected against an informed counterparty.

## Hypothesis 2 — The settlement-rush volume is the only volume worth having, and we can't capture it

The barrier markets do $50-167k over 24h but the bulk is the final 1-3 hours when spot approaches the barrier. The balanced-probability steady-state volume we'd target is quiet — in my one-hour sample of ETH-above-2400 at 12.5h to expiry, only **2 trades for $14 of notional** crossed the book.

**If true:** the addressable flow at our target windows is ~$200-500/day across all markets combined, not the $2-10k/day my estimate assumes. At a 10-15¢ edge per fill, that's $20-75/day gross, $600-2,200/month gross. **Net of adverse selection, this goes to near-zero.**

**Testable:** the week-long passive watcher script will show how much real flow passes through balanced-probability windows. If it's <$1k/day addressable per market, the strategy is dead.

## Hypothesis 3 — Polymarket's fee isn't zero, and even a small fee kills it

We don't know the real fee structure. `maker_base_fee: 1000` in unknown units. If it's 1% per trade, round-trip cost is 2% — larger than our expected 10-15¢ edge per fill (which is ~10% of a $1 contract). **At a 1% maker fee, the strategy is flat-to-negative before adverse selection.**

**Testable:** the $10 fee experiment resolves this. But until resolved, we're flying blind.

**If fee is 1%:** the strategy returns $0/month at any capital level.

## Hypothesis 4 — We can detect the opportunity but not execute on it

The MM strategy requires:
- Sub-second reaction time to spot moves (for cancel-before-pickoff)
- Inventory tracking across 30-60 concurrent markets
- Fast limit-order placement and cancellation
- Operating from a VPS near Polymarket's infrastructure (matrix relay nodes)

My current infrastructure (laptop, REST API via aiohttp, SQLite) is orders of magnitude slower than what's needed. A sophisticated MM co-located with 10ms round-trip time would pick off our 500ms-reaction-time quotes consistently.

**If true:** even a real underlying edge doesn't flow to us; it flows to better-infrastructured MMs.

**Testable:** measure our end-to-end reaction time to a simulated spot shock (read spot → decide → cancel → confirm) — if it's >200ms, we're a dead-on-arrival MM.

## Hypothesis 5 — The 73¢ gap isn't a gap, it's the exchange mechanism working as designed

Looking at the book `bids: 0.20 @ $12.7k, 0.07 @ $9, 0.06 @ $17k, ...` — there ARE quotes between 0.07 and 0.20. The "73¢ gap" I emphasized is really only at the very top-of-book levels (0.01 penny-stub to 0.20 real-depth). Retail takers who walk with a market order will hit the 0.20 first, not the 0.01, so they're *already* getting filled at a level well inside the 1¢/99¢ stubs.

**If true:** the real tradable spread is more like `0.20 to 0.93` = 73¢, but that's the *executed* spread; we'd be fighting for queue position at 0.20+ (bid side), and the top-of-book traders are already there.

## Hypothesis 6 — Polymarket regulatory risk eats the first 12 months

NZ-based access is legal today. But:
- CFTC has enforced against Polymarket before (2022)
- US agents can't access at all
- Polymarket has ongoing investigations
- If NZ were to follow US regulatory guidance, access closes with little warning

**If you deploy $50k and access closes in month 4:** you might be unable to withdraw without lengthy remediation. Capital lost to operational risk.

**If true:** the EV calculation needs a material regulatory-exit discount — probably 15-25% per year. That cuts realistic returns by a similar amount.

## Hypothesis 7 — Scale kills the edge faster than capital helps

The $300-2k/month estimate assumes linear scaling with capital up to some ceiling. But actually:
- At $10k we're too small to matter; book depth is plenty
- At $50k our orders *are* the book depth at balanced-probability points; we affect prices
- At $100k we're visible enough that other MMs adjust to our patterns, reducing our edge
- At $250k we're a significant fraction of typical flow; adverse selection dominates

**If true:** the path from $10k ($300-2k/mo) to $50k ($3-10k/mo) is illusory. Real scaling is capped closer to the low end, and the hobby-business number is the real number, not a floor.

## What to do with this counter-memo

Each hypothesis is **testable without deploying capital**. The week-long watcher + fee experiment + 1-hour behavior profile on the 0.20 bid together resolve hypotheses 1, 2, 3, 4, and partially 5.

If after those tests:
- H1 false (0.20 bid is retail) + H2 false (flow exists in target windows) + H3 resolved (fee is low) + H4 false (our infra is fast enough) → proceed to backtest
- H1 true OR H3 true (1% fee) → kill strategy
- H2 true OR H4 true → strategy is still alive but only at the $300/mo end of the range

Hypotheses 6 and 7 are real but softer; they bound the *maximum* return rather than killing the minimum.

## The overall pattern this memo is trying to capture

The writeup in `OPPORTUNITY_HOURLY_LADDER_MM.md` is honest but incomplete. It acknowledges uncertainties but *frames* them as "things to resolve before deploying" rather than as "ways the strategy silently fails without you noticing." This counter-memo reframes the same uncertainties as silent-failure modes.

**If any of H1-H4 is true, the strategy generates ≤$0/month regardless of capital.** That's the kind of downside the optimistic writeup didn't lead with.
