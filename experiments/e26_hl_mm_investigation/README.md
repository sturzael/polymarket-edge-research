# e26 — Hyperliquid BTC-PERP market-making viability investigation

**Date:** 2026-04-21
**Status:** Four-agent recon complete. DEFER BUILD. Thesis is weakened: classical spread capture is dead for solo retail. Niche inventory-management in quiet hours is the only residual path, capped at HLP-like ~15–20% APR gross before opex. Apply ÷5 discipline: realistic expectation is single-digit annualized on $5–10k capital.
**Motivating finding:** e25's rank-2 wallet (`0xecb63caa`, $203M allTime PnL) shows a 3-hour session with 84% flat-regime BTC entries and passive-resting-quote fill composition — consistent with MM in low-vol windows. Hypothesis: can a solo operator replicate the surface at small scale?

## One-line verdict

**Build is physically possible from Tokyo VPS at ~$12/mo opex. Economic edge is structurally thin. Test on testnet first; do not deploy capital until paginated 60-day wallet pull validates the quiet-hours hypothesis AND paper-trade shows positive net-of-fees P&L over ≥30 days.**

## Scope

This experiment investigates whether a solo operator with $5–10k capital can profitably market-make HL BTC-PERP during identified low-volatility hours. Output is go/no-go for a 1–2 week build.

Four parallel recon agents were dispatched:
- **Agent A:** MM economics — fees, rebates, tick sizes, HLP mechanics, capacity for retail
- **Agent B:** Quiet-hours empirical characterization + rank-2 wallet overlap test
- **Agent C:** Competitive landscape — who's there already, HLP dominance, incidents
- **Agent D:** Technical stack + risk framework — SDKs, latency, opex, testnet path

Detailed reports in `agent_reports/`.

## Key findings by agent

### A) Economics — "accessible but structurally thin-edge"

- **Fee schedule (perps):** VIP 0 (<$5M 14d vol) = 0.015% maker / 0.045% taker. Rebate tiers require ≥0.5% of exchange-wide maker volume — unreachable on $5–10k.
- **Realistic solo stack:** VIP 0 + referral (–4% on first $25M) + Bronze HYPE stake ($1–2k for 100 HYPE) → effective maker ≈ **0.013%**, taker ≈ 0.040%. No rebates.
- **BTC-PERP specs:** tick = $0.1 (≈1 bp on ~$100k BTC). Min notional $10.
- **Typical top-of-book spread:** ~1 bp during normal hours. **After 0.013% maker fee, almost no captured spread remains.** Edge must come from inventory skew, not spread capture.
- **HLP:** protocol-owned ~$373–442M USDC vault, ~20% APR run-rate, quotes on the open book — competes with external MMs, isn't just a backstop. JELLY incident cost HLP ~$12M (Mar 2025).
- **Capacity for $5–10k solo:** naive 5× leverage supports ~$25k gross quoted; ÷5 discipline → **~$2.5k per side** realistic resting without adverse selection. Trivial vs exchange $3–5B daily volume.

### B) Quiet hours exist and are measurable; wallet-overlap test inconclusive

- **Bottom-quartile vol hours (UTC):** 03, 05, 06, 09, 10, 12 — roughly **03–12 UTC band** (Asia late / Europe open). Peak vol is 13–17 UTC at ~2× quiet-hour median.
- **Top-of-book spread during quiet hour (06 UTC):** 1 tick = $1 = **0.13 bps**. Bids thin, asks fat — directional pressure visible in book shape.
- **Rank-2 wallet overlap test:** SAMPLE ARTIFACT. HL `userFillsByTime` returned only the most recent batch (3 hours, 2026-04-21 00:53–03:50 UTC, 876 fills). **Cannot claim the wallet avoids active hours from this sample.** The 3 hours observed were in a below-median-vol window and fill composition is classic passive MM (719 Open Long, 14 Open Short, 100 Close Long, 37 Close Short) — directionally consistent with the MM-in-flat hypothesis, but not yet validated at 60-day horizon.
- **Mandatory next step before any build:** paginated `userFillsByTime(startTime=...)` across 60 days to validate hour-of-day selectivity.

