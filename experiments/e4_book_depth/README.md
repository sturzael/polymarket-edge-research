# e4 — CLOB book depth

**Question:** How thick is the orderbook at different distances from expiry? Is midpoint a meaningful price?

**Method:** Point-in-time snapshot of `clob.polymarket.com/book?token_id=<up>` for 5m crypto markets at multiple lifecycle stages.

## Findings

**All three mid-life markets sampled had `bid=0.01 / ask=0.99` with 60+ price levels posted** — purely stub orders at the 1¢ and 99¢ extremes:

| underlying | t to end | bid | ask | spread | bid levels | ask levels | bid notional | ask notional |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DOGE | +144 s | 0.01 | 0.99 | 0.98 | 64 | 27 | $430 | $6,782 |
| BTC  | +144 s | 0.01 | 0.99 | 0.98 | 63 | 36 | $5,880 | $42,512 |
| ETH  | +144 s | 0.01 | 0.99 | 0.98 | 43 | 56 | $689 | $10,781 |

**Midpoint = 0.50 for all three**, even though the actual market views (implied by earlier last-trade prices) were quite different: ~0.25 for BTC, ~0.50 for DOGE, ~0.08 for ETH in the post-expiry analysis.

**The midpoint is fiction.** The user was right to flag this. Any analysis that derives "market's implied probability" from midpoint will be systematically wrong during mid-life. You must use `lastTradePrice`, or weight by depth at tighter levels, or run during final-stretch only.

## What wasn't measured

- Final-stretch (T-90s to T-0) book depth — requires passive sampling over an hour (the 5m-market lifecycle is quantized; only one batch is active at a time per underlying, and the probe saw mid-life only in the single window we sampled).
- Trade-weighted effective spread (what actual fills happen at vs midpoint).
- Whether the 1¢/99¢ stubs are market-maker limit orders or opportunistic hedging orders.

## Lifecycle quantization finding (bonus)

While debugging the bucket picker I noticed 5m markets have **perfectly quantized 300s offsets**:
tte = …, -168, +131, +431, +731, +1031, …

This means at any moment, per underlying there is exactly one market in each lifecycle stage — one in its final minutes, one with ~3 minutes left, one with ~5, etc. The full book-depth story needs samples from each stage, which requires sampling the single "final-stretch market" each time it cycles through that phase.

## Implication for v2

- **Use `lastTradePrice`, not midpoint, as the primary price signal** during non-final phases.
- **Midpoint becomes meaningful only in the final stretch** once MMs post tighter quotes — that's the actionable window.
- **Maximum strategy size bounded by final-stretch ask notional**, which we haven't measured yet. Given the mid-life stubs show $5k-$40k at 99¢, the final-stretch tighter book likely carries low-$k at reasonable prices. Confirm with a follow-up sampler.

## Status

Partial. Mid-life depth sample done. Final-stretch depth sample pending (requires ~1h background sampler, needs user approval for the background spawn).
