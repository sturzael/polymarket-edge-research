# Agent C — HL MM competitive landscape

**Returned:** 2026-04-21

## Institutional MM presence

- **Wintermute**: named counterparty in Bitwise's HL ETF amendment (April 2026) and growing HL involvement alongside **Flowdesk**. Runs on 50+ venues, ~$237M on-chain inventory (Feb 2025).
- **Keyrock, GSR, Cumberland, B2C2, DWF Labs**: active in crypto MM broadly; no strong public statements naming HL, but HL is now the largest perp DEX (~70–80% of decentralized perp volume, ~$30B daily), so presence is near-certain.
- **Key HL design choice**: "There is no DMM program, special rebates / fees, or latency advantages" per HL docs — institutional MMs get the *same* fee schedule. Cancels and post-only orders prioritized onchain above GTC/IOC.
- Book depth is Tier-2 CEX quality — $500k BTC orders fill with "minimal slippage," fingerprint of professional MMs already present.

## HLP assessment

- TVL: **~$373M** (Hyperscreener, 2026); all-time cumulative PnL ~$43M.
- Historical return: ~1.75% monthly / ~20% annualized; outlier $15M/day on 1 Feb 2026 (~5.8% in 24h).
- Drawdowns: JELLY (Mar 2025, ~$12–13.5M unrealized, socialized-settled at $0.0095); toxic liquidations elsewhere.
- **HLP is flagship but not the sole LP** — HL docs explicitly acknowledge external MMs. HLP takes 1% of trading revenue plus spread/liquidation PnL. Share of *volume* isn't publicly disaggregated, but HLP's AUM vs HL's $30B daily volume implies it's not trading the whole book.

## Public solo operators / prior art

- **"220× returns" case study** (Bitget/Futu): anonymous retail bot, $6.8k → $1.5M via one-sided quoting for the −0.003% rebate. **Applying ÷5**: treat as ~40× = survivorship-biased outlier; path requires ≥3% of maker volume for top tier, unreachable on $5–10k.
- **Hummingbot HL connector** (hyperliquid + hyperliquid_perpetual, HIP-3 support in v2.12, API-key auth added early 2026) — mature, actively maintained.
- **TreadFi**, Gainium, OctoBot, Novus-Tech MM repos on GitHub — retail frameworks exist, no verified sustained MM P&L disclosures.
- Solo-operator Substack / Twitter signal is thin: lots of "how to" posts, almost no verified monthly P&L.

## Recent incidents affecting viability

- **JELLY (26 Mar 2025)**: validator-forced delist at $0.0095 within 2 min. Post-incident changes: BTC leverage capped 40×, ETH 25×, dynamic Unrealized Contract Limit, HLP Liquidation Reserve, 4-day withdrawal lockup maintained. Centralization concerns remain.
- **HYPE** price volatile 2026 ($20–$60 range, currently ~$44); doesn't directly hit BTC MM but correlates with regime shifts.
- No 2026 MM-specific catastrophic events found.

## Competitive-intensity score

**Top-of-book at sub-second is contested.** Median end-to-end latency for co-located clients is **200ms**, 99p 900ms; third-party feeds (HypeRPC, Tokyo) beat native API by ~2× at 135ms. NZ → HL validators (likely Tokyo) is ~120–140ms physical floor — **workable at the 100–200ms tier, not competitive sub-50ms.** Maker rebate tiers (−0.001% / −0.002% / −0.003%) require 0.5% / 1.5% / 3.0% of 14-day maker volume — **completely unreachable on $5–10k**. You quote at 0.015% maker, 0.045% taker base tier with no rebate.

## Verdict

**Thesis weakened but not dead for niche strategies.** Institutional MMs dominate top-of-book for the rebate; a $5–10k solo operator from NZ cannot compete there and cannot reach any rebate tier. However: (1) HL explicitly levels the field (no DMM privileges), (2) HLP has structural limitations (4-day lockup, risk caps post-JELLY), (3) quiet-hour inventory-management strategies at 100–200ms do not require top-of-book. Realistic edge is **not** classical spread capture — it's **niche informed-flow avoidance + small-size quoting in quiet BTC hours**, aiming for HLP-like ~15–20% annualized, not rebate-farming 220× tales. If the build goal is rebate capture, abandon. If it's a learning exercise with modest return expectations and inventory discipline, retail access remains open.

## Sources

- [HL Market Making docs](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/market-making)
- [HL Fees docs](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees)
- [HL Optimizing Latency docs](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/optimizing-latency)
- [Bitwise HL ETF names Wintermute/Flowdesk](https://www.crowdfundinsider.com/2026/04/272856-bitwise-submits-latest-amendment-to-hyperliquid-etf-names-flowdesk-and-wintermute-as-trading-counterparties/)
- [HLP on DefiLlama](https://defillama.com/protocol/hyperliquid-hlp)
- [ASXN HL dashboard](https://stats.hyperliquid.xyz/)
- [Halborn JELLY post-mortem](https://www.halborn.com/blog/post/explained-the-hyperliquid-hack-march-2025)
- [HL incident 2025-26-03](https://hyperliquid-co.gitbook.io/wiki/introduction/roadmap/incident/2025-26-03)
- [HL risk updates post-JELLY](https://cryptorank.io/news/feed/506c0-hyperliquid-announces-key-risk-management-updates-following-jelly-market-incident)
- [Hummingbot HL connector](https://hummingbot.org/exchanges/hyperliquid/)
- [220× MM bot case study](https://www.bitget.com/news/detail/12560604969577)
- [ASXN HL microstructure writeup](https://www.asxn.xyz/posts/hyperliquid/)
