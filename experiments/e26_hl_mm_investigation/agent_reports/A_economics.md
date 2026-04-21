# Agent A — HL MM economics & mechanics

**Returned:** 2026-04-21

## Fee / Rebate Schedule (perps, post-May-2025)

| Tier | 14d Weighted Vol | Taker | Maker |
|------|------------------|-------|-------|
| VIP 0 | < $5 M | 0.045 % | 0.015 % |
| VIP 1 | > $5 M | 0.040 % | 0.012 % |
| VIP 2 | > $25 M | 0.035 % | 0.008 % |
| VIP 6 | > $14 B | 0.024 % | 0.000 % |

Separate **maker-rebate track**: trailing 14-day maker share of total exchange volume > 0.5% earns −0.001% (rebate); deeper tiers go lower. For a $5–10k book this threshold is unreachable in isolation — exchange-wide daily volume is tens of $B.

Stackable discounts:
- **Referral code**: −4% on fees for first $25M of own volume.
- **HYPE staking**: Wood (>10 HYPE) 5% → Diamond (>500k) 40%.
- **Realistic solo cap**: VIP-0, referral + Bronze stake (100 HYPE ≈ $1–2k) → maker ≈ **0.013%**, taker ≈ 0.040%. No rebates.

## Order Types on BTC-PERP

GTC, IOC, **ALO (post-only)**, FOK, market, trigger (SL/TP). ALO has **highest block-ordering priority** — cancels/post-onlys are sequenced before GTC/IOC each block, which materially reduces adverse-selection on the quote side.

## BTC-PERP Specs

- `szDecimals = 5`, `MAX_DECIMALS = 6` → price precision 1 decimal place (tick = $0.1) on a ~$100k coin → **~1 bp tick**.
- Min notional: **$10**.
- Typical top-of-book spread: ~$1 (≈1 bp) during normal hours; cumulative 1% depth ~140 BTC per side.

## HLP (Hyperliquidity Provider)

Protocol-owned USDC vault (~$442M TVL on DefiLlama) running passive MM + backstop-liquidator strategies. It **quotes on the open book** alongside retail — competitor, not just fail-over. Historical ~20% APR run-rate; spiked in Feb 2026 after absorbing a $700M liquidation (+$15M). Major prior tail events: **JELLY attack (26 Mar 2025)** cost HLP ~$12M before validators delisted the token.

## Capacity for $5–10k Solo on BTC

Naive bps math: 0.013% maker + ~1 bp spread → maker fill earns ≈1.3 bps before adverse selection. Spread already ~1 bp → **almost no captured spread left** once fees paid; edge comes only from inventory-skew profits.

Resting sizing: 5× gross leverage on $5k → ~$25k gross quoted notional. Applying ÷5 discipline → **~$2.5k per side realistic** without adverse selection. At HL's BTC daily volume ($3–5B), you are dust — no venue impact — but competing against HLP + dozens of colo'd pro MMs on a sub-ms matching engine.

## Key Risks

1. **Adverse selection**: HLP + pro MMs latency-optimised; retail VPS sees 20–100 ms disadvantage.
2. **HLP crowding**: same passive strategy, deeper capital, zero fees internally.
3. **Fat-tail**: JELLY-type oracle/OI manipulation has happened; validator intervention discretionary.
4. **No meaningful rebate** below ~0.5% share of total HL volume.
5. **Tier data public**; maker-rebate qualifier share requires logged-in dashboard.

## Verdict

**Economically accessible but structurally thin-edge.** The surface (APIs, ALO priority, low min-notional, tight tick) is retail-friendly, and no account-gated tier is required to start. But the combination of (a) ~1 bp spreads already, (b) 1.3 bp maker fee floor without rebate, (c) HLP as a better-capitalised, fee-exempt co-quoter, and (d) sub-ms pro-MM competition means a $5–10k solo BTC-MM has **essentially no spread-capture edge** — any positive PnL must come from inventory timing (i.e. directional alpha, not market-making). Rank-2 wallet's reported 0.1% momentum-coincidence consistent with a **much larger, latency-advantaged** operator, not a replicable retail template. **Recommend: prototype on testnet / observe-only first; do not scale until edge net-of-fees is demonstrated on out-of-sample paper fills simulating ≥50 ms latency.**

## Sources

- [HL Fees Docs](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees)
- [HL Order Types](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/order-types)
- [Tick/Lot Size](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/tick-and-lot-size)
- [HLP Protocol Vault Docs](https://hyperliquid.gitbook.io/hyperliquid-docs/hypercore/vaults/protocol-vaults)
- [HL Referrals](https://hyperliquid.gitbook.io/hyperliquid-docs/referrals)
- [DefiLlama HLP TVL](https://defillama.com/protocol/hyperliquid-hlp)
- [Halborn JELLY incident](https://www.halborn.com/blog/post/explained-the-hyperliquid-hack-march-2025)
- [HL incident page 2025-26-03](https://hyperliquid-co.gitbook.io/wiki/introduction/roadmap/incident/2025-26-03)
- [asxn HL orderbook teardown](https://www.asxn.xyz/posts/hyperliquid/)
