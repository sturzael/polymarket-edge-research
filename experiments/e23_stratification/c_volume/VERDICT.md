# Agent C VERDICT — Volume stratification

**The sports FLB is scalable, not liquidity-gated.** Of the 120 sports markets at 0.55-0.60 at T-7d, 98 (81.7%) belong to the ≥$5k window-volume tier, and those 98 markets show a **+30.3pp FLB** (Wilson 95% lower bound ~+22pp) — *larger* than the pooled +25.8pp headline. The <$500 tier, where a liquidity artifact would live, contributes only 16 markets at +11.2pp (insufficient sample).

**Capacity:** median `max_single_trade_usd` in Tier 3 = $9,040; p90 = $66k. The FLB is observable in markets where $5-50k clips have actually transacted at T-7d ±12h.

**Signal-strengthens-with-volume** is the critical qualitative result — correlation(price, yes) rises from 0.42 → 0.67 → 0.76 across tiers. This is inconsistent with the liquidity-artifact hypothesis.

**Remaining risk for deployment:** execution quality (spread, depth, post-fill slippage). Hand off to Agent F for friction-adjusted edge.
