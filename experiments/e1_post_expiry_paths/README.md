# e1 — Post-expiry price path analysis

**Question:** Between T (nominal 5m-market expiry) and T+400s (actual Polymarket resolution), what do prices do?

**Method:** For 20 resolved 5m/15m markets from the probe DB, pulled full trade history via `data-api.polymarket.com/trades?market=<cid>` (up to 4000 trades per market), converted each trade into (t_rel, P(Up-token)), and analyzed the window T-60 to T+400.

Code: `analyze.py`. Output: `per_market.csv`, `summary.json`.

## Findings

**Shape distribution across 20 markets:**
| Shape | n | meaning |
|---|---:|---|
| **snap** | 16 | price touches within 2% of target in first 30s |
| drift | 1 | target reached between 30-300s |
| slow | 0 | still not at target by 300s |
| no-data | 3 | 0 trades in post-T window |

**Volume in post-T window:** mean **50.2** trades per market, median **17**. So there *is* material trading activity between T and resolution — not a ghost town.

**Representative cases (from `per_market.csv`):**

| market | outcome | price at T-0 | mean first 30s | shape |
|---|---|---|---|---|
| `btc-updown-5m-1776479400` (DOWN) | DOWN | **0.01** | 0.006 | snap — already at target |
| `btc-updown-5m-1776478800` (DOWN) | DOWN | 0.19 | 0.13 → 0.01 @60s | snap |
| `bnb-updown-5m-1776478800` (UP)    | UP   | **0.01** | **0.93** | **snap with huge pre-T misprice** |
| `eth-updown-5m-1776479100` (DOWN)  | DOWN | 0.08 | 0.014 | snap, clean convergence |
| `doge-updown-5m-1776478800` (UP)   | UP   | 0.97 | 0.99 | snap — market already knew |

## The BNB outlier is the story

`bnb-updown-5m-1776478800`: **price of Up-token was 0.01 (99% Down) in the final 60 seconds, but the market resolved UP**. Within 30s post-T, price jumped to 0.93 (93% Up) — a 92¢ swing on a binary.

Interpretations:
1. **Spot whipsaw right at the boundary** — BNB spot ticked up in the last second, the Chainlink oracle reading happened to catch that tick, outcome flipped against consensus.
2. **Oracle lag / snapshot discrepancy** — market was pricing against one view of spot; Chainlink's resolution was against another reference moment.
3. **Legitimate tail outcome** that the market simply missed.

Either way: **this is exactly the type of case where lead-lag / feed-mismatch analysis matters.** If we see N of these per day and they correlate with *spot movement in a specific 1–3 second pre-T window*, that's the tradable pattern.

## Strategy-universe implications

The **snap** pattern is dominant. That rules out two of the three hypothesis shapes the user proposed:
- ❌ "Drift toward 0/1 over 400s" — we don't see this.
- ❌ "Stay at 0.9/0.1 with wide spreads during dispute window" — we don't see this either.
- ✅ "Snap at T; residual mispricing is in the final seconds *before* T, not after."

This shifts the strategy from "read oracle faster than others post-T" to "identify cases where pre-T price diverges from imminent spot fate". The key question becomes: **in the final 5-15 seconds pre-T, when price is still nominally ambiguous, how often does spot already tell you the answer with high confidence?**

## Caveats

- 20 markets is a small sample. Full validation needs 200+.
- "Snap" as I defined it is "any trade within 30s touches within 2% of target" — it's permissive. A stricter definition would be "stays there for ≥5 consecutive trades." Revisit when sample is larger.
- The 3 no-data cases may be informative — those are likely markets where the outcome was fully priced-in pre-T (no trades because no uncertainty).
- This analysis uses trade timestamps as wall-clock; Polymarket's resolution is on-chain via Chainlink oracle, which may settle at slightly different moments. Validity fine for the shape classification, but exact timing of "resolution moment" would need on-chain data.

## Status

Complete. Key insight: **the tradable window is pre-T, not post-T.**
