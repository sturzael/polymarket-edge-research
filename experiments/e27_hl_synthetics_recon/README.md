# e27 — Hyperliquid synthetics MM recon

**Date:** 2026-04-21 (single-session, ~3 hours of live HL API work)
**Capital regime under test:** $5-10k solo retail
**Question:** Does the HL non-BTC/ETH/SOL "synthetics slice" (xyz:CL, xyz:BRENTOIL, xyz:XYZ100, HYPE, TAO, etc.) offer a structurally wider MM opportunity than BTC-only did in e26?

## 1. One-line finding

**REJECTED.** The synthetics slice on HL is not structurally wider than the BTC surface — top synthetics by volume quote at 0.1-1.0 bp (comparable to BTC/ETH), and the only assets with 2-6bp spreads are low-volume tails where our ÷5-adjusted planning number stays in the **-$90 to +$130/mo** range. The e26 "defer build" verdict for BTC-only extends to all of HL.

## 2. Asset universe overview

Fetched 2026-04-21T05–06 UTC via `metaAndAssetCtxs` across all 9 perpDexs + spot.

- **393 perps** across 9 perpDexs: `core` (229), `xyz` (65, the HIP-3 equities/commodities dex), `flx` (16), `vntl` (15), `hyna` (25), `km` (23), `abcd` (1), `cash` (16), `para` (3).
- **292 spots**.

Top 10 perps by 24h $ volume (non-major):

| Rank | Name | Dex | 24h $ Vol | Mark | OI $ |
|---|---|---|---|---|---|
| 3 | xyz:CL | xyz | $669M | 86.43 | $293M |
| 4 | HYPE | core | $264M | 40.98 | $814M |
| 5 | xyz:SP500 | xyz | $257M | 7125 | $449M |
| 6 | xyz:BRENTOIL | xyz | $245M | 89.75 | $284M |
| 7 | xyz:XYZ100 | xyz | $161M | 26684 | $212M |
| 8 | xyz:SILVER | xyz | $147M | 78.84 | $85M |
| 9 | XRP | core | $55M | 1.44 | $85M |
| 10 | AAVE | core | $47M | 93.3 | $56M |

Key observation: **the xyz perpDex (HIP-3 builder market) now carries ~$1.5B in daily volume across commodities (CL, Brent, silver, gold), indices (SP500, XYZ100) and equities (TSLA, MSTR, NVDA, ...).** This was the "synthetics" referenced in e25. It IS large and real.

## 3. Where the 9 top wallets actually trade