### C) Competitive landscape — crowded at top-of-book, niche residual

- **Named institutional MMs:** Wintermute and Flowdesk confirmed as counterparties in Bitwise's HL ETF amendment (April 2026). Keyrock, GSR, Cumberland, DWF likely present given HL's $30B daily volume share.
- **HL has NO DMM program, NO special rebates, NO latency advantages.** Institutional MMs get same fees.
- **Latency floor:** median end-to-end latency for co-located clients ~200ms, 99p ~900ms. Third-party feeds (HypeRPC, Tokyo) ~135ms. **NZ → HL validators ~120–140ms physical floor — workable at the 100–200ms tier, not competitive sub-50ms.**
- **HLP limitations:** 4-day withdrawal lockup, risk caps post-JELLY (BTC leverage 40×, ETH 25×), HLP Liquidation Reserve. Its dominance is real but not absolute.
- **Public solo operators:** thin signal. Hummingbot HL connector exists; TreadFi/Gainium/OctoBot frameworks exist; no verified sustained monthly P&L disclosures found.
- **Outlier claim ($6.8k → $1.5M via rebate-farming):** apply ÷5 for survivorship — treat as ~40× ceiling, not replicable on $5–10k (requires ≥3% of maker volume share, architecturally unreachable at that scale).

### D) Technical stack — Tokyo VPS or don't build

