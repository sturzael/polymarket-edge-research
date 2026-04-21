# Measuring Structural Inefficiency in Prediction Markets

**A systematic investigation of solo-operator trading strategies on Polymarket, including the construction of a negative-risk arbitrage scanner and retrospective analysis of cross-outcome sum violations.**

> 👉 **Not a markets person?** Read the [Explain Like I'm Five version](docs/ELI5.md) instead.

> ⏩ **Looking for the current-state summary?** Jump to [Current state (2026-04-21)](#current-state-2026-04-21) — what's deployable, what's killed, what's open.

---

## Current state (2026-04-21)

The ten-thesis falsification described in the abstract below is **Stage 1** of this project. Stage 2 (cross-venue calibration) and Stage 3 (stratification + deployment scoping) have since found one deployable edge and opened an active investigation on a second. Summary:

### ✅ Deployable now (subject to forward validation + V2 cutover)

- **[e23 — Polymarket sports FLB](experiments/e23_stratification/SYNTHESIS.md)** — MLB/NBA/NFL/NHL game-outcome favorites at T-7d in 0.55–0.60 price bucket, ≤14d lifespan, ≥$5k window volume. Measured +25.8pp edge on 120-market bucket (z=7.6). Scanner + notification infra live in [`experiments/e23_stratification/live_trader/`](experiments/e23_stratification/live_trader/). Planning number: **$4–11k/yr on $5–25k capital** (÷5-adjusted).

### 🔴 Null results from the 2026-04-21 Solana/HL recon

- **[e24 — Orca USDC/SOL CL LP stratification](experiments/e24_orca_cl_lp/)** — closed. Pool-level simulation calibrated against Heimbach 49.5% loser-rate prior returns no cell meeting the pre-committed n≥200 + median APR>5% gate. Narrow ranges lose −96 to −121% APR in the observed SOL −31% regime.
- **[Solana perps funding arb](experiments/e11_funding_arb_sensecheck/)** — confirmed killed. Drift paused post-$286M exploit; Jupiter/Flash are one-way borrow-fee (not bilateral funding); Zeta too thin. No cross-venue divergence to trade.
- **Solana LST NAV arb** — ~25bps steady-state (inside Sanctum unstake fee); depegs minute-scale, require co-located MM infra.
- **[e27 — HL synthetics slice MM](experiments/e27_hl_synthetics_recon/)** — closed. The "5–20× wider spreads on synthetics" hypothesis was falsified against live L2 data. Top xyz:SP500 / xyz:CL / xyz:BRENTOIL / xyz:SILVER synthetics quote at 0.14–0.94 bps (comparable to BTC). Wide-spread assets (LIT 4bp, MON 4bp, xyz:MSTR 6bp) lack volume AND top-wallet concentration. Best candidate ÷5-planning: $129/mo at $5–10k. Top wallets on synthetics are predominantly directional traders (rank-28 is 91% taker), not MMs — their PnL is not replicable by a market-making book.

### 🟡 Open investigations

- **[e25 — Hyperliquid top-wallet forensics](experiments/e25_hyperliquid_forensics/)** — descriptive classification of top-50 HL wallets using the e9 methodology. Headline: the Polymarket "mostly momentum-lucky" pattern **inverts on HL** — distribution is heavily left-skewed toward structural signatures. 10 of 24 top wallets don't trade BTC/ETH/SOL at all — real top-PnL book lives in synthetics/HYPE/alts. Content-monetizable as a standalone finding.
- **[e26 — HL BTC-PERP MM viability](experiments/e26_hl_mm_investigation/)** — 4-agent recon complete. Verdict: build possible from Tokyo VPS at $12–90/mo opex; classical spread capture is dead for solo retail; niche inventory-management in quiet hours (03–12 UTC band) is the only residual path, capped at HLP-like ~15–20% APR gross. Deployed capital expectation ÷5-adjusted below e23. Defer build until paginated 60-day wallet pull validates rank-2 wallet's hour-of-day selectivity.

### 💡 Byproducts worth monetizing independently

- **Methodology** (÷5, counter-memo, pre-registration, default-to-KILL). Applied across 25+ experiments. Unusual in crypto research; saleable as due-diligence consulting or a report product.
- **[Cross-venue FLB synthesis](experiments/SYNTHESIS_flb_cross_venue.md)** — Polymarket T-7d +25pp vs Betfair ≤±6pp vs Azuro +0.4pp across 1.9M resolution events. Novel empirical finding; publication-ready.
- **[The inverted HL distribution](experiments/e25_hyperliquid_forensics/README.md)** — no prior public work decomposes HL top-wallet PnL into structural vs regime components.
- **API/microstructure findings** — see the [Polymarket microstructure findings](#polymarket-microstructure-findings) section below.

See [SYNTHESIS.md](SYNTHESIS.md) for the original Stage 1 arc + the 2026-04-19 post-synthesis update, and [SYNTHESIS_flb_cross_venue.md](experiments/SYNTHESIS_flb_cross_venue.md) for the cross-venue work.

---

## Abstract

This repository documents a structured empirical investigation into whether systematic trading edge exists for retail operators on Polymarket, the largest USD-denominated prediction-market venue. Across two weeks, ten trading strategies were identified, historically backtested against a 954M-row on-chain dataset, and forward-validated against live market behavior. All ten were falsified as retail-accessible edge sources. The negative result is specific to the operator profile studied ($1k bankroll, 200-300ms network latency, REST-only polling); reopening conditions under which the conclusion would flip are documented.

The project produced three durable outputs independent of the trading conclusion: (1) a negative-risk multi-outcome arbitrage scanner with phantom-depth verification, capable of detecting real-time sum violations across Polymarket's full active market set; (2) retrospective frameworks (Q1–Q3) measuring historical tail-outcome rates, arbitrage window persistence, and long-duration standing violations against on-chain trade data; (3) a catalog of Polymarket microstructure findings (API quirks, fee formula empirics, resolution-lag measurements) not documented in existing public sources or academic literature.

---

## Core findings

### On retail-accessible edge

Across ten strategies — sports settlement-lag arbitrage, 5-minute crypto directional, hourly strike-ladder market-making, static monotonicity arbitrage, crypto-barrier residual, long-tail liquidity provision, dump-and-hedge pair-sum arb, funding-rate arb, top-wallet copy-trading, and negative-risk multi-leg arbitrage — none produced retail-accessible edge at $1k bankroll from a 200-300ms-latency operator.

The strongest historical candidate (sports settlement-lag) showed +3.99% net edge in backtests (n=47, SII-WANGZJ on-chain data through 2026-03-31). Live observation found zero opportunities at the 0.95-0.97 target entry zone: single-game sports markets close (via UMA liveness) within ~2 hours of game end, faster than a 2-second polling cadence can reliably capture the pre-close price walk through the profitable zone.

The negative-risk arbitrage scanner identified 39 live sum-violations on 2026-04-20, of which 18 initially classified as "guaranteed" and 21 as "probabilistic." Manual verification revealed that the largest apparent violations (+42% on Nobel Peace Prize, +37% on Apple CEO) were not arbitrage but the market correctly pricing tail outcomes not included in the listed candidate set. The genuinely structural arbs that survived scrutiny cluster at ≤3% edge with multi-month capital lockup, producing expected annual return of ~$400-900 at $1k deployed — below the threshold where execution risk (non-atomic multi-leg order submission, partial-fill exposure) makes the strategy net-negative.

### On arbitrage persistence

Retrospective analysis of historical negative-risk sum violations (n=30 events with observable trade activity, 90-day window) found:

- Median arbitrage window duration: 1.0 minute
- 75th percentile: 1.2 minutes
- 95th percentile: 2.8 minutes
- Maximum observed in sample: 5.0 minutes
- Edge decay pattern: abrupt termination (window ends when a single counterparty takes the arb whole), not gradual compression

Long-duration windows (≥24 hours) appeared in only 2.2% of sampled events, concentrated in low-volume markets with minimal market-maker attention. The pattern is consistent with active bot competition at median-window scale and passive mispricing at the long-duration tail.

### On category-level tail-outcome rates

Resolution analysis of 412 historical events (90-day window) across closed-set market categories (sports game outcomes, weather thresholds, politics with locked ballots) found zero tail-outcome resolutions — all 412 events resolved to listed candidates. Open-ended categories (awards, executive appointments) were underrepresented in the sample (n=5 awards, n=0 CEO-type appointments) and cannot be validated from this dataset; separate analysis of active markets in these categories confirmed that apparent sum-violations correspond to correctly-priced tail probabilities for outcomes not on listed slates.

### On market maker operating points

Detailed analysis of one high-frequency operator (pseudonymously tracked, 500 trades over 125 days, $1.32M net deployed, $101k portfolio value) confirmed a "scale over edge" profile: median entry at 0.981, 41% of positions opened at prices ≥0.99, per-trade edge approximately 0.1%, positions sized $20k-150k. This operating point is inaccessible at retail scale; the same mechanical strategy at $100 trade size produces $0.10 per trade in gross edge, before fees.

### On latency compression trends

Saguillo et al. (2025) report that general Polymarket arbitrage window duration collapsed from 12.3 seconds (2024) to 2.7 seconds (2025), with 73% of arbitrage profits captured by sub-100-millisecond operators. Our findings are consistent with this compression at the median-window level (1 minute median for neg-risk arbs); long-duration outliers in low-volume markets appear to persist independently, suggesting a bifurcated regime rather than uniform tightening.

---

## Methodology

### Data sources

**Primary dataset:** SII-WANGZJ Polymarket on-chain archive, 954M rows spanning contract events through 2026-03-31. Accessed via HuggingFace with custom parquet streaming to handle 107GB data volume.

**Live market data:** Polymarket Gamma API (market metadata), CLOB API (order books, trades), data-api (wallet trade history). Collector code is included; all endpoints are public and unauthenticated.

**Supplementary:** Binance spot prices via public API, Deribit options IV for probability baselines, UMA subgraph via GraphQL for oracle resolution tracking.

### Strategy evaluation framework

Each of the ten strategies was evaluated against a consistent pipeline:

1. **Hypothesis formalization.** Specific claim about market inefficiency, operator profile, and expected edge magnitude.
2. **Historical backtest.** SII-dataset query with pre-committed entry/exit rules, fee modeling (tested across 0/100/300 bps to characterize fee-sensitivity), and sample-size requirement.
3. **Counter-memo.** Before accepting a positive result, an adversarial memo written from the same dataset identifying silent-failure modes (adverse selection, capacity limits, regime dependence, infrastructure requirements).
4. **Live observation.** Real-time measurement of the strategy's target conditions over a minimum 24-hour window, with explicit comparison against backtest distribution.
5. **Kill criterion.** Pre-committed thresholds for abandonment (net edge < 0.5%, negative PnL at n=75, >50% missed-fill rate) applied without modification after results.

### Methodological rules developed

Six rules accumulated during the project that meaningfully changed outcomes:

1. **Divide revenue estimates by 5 before acting on them.** Initial estimates in this project were empirically 3-10× too high across every thesis. The heuristic is crude but directionally correct.
2. **Write the counter-memo from the same data.** Forces explicit modeling of silent failure modes before commitment.
3. **Measure raw before parameterizing.** Empirical baseline first; fee/latency/capture adjustments second.
4. **Sample size drives the decision window, not vice versa.** Pre-commit criteria before seeing data to prevent observed-magnitude from biasing the threshold.
5. **Distinguish "pattern exists historically" from "pattern is capturable now."** Backtest is necessary but not sufficient; live observation is required to close the loop.
6. **Phantom edge = market correctly pricing tail risk.** Apparent large mispricings in open-ended categories reflect implicit tail probabilities for outcomes not on listed slates, not arbitrage.

---

## Scanner implementation

### Architecture

The negative-risk arbitrage scanner ([`experiments/e15_neg_risk_arb/`](experiments/e15_neg_risk_arb/)) operates on a detect-verify-log pipeline:

**Detection:** Queries Gamma API for all active multi-outcome markets, filters to categories with ballot-locked or otherwise closed outcome sets, computes the sum of best-ask prices across all outcomes. Flags markets where sum < 1.00 for further verification.

**Verification (phantom check):** For each flagged market, queries CLOB directly for current book state on each outcome. Confirms that the aggregate ask depth observed in Gamma is backed by real CLOB orders, not stale-quote artifacts. Cross-references market resolution rules against the listed outcome set to identify open-ended tail-risk cases (the false-positive pattern that produced the Nobel/Apple CEO apparent-arbs).

**Logging:** Persists flagged opportunities with timestamp, sum, capturable depth per leg, category classification, and resolution horizon to SQLite. Hourly logger runs autonomously, building a persistence dataset on arb frequency and lifetime.

### Retrospective frameworks

**Q1 (tail-outcome rate):** For each resolved event in the observation window, compare the resolved outcome against the outcome set that had been listed when the market was active. Measure the rate at which events resolved to outcomes not on the listed set, stratified by category.

**Q2 (window persistence):** Reconstruct historical sum-of-outcomes over time for each event with observable trade activity. Identify periods where sum < 1.00 and measure duration distribution, edge magnitude at peak, and termination shape (gradual compression vs abrupt).

**Q3 (long-duration arbs):** Filter to events with arb windows ≥24 hours. Measure frequency, depth distribution, and category concentration. Distinguish populated long-duration arbs (structural mispricing) from selection-biased present-sample artifacts.

### Extensions built but not required

Paper-trade harness ([`experiments/e12_paper_trade/`](experiments/e12_paper_trade/)) with dual detection paths (sports-feed-triggered + book-poll), per-cell drawdown breakers, event-concentration gates, missed-opportunity logging, and V2 cutover pause/resume protocol. Not ultimately deployed given the upstream strategy falsifications but available for any future investigation.

---

## Polymarket microstructure findings

A consolidated list of protocol and API behaviors documented during the project. These are included because they cost real debugging time and are not documented in Polymarket's public documentation or prior academic literature.

**API quirks:**
- Gamma API silently drops past-expiry markets from listings; use CLOB for resolution detection.
- Gamma's `condition_ids` filter requires repeated query parameters, not comma-separated values.
- CLOB's `/markets?condition_id=X` silently ignores the filter parameter; use the singular-path form `/markets/<cid>` instead.
- CLOB's `/book` endpoint returns bids sorted ascending (lowest price first); `bids[0]` is the worst bid. Use `max(float(l["price"]) for l in bids)` to identify the top of book.
- Gamma rate limits: 4000 req/10s general, 300 req/10s on `/markets`, 500 req/10s on `/events`. Documented in their internal headers but not surfaced prominently.

**Protocol facts:**
- Resolution lag averages ~400 seconds past nominal expiry, not seconds as might be assumed from the UMA liveness window.
- Fee formula is `shares × feeRate × p × (1−p)` — symmetric, peaks at p=0.5. Not the `min(p, 1-p)` form sometimes assumed.
- Published fee rates (3 bps sports, 7.2 bps crypto) are ceilings; empirical on-chain fees measured zero across a 143-trade sports sample through 2026-03-31. V2 cutover may change this.
- CLOB priority is price-time, not pro-rata. Cancel-before-match latency is not publicly documented.
- UMA resolution: 2 hour liveness window, $750 pUSD bond per side. Sports auto-proposer posts within minutes of game end.
- CTF Exchange + CLOB V2 cutover: 2026-04-22. No V1 backward compatibility. Order struct changes: removed `nonce`/`feeRateBps`/`taker`, added `timestamp`/`metadata`/`builder`.

**Operational:**
- For `*-updown-*m-*` slug patterns, `endDate − startDate` gives the parent series duration, not per-contract duration. Parse the slug regex directly.
- Market closure (`closed=true`) happens within ~2 hours of game end on sports markets, meaningfully before UMA resolution finalization. This is why post-resolution arb windows at low prices are historically visible but not live-capturable.

---

## Conditions under which the negative result might flip

The conclusion "no retail edge at $1k bankroll from 200-300ms latency" is specific to the operator profile studied. Conditions under which the null result would merit re-examination:

- **Capital scales to $10k+.** Barrier tail-insurance strategies (documented on other operator wallets) appear viable at this threshold with expected return of $4-9k/year based on retrospective analysis of one operator's 28-day trading record.
- **Latency drops to VPS-grade.** Median-window neg-risk arbs become accessible at sub-100ms execution latency; current 200-300ms excludes most capture attempts.
- **Atomic multi-leg execution becomes available.** Current CLOB batch endpoint is parallel, not atomic; partial-fill risk eats most of the theoretical edge on multi-leg trades. V2 cutover may or may not address this.
- **A specific high-capacity operator demonstrably exits the space.** If LlamaEnjoyer-scale operators stop servicing particular market categories, capacity opens for smaller operators at the same operating point.
- **A new market type launches with bot-light coverage.** V2 may introduce order types or market structures that have not yet been arbed flat; the scanner is immediately applicable.

None of these is venue expansion. Investigation of Kalshi, Probo, Manifold, or other prediction markets was considered and rejected on the basis that the binding constraints (latency, capital, execution infrastructure) travel with the operator rather than the venue.

---

## Tooling included

All code is MIT-licensed and runnable against public APIs. Raw data is gitignored for size; collectors are included, data is regenerable.

- [`experiments/e1`](experiments/e1_post_expiry_paths/) through [`e15`](experiments/e15_neg_risk_arb/) — Stage 1 thesis investigations (the ten-strategy sweep), self-contained
- [`experiments/e15_neg_risk_arb/`](experiments/e15_neg_risk_arb/) — scanner, phantom-depth verifier, retrospective frameworks, hourly logger
- [`experiments/e12_paper_trade/`](experiments/e12_paper_trade/) — paper-trade harness with V2 cutover handling
- [`experiments/e13_external_repo_audit/`](experiments/e13_external_repo_audit/) — SII-WANGZJ dataset integration and wallet forensics
- [`experiments/e16_calibration_study/`](experiments/e16_calibration_study/) — Polymarket sports FLB calibration (the +25pp finding at T-7d)
- [`experiments/e18_drift_solana/`](experiments/e18_drift_solana/) through [`e22_cross_venue_spread/`](experiments/e22_cross_venue_spread/) — cross-venue FLB work (Drift, Baozi, Azuro, Betfair, Smarkets)
- [`experiments/e23_stratification/`](experiments/e23_stratification/) — 6-dimension stratification + **[`live_trader/`](experiments/e23_stratification/live_trader/)** (the currently-deployable FLB scanner)
- [`experiments/e24_orca_cl_lp/`](experiments/e24_orca_cl_lp/) — Solana CL LP stratification (clean null)
- [`experiments/e25_hyperliquid_forensics/`](experiments/e25_hyperliquid_forensics/) — HL top-wallet structural-vs-momentum decomposition (inverted-from-Polymarket finding)
- [`experiments/e26_hl_mm_investigation/`](experiments/e26_hl_mm_investigation/) — HL BTC-PERP MM viability (4-agent recon, defer build)
- [`experiments/e27_hl_synthetics_recon/`](experiments/e27_hl_synthetics_recon/) — HL synthetics MM recon (5–20× hypothesis falsified; extends defer-build verdict across all of HL)
- [`experiments/SYNTHESIS_flb_cross_venue.md`](experiments/SYNTHESIS_flb_cross_venue.md) — cross-venue meta-synthesis
- [`probe/`](probe/) — 24-hour Polymarket market structure reconnaissance tool
- [`docs/`](docs/) — findings log, null results, methodology, project postscript

Python 3.12, dependencies managed with [uv](https://github.com/astral-sh/uv).

```bash
uv sync
uv run python -m probe.main --hours 24
uv run python experiments/e15_neg_risk_arb/scanner.py
```

---

## A note on LLM-assisted research

This project was conducted with Claude as a research collaborator across specification, implementation, review, and iteration. The workflow accelerated the research meaningfully; it also introduced specific failure modes worth documenting.

Observed LLM failure modes and their mitigations:

- **Estimate inflation.** Polished revenue projections consistently ran 3-10× higher than what the underlying data supported. Mitigation: apply the ÷5 heuristic (rule 1) before acting on any LLM-produced projection.
- **Stale-memory citations.** In at least one instance (crypto funding rates), the LLM cited historical APY figures from memory that no longer reflected current market conditions, without prompting verification. Mitigation: treat LLM-cited factual numbers as hypotheses requiring live confirmation, not authoritative references.
- **Motivated reasoning toward pre-existing conclusions.** When intermediate results pointed toward strategy falsification, the LLM occasionally generated reasoned alternatives preserving the original hypothesis. Mitigation: rule 2 (counter-memo from same data) and rule 4 (pre-committed kill criteria).

These are not arguments against LLM-assisted research. They are operational observations about where the human partner must remain skeptical. The LLM is an exceptional research assistant and an unreliable analyst. Polish level is not correlated with accuracy.

---

## Citation

If referencing this work:

```
Sturzaker, E. (2026). Hunting for Edge on Polymarket: A Structured Falsification.
GitHub: sturzael/polymarket-edge-research
```

## Disclosure

No capital was deployed. No trading was conducted. All findings are based on observation of public Polymarket data, public wallet activity, and public market infrastructure. Wallet analysis is at the behavioral-pattern level; no claims of informed trading or misconduct are made against any named wallet or operator.