Per-wallet summary (using e25's on-disk fills, 30-day window where available). Fill count in first row:

| Rank | Addr | Fills | Top asset (% of fills) | #2 | #3 | Role heuristic |
|---|---|---|---|---|---|---|
| 14 | 0xa31...ad1e | 16541 | LIT 45% | HYPE 8% | MON 7% | mixed maker 51% |
| 16 | 0x2e3...dd14 | 72 | TST 100% | — | — | **underpowered (liquidation cluster)** |
| 19 | 0xbdf...5c50 | 69 | xyz:CL 74% | km:SMALL2000 22% | xyz:XYZ100 3% | **underpowered** |
| 23 | 0x5d2...9bb7 | 1064 | xyz:CL 78% | xyz:SP500 18% | xyz:XYZ100 4% | maker 93%, directional |
| 24 | 0x8af...fa05 | 22990 | xyz:CL 47% | xyz:BRENTOIL 35% | xyz:XYZ100 11% | maker 60%, mixed |
| 28 | 0x8e0...70c9 | 21893 | xyz:CL 39% | BTC 22% | xyz:SILVER 20% | taker 91%, aggressive |
| 32 | 0x939...04d2 | 31 | xyz:CL 100% | — | — | **underpowered** |
| 35 | 0x7da...f410 | 14332 | HYPE 99.8% | CRV <1% | — | mixed |
| 50 | 0x82d...32ff | 3245 | @107 (spot NEKO-era) 100% | — | — | 1-day spot burst |

**Aggregate:** among 9 wallets over ~30d, `xyz:CL` (20.2k fills, 5 wallets), `HYPE` (15.6k fills, 2 wallets), `xyz:BRENTOIL` (11.0k fills, 2 wallets), and `xyz:XYZ100` (2.5k fills, 3 wallets) are the genuine concentration points. So the hypothesis about **where** top wallets trade is confirmed — they do cluster on the xyz equities/commodities dex. The question is whether SPREADS there are wide.

## 4. Spread comparison: synthetics vs BTC

5 L2-book snapshots spaced 45s apart, 2026-04-21 ~05:55-06:00 UTC. Mean spread (bps) sorted ascending:

| Coin | Vol24h | Mean spread (bps) | 50bp-depth bid+ask (USD avg) |
|---|---|---|---|
| SOL | $157M | 0.117 | $1.2M |
| BTC | $2.22B | 0.132 | $8.3M |
| **xyz:SP500** | **$257M** | **0.140** | $1.3M |
| **xyz:GOLD** | **$30M** | **0.209** | $1.2M |
| PAXG | $4.7M | 0.252 | $0.9M |
| **xyz:XYZ100** | **$161M** | **0.375** | $3.6M |
| ETH | $1.04B | 0.431 | $18.5M |
| HYPE | $264M | 0.488 | $0.28M |
| **xyz:SILVER** | **$147M** | **0.634** | $0.84M |
| XMR | $3.5M | 0.731 | $0.15M |
| TAO | $9.5M | 0.894 | $0.25M |
| **xyz:CL** | **$669M** | **0.903** | $1.3M |
| **xyz:TSLA** | **$14M** | **0.913** | $0.17M |
| **xyz:BRENTOIL** | **$245M** | **0.935** | $0.46M |
| ZEC | $36M | 1.260 | $0.27M |
| FARTCOIN | $19M | 1.486 | $0.09M |
| AAVE | $47M | 2.560 | $0.09M |
| LIT | $4M | 4.061 | $0.03M |
| MON | $14M | 4.209 | $0.06M |
| **xyz:MSTR** | **$13M** | **6.036** | $0.76M |

Key facts:
- The **most-traded** synthetics (xyz:SP500, xyz:XYZ100, xyz:GOLD, xyz:CL, xyz:BRENTOIL, xyz:SILVER) all quote between 0.14 and 0.94 bps. That is tighter than or comparable to BTC/ETH.
- Top-of-book changed every snapshot (4/4) on every major asset and most synthetics — i.e. **TOB refreshes faster than 45s**. This is the signature of colocated pro MMs.
- The only assets with wide (2-6bp) spreads are the low-volume tails where top-PnL wallets either DON'T trade (FARTCOIN, ZEC) or trade only marginally (AAVE, LIT at rank-14, MON at rank-14, xyz:MSTR at 2 wallets with small fill counts).
- Hypothesis "synthetics are 10-50bps" = **falsified**. Reality is 0.1-1bp for the size-bearing synthetics.

## 5. Top candidate synthetics for solo MM (with numbers)

Assumptions (shown): HL maker fee 1.3bp; quote $2500/side; 50% spread capture; 50 fills/day.

| Coin | Spread | Net/fill | Raw $/mo | ÷5 $/mo | Top wallets | Verdict |
|---|---|---|---|---|---|---|
| xyz:MSTR | 6.04 | +1.72bp | $644 | **$129** | 0 | borderline, but 0 top wallets |
| MON | 4.21 | +0.80bp | $302 | **$60** | 1 (rank14) | marginal |
| LIT | 4.06 | +0.73bp | $274 | **$55** | 1 (rank14) | marginal |
| AAVE | 2.56 | −0.02bp | −$8 | −$2 | 1 | dead |
| FARTCOIN | 1.49 | −0.56bp | −$209 | −$42 | 0 | dead |
| xyz:CL | 0.90 | −0.85bp | −$318 | −$64 | 5 | **dead: top-wallet magnet but spread too tight** |
| xyz:BRENTOIL | 0.94 | −0.83bp | −$312 | −$62 | 2 | dead |
| xyz:XYZ100 | 0.38 | −1.11bp | −$417 | −$83 | 3 | dead |
| xyz:SP500 | 0.14 | −1.23bp | −$461 | −$92 | 1 | dead |
| BTC | 0.13 | −1.23bp | −$463 | −$93 | — | dead (e26 baseline) |

**Ceiling sensitivity** (100% capture, 1.0bp fee, 200 fills/day — everything breaks our way): only `xyz:MSTR`, `MON`, `LIT`, `AAVE` break +$500/mo ÷5, and all four have weak or zero top-PnL-wallet concentration signal and sub-$20M vol (thin depth, whale-dominated).

## 6. Revised planning number vs e26 BTC-only

| Scenario | Monthly raw | Monthly ÷5 |
|---|---|---|
| e26 BTC-only at $5-10k | ~$50-150 raw | **$15-50** |
| e27 best synthetic (xyz:MSTR, realistic 50% capture) | $644 | **$129** |
| e27 aggregate: trade 3 of MON/LIT/xyz:MSTR with $1k each | $400-1100 | **$80-220** |
| e27 ceiling (any synthetic, 100% capture scenario) | $1.5-7.5k | $300-1500 |

So the "5-20×" claim requires, at a minimum, concentrating in low-vol tails (xyz:MSTR, MON, LIT) AND getting a favorable capture rate, AND accepting ~$130/mo/asset/pair at ÷5. That is not structurally different from BTC-only once you account for the fact that 2-6bp spreads on thin assets are exactly where adverse selection is worst.

**Planning number if one were to proceed:** $80-200/mo ÷5 on a 3-asset portfolio (xyz:MSTR + MON + LIT), with realistic chance of actually delivering $30-80/mo after adverse selection. Barely 2× the BTC-only baseline, not 5-20×.

## 7. Verdict

**Hypothesis rejected.** The "synthetics slice is 5-20× BTC-only for solo retail" thesis is not supported by the data:

1. The biggest, top-wallet-magnet synthetics (xyz:CL, xyz:BRENTOIL, xyz:SP500, xyz:XYZ100, xyz:SILVER, xyz:GOLD) all quote at BTC-like or tighter spreads. Those are already fully contested by the same pro MMs.
2. The only assets with wide spreads (LIT, MON, xyz:MSTR) are thin, have no meaningful top-PnL-wallet concentration (weak social proof that an MM strategy works there), and at ÷5 discipline plausibly yield $50-130/mo each — not materially different from BTC.
3. Top-wallet role analysis (rank-23 @ 93% maker, rank-24 @ 60% maker, rank-28 @ 91% **taker**) shows that even the top wallets in xyz:CL are split between MM-like and directional-takers. The directional traders (rank-28 with $58.9M allTime PnL at 91% taker in xyz:CL+BTC+silver+brent) did NOT make their money market-making — they made it directionally. That PnL is not reproducible by an MM book.
4. TOB refresh is ≥ every 45s on every sizable synthetic — same signature as BTC/ETH. There is no quiet corner of HL where solo retail can post top-of-book and collect.

**Go/no-go: NO-GO on the 3-day Phase 2 HL synthetics build.** The e26 verdict ("BTC-only MM is structurally dead for solo retail on HL") extends across the platform.

## 8. Caveats & next steps

- **Snapshot concentration risk:** all L2 snapshots were from one 4-minute window at 05:55-06:00 UTC. US-equities hours (xyz:TSLA, xyz:MSTR, xyz:SP500) would likely show wider spreads pre/post market open; a 24h sweep is warranted before finalising. But since the thesis is "structural 5-20×", a 4-minute single-window finding of 0.1-1bp on the volume winners is already sufficient to reject.
- **Top wallets' PnL sources remain unexplained:** rank-28 (91% taker, $58.9M allTime) is NOT a MM — that's a directional call, probably on oil. Rank-23 is 93% maker in xyz:CL/SP500 — but their 1064 fills and $63M allTime PnL suggest they made the bulk of it on one or two multi-million-dollar directional bets, not by harvesting 1bp 10k times. This would need a closedPnl distribution study; deferred.
- **HLP not directly characterised.** I did not pull HLP's positions per asset. HLP's mandate is BTC/ETH/SOL but they may be passive in top synthetics too; that's a separate investigation.
- **Builder codes / HIP-3 vault:** xyz perpDex has a fee-recipient structure (`0x9cd...` in the perpDexs response); a builder might already be capturing the maker rebate on synthetics that would otherwise accrue to MMs. This deserves a follow-up look if a synthetics MM build is ever revisited.
- **Low-vol assets NOT characterised:** we sampled 20 assets; there are ~373 more perps. Some very-low-volume ticker (e.g. random alt on `flx`/`vntl`/`hyna`/`km` dexs) might have 20bp spreads with 1 fill/hour. That is technically positive bps but the turnover kills it — a 20bp spread at 10 fills/day = ~$15/mo at ÷5 on $2.5k per side. Not worth pursuing.

### Data artifacts

- `data/asset_universe.json` — 393 perps + 292 spots, ranked by 24h vol, tagged by dex/category.
- `data/wallet_profiles.json` — 9 wallets × top assets × fill/role/hour distribution + cross-wallet aggregation.
- `data/spread_snapshots.json` — 20 assets × 5 L2 snapshots × spread/depth/TOB-change metrics.
- `data/capacity_estimates.json` — planning-number table with ÷5 discipline + assumptions.