- **Recommended:** Python 3.11 + `hyperliquid-python-sdk` v0.23.0 (MIT, actively maintained, `examples/basic_adding.py` is a working MM skeleton).
- **VPS:** Vultr High Frequency Tokyo ($12/mo, 2 vCPU / 2GB). Tokyo is not a preference — HL officially recommends it for lowest latency to validators.
- **Latency reality:** NZ direct ~200ms (dead); US-East ~160–190ms (marginal); **Tokyo VPS ~5–20ms (the only viable option)**. Auckland is your cockpit, not your server.
- **Monthly opex:** $12–90 (VPS + optional dedicated RPC).
- **Testnet path:** deposit ≥$5 USDC on Arbitrum mainnet → HL bridge → faucet 1000 mock USDC at `app.hyperliquid-testnet.xyz/drip` → point SDK at `api.hyperliquid-testnet.xyz`.
- **Top 3 reference repos:**
  1. [`hyperliquid-dex/hyperliquid-python-sdk`](https://github.com/hyperliquid-dex/hyperliquid-python-sdk) — canonical SDK + `basic_adding.py`
  2. [`fedecaccia/avellaneda-stoikov`](https://github.com/fedecaccia/avellaneda-stoikov) — reservation-price / spread math
  3. [`chainstacklabs/hyperliquid-trading-bot`](https://github.com/chainstacklabs/hyperliquid-trading-bot) — HL-specific auth/WS/order patterns

### Risk controls checklist (minimum viable)

1. Hard position cap: notional + % equity (e.g. $5k / 20%)
2. Daily drawdown kill: halt + cancel-all at −2% equity
3. Adverse-selection detector: one-sided fill ratio >75% over 5 min → widen 2× or pause
4. Quote sanity: reject quotes >0.3% from mark; halt if mid deviates >0.5% from reference CEX
5. Remote kill via ntfy webhook → systemd stop; phone dashboard
6. Heartbeat watchdog: no L2 update >2s → cancel all, reconnect
7. Nonce discipline: atomic counter (HL stores top-100 per address; collision = silent drop)
8. Post-upgrade handler: catch "only post-only allowed" errors, retry with ALO

## Combined verdict

| Angle | Finding | Blocker? |
|---|---|---|
| Economics | Accessible but ~1 bp spread against ~1.3 bp net maker fee → no spread edge | YES (structurally) |
| Quiet hours | Measurable, 03–12 UTC band, ~0.13 bp spread at 06 UTC | NO |
| Rank-2 validation | 3-hour sample, directionally consistent but not validated at 60d | YES (data gap) |
| Competitive | NZ 120–140ms floor; works at 100–200ms tier, not HFT | NO (for this tier) |
| HLP dominance | Competitor on open book; ~20% APR ceiling benchmark | NO (cap, not block) |
| Stack | Python + Tokyo VPS, $12–90/mo, SDK mature | NO |
| Testnet | Free, one-shot faucet, full API parity | NO |

**Two load-bearing blockers remaining:**
1. Spread capture is dead at current HL BTC microstructure for retail-tier fees. Edge must come from inventory timing (directional alpha disguised as MM), NOT from classical two-sided spread.
2. The rank-2 wallet's hour-of-day preference is unvalidated (3-hour sample).

## Recommended next steps (ordered)

1. **Paginated 60-day wallet pull** for rank-2 + rank-5 + rank-42. Validate hour-of-day preference. ~3 hours work, rate-limited.
2. **Testnet deploy of `basic_adding.py`** + risk controls. No cost, ~2 days. Tune spread/inventory parameters.
3. **30-day paper-trade on live L2Book** with book-walking fills + ≥50ms latency simulation (matches your e12 Polymarket harness pattern).
4. **Go/no-go on live $500 deployment** only if paper-trade shows positive net-of-fees P&L over 30 days.
5. **Scale to $5–10k** only after 30+ live fills confirm the paper-trade edge.

**Expected planning number (÷5-adjusted):** if the hypothesis holds and execution is clean, ~3–5% annualized on $5–10k = $15–50/mo. That is WORSE than e23 FLB ($400/mo at similar capital) unless the wallet-forensics deep-dive reveals a meaningfully stronger signal.

## Honest comparison against e23 FLB

| Dimension | e23 Polymarket FLB | e26 HL BTC MM |
|---|---|---|
| Planning return | $400/mo at $5–10k | $15–50/mo at $5–10k (÷5-adjusted) |
| Infra needed | Laptop + ntfy + $56 USDC | Tokyo VPS + testnet + ~$90/mo opex |
| Build cost | Already built | 1–2 weeks |
| Forward validation | 30-day collector + V2 cutover gate | Paginated wallet pull + 30-day paper-trade |
| Capacity cap | ~$25k | ~$2.5k per side; likely capped at $5–10k total before adverse selection |
| Risk of blowup | Low (small sizes, no leverage) | Medium (HLP competition, fat-tail liquidation events like JELLY) |

**e23 wins on every dimension except novelty.** e26 is defensible only as a learning exercise or as a necessary prelude to a larger synthetic/HYPE MM strategy (where the actual top-PnL lives — see e25).

## Reproducibility

- `data/btc_{1m,5m,15m,1h,4h}_candles.json` — HL BTC-PERP candles (various intervals, 3.5d–60d windows)
- `data/btc_hourly_vol.json` — hour-of-day realized-vol table + 4h flat-regime test
- `data/rank2_hour_distribution.json` — rank-2 wallet hour-of-day fill distribution (3-hour sample — see caveat above)
- `data/l2_snapshots.json` — 5 BTC book snapshots at 06:09 UTC (quiet hour)
- `data/fetch_candles*.py`, `data/analyze.py`, `data/l2_snapshots.py` — pipeline scripts
- `agent_reports/` — the four recon agent verdicts in full

## Related experiments

- [`../e25_hyperliquid_forensics/`](../e25_hyperliquid_forensics/) — the motivating wallet decomposition
- [`../e11_funding_arb_sensecheck/`](../e11_funding_arb_sensecheck/) — the CEX funding arb that killed via similar "spread eaten by fees" dynamics
- [`../e12_paper_trade/`](../e12_paper_trade/) — the Polymarket paper-trade harness that provides the pattern for step 3 above
- [`../e23_stratification/live_trader/`](../e23_stratification/live_trader/) — the competing deployable (e23 FLB) for honest comparison
