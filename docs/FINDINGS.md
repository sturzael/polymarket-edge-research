# Findings — running log

Chronological, appended as we learn. Dated in UTC unless noted. Session started 2026-04-18.

---

## Session 2026-04-18 — architecture pivots + probe launch

### Plan evolution (high level)

The plan went through three reframings before the first line of code:

1. **v0 — funding-rate arbitrage POC.** Rejected by the user as too safe and conventional; they wanted asymmetric-upside opportunities.
2. **v1 — 7-idea asymmetric scan** (Filing Reader / Signal-to-Settle / Sharp-to-soft / Liquidation Radar / Cliff Watcher / Cross-language / First-mover). User selected ideas 2 + 6, then re-scoped to…
3. **v2 — event-impact MVP** (news → crypto reaction), then added Fast Feedback Mode (live z-score classifier), Polymarket streams, and an Expiry Microstructure Mode as primary same-day signal loop. Sidecar wallet watcher added as optional isolated process.
4. **v3 (current) — cheap 24h reconnaissance probe only** to answer whether short-duration Poly crypto markets exist before committing to the full build. User also flagged multiple analytical problems in v2 that would have invalidated the study (see "Analytical issues flagged" below).

See `PLAN_HISTORY.md` for the detailed narrative of each pivot.

### Analytical issues the user flagged in v2 (must fix before full build)

These apply to any future full build using expiry mode, not the probe itself:

- **`|poly − outcome_bin|` is backwards as a signal quality metric.** Its expected value for a calibrated market is `2p(1-p)` — maximized at p=0.5, *minimized* by certainty. Our rubric "high err = strong signal" was inverted. Replace with **calibration curves** (bucket poly_price, compare empirical YES-rate to midpoint), **Brier score vs a spot-implied GBM benchmark**, and **lead-lag cross-correlation** of Δpoly vs Δspot.
- **The "mispricing" flag was hindsight-biased.** "Market underestimated the move AND spot moved in direction of realized outcome" — these are not independent events for BTC-up/down markets. Need lead-lag analysis with τ>0 threshold.
- **Reference-feed matching is the validity hinge, not a footnote.** Each Polymarket market resolves against a specific oracle (Chainlink / Coinbase / Binance). Measuring against Binance spot while the market resolves against Coinbase could yield a "mispricing" signal that is just Binance↔Coinbase latency and not tradable on Polymarket.
- **1 Hz REST + midpoint is too coarse.** Use CLOB websocket + matched-venue spot websocket, record bid+ask separately, compute microprice/midpoint at analysis time.
- **Cross-language RSS is second-order.** Cut from v1.

### What's in the repo

- `src/prices.py`, `src/storage.py` — scaffolding from v2; not currently used.
- `probe/` — the reconnaissance probe described below. Running now.
- `config.yaml` — stale v2 config; left for reference.

---

## Probe implementation notes

### Architecture

Five concurrent asyncio tasks:
- `discovery_loop` — every 45s: paginate `gamma-api/markets`, classify crypto via keyword, upsert to `markets` table. Horizon = 25h.
- `spot_loop` — every 10s: ccxt Binance `fetch_tickers` for 6 underlyings (BTC/ETH/SOL/BNB/XRP/DOGE), keep latest in-memory. Noted as a **known invalidity** for markets that resolve against Coinbase/Chainlink — for the probe this is fine since we're only measuring existence/cadence.
- `normal_sampler` — every 15s: bulk-fetch gamma for markets with `time_to_end > 120s`, write snapshots.
- `final_sampler` — every 5s: bulk-fetch gamma for markets with `0 < time_to_end <= 120s`.
- `resolution_checker` — every 10s: per-market CLOB `/markets/<cid>` call for markets past nominal end. Detects `tokens[].winner`, writes resolution row with accurate lag.

### API gotchas hit during the build (in order)

1. **`gamma-api/markets?condition_ids=X,Y` silently returns 0 rows.** Required repeated query-param form (list of tuples with aiohttp). Cost: one failed smoke run producing 0 snapshots.
2. **`gamma-api/markets/<conditionId>` returns HTTP 422.** Gamma's path expects the numeric `id` field, not the hex `conditionId`. Workaround: `/markets?condition_ids=<cid>` always.
3. **Gamma-api purges markets from listings the moment their `endDate` passes.** No way to read resolution status via gamma. Required a second endpoint.
4. **`clob.polymarket.com/markets?condition_id=X` silently ignores the filter.** Returns the default unfiltered page. The working form is `clob.polymarket.com/markets/<conditionId>` (singular path). That endpoint keeps markets visible post-expiry and exposes `tokens[].winner` and `tokens[].price`.
5. **`duration_s = endDate − startDate` from gamma is the series duration, not the per-contract duration.** For `*-updown-Nm-<ts>` markets this returns ~23h or 1d (the rollover series). The per-contract duration must be parsed from the slug via regex: `-updown-(\d+)(m|h|d)-`.

### Ecosystem facts confirmed

- **5m Polymarket crypto Up/Down markets exist and are abundant.** First discovery pass at 2026-04-18 14:21 UTC found 607 active 5m markets (65%), 204 15m (22%), 32 4h (3%), 36 daily (4%), 50 weekly (5%). Total 929 crypto markets in the 25h horizon.
- **Six underlyings covered, roughly balanced:** ETH 167, BTC 165, SOL 153, XRP 152, DOGE 145, BNB 145, TRX 2.
- **Real Polymarket resolution lag ≈ 400 s** (6.6 min) past nominal expiry, observed on the first six resolutions (ETH/BNB/BTC/DOGE/SOL/XRP from the 14:20 batch all landed in a tight 397–399s band). This is the concrete floor for any execution strategy on these markets.
- **Discovery throughput healthy:** 3000 active markets scanned per pass (~15 pages × 200), ~10–15 new crypto markets per 45s cycle.

### Probe state as of ~14:32 UTC

- PID alive, 953 crypto markets discovered, 23k snapshots, 6 clean resolutions, 0 UNRESOLVED, 0 errors.
- Expected final count: several hundred resolutions over 24h.

---

## Experiments — combined findings (2026-04-18 ~15:00 UTC)

All seven experiments first-passed while the probe ran. Per-experiment details live in `experiments/e*/README.md`. Headlines below.

### e7 — Resolution sources (highest-impact finding so far)

**88% of crypto markets (846/958) resolve against Chainlink Data Streams**, not Binance or Coinbase. Distribution is perfectly uniform across the six underlyings (141 each). Only ~5% resolve to Binance (the longer-dated daily/weekly markets like `ethereum-above-$X`).

**v2 consequence:** the primary spot feed must be Chainlink Data Streams, not Binance via ccxt (what the probe currently uses). Our existing spot data is fine for characterizing the market but is a **reference-feed mismatch** for any tradable signal. This is exactly the validity problem the user flagged.

### e5 — Historical backfill spike

CLOB retains per-cid resolution state indefinitely (tested up to our latest resolutions; no ceiling found). `data-api.polymarket.com/trades?market=<cid>` returns up to ~1000 trades per market — covers the full 5m market lifetime.

**But there is no enumeration path for historical updown cids.** Both gamma-api and CLOB's paginated `/markets` listings filter the updown series out entirely. Confirmed by scanning 10,000 markets across 10 CLOB pages — zero updown.

**v2 consequence:** The probe's unique value is cid discovery, not price sampling. Once we record (cid, nominal_end_ts, resolution_source), we can reconstruct the full price path any time later via data-api + CLOB. This dramatically simplifies v2: **skip the live 1-Hz intensive sampler for data collection** — it's only needed for live trading decisions.

### e2 — Deribit IV baseline

BTC (930 options) and ETH (786 options) snapshotted 2026-04-18 14:40 UTC. Nearest expiry 24APR26 (6 days). Full chains saved to `experiments/e2_deribit_iv/*.json`. Second snapshot planned for 24h later to compute realized-vs-implied vol over the probe window. Deribit IV is the independent benchmark against which any Polymarket 5m-market implied probability should be sanity-checked.

### e1 — Post-expiry price path (headline result)

**The tradable window is pre-T, not post-T.**

Pulled full trade streams for 20 resolved markets. 16/20 classify as "snap" (price touches within 2% of target in first 30s post-expiry). 1 drift. 3 no-data. No "slow" cases.

This rules out two of three candidate strategy universes:
- ❌ "prices drift toward 0/1 over 400s" → we don't see this
- ❌ "prices stuck at 0.9/0.1 for dispute window" → we don't see this
- ✅ "snap at T; residual mispricing is in the final seconds BEFORE T"

**One striking case:** BNB `-updown-5m-1776478800`: market priced 99% DOWN in final 60s but **resolved UP**. 92¢ price swing within 30s. This is the shape of real mispricing and exactly the case where spot→oracle lag would be exploitable IF the spot feed matches the oracle's reference. Tied directly to e7.

### e6 — Rate limit baseline

Sequential 10-sample latency check (1 req/s):
- gamma-api: ~120 ms p50
- CLOB /markets (paginated): ~270 ms p50 (heavy response)
- CLOB /markets/<cid>: ~150 ms p50
- data-api /trades: ~100 ms p50

Zero 429s observed. Actual rate-limit ceiling was not probed (sandbox-blocked the escalating-burst test as potentially abusive).

### e3 — Cross-exchange lead-lag (rig calibration)

4-minute smoke on Binance + Coinbase BTC websockets. 1374 trades captured (∼25% of received trades were dropped by per-row SQLite commit contention — batching fix noted in experiment README).

At 100 ms binning: **peak cross-correlation at +100 ms lag (Binance leads Coinbase)**, matching published 50–200 ms lead-lag literature. At coarser bins the lead collapses into the zero-lag bucket, as expected.

**Rig works — we can detect sub-second lead-lag.** For Chainlink-resolved markets the binding constraint will be Chainlink's update cadence (seconds), so our resolution is sufficient.

### e4 — Book depth (partial)

Mid-life 5m markets show **bid=0.01 / ask=0.99 across 40-60 price levels** with stub orders. $500-$40k in notional, but only at the extremes. **Midpoint (0.50) is meaningless during mid-life.** Use `lastTradePrice`, or restrict analysis to final-stretch windows where MMs post tighter quotes.

5m markets arrive in quantized 300-second batches — at any instant there is exactly one "active" market per underlying in each lifecycle stage. Full final-stretch depth sampling requires a 1h passive collector (sandbox-blocked the background spawn — user approval needed).

---

## Concrete v2 design changes (from experiments)

Translating the findings above into the v2 build:

1. **Primary spot feed: Chainlink Data Streams** — not Binance via ccxt.
   - Action: investigate public access to Data Streams. If it requires a Chainlink node / verifier, we may need to fall back to Chainlink's on-chain aggregator (5-10s lag, acceptable for measurement).
2. **Kill the live 1 Hz intensive sampler from the plan.** The probe records cids, the analysis happens offline from data-api + CLOB.
   - Storage reduces ~100x.
   - Live sampler only re-introduced if/when we go to live trading.
3. **Analysis metrics (per user's earlier feedback):** calibration curve + Brier vs GBM baseline + lead-lag cross-correlation at ≥100 ms resolution. All computable from the retroactive trade stream — no new live collection.
4. **Use lastTradePrice as the price signal during non-final-stretch phases.** Midpoint only meaningful in final stretch once MMs tighten.
5. **Analysis target: pre-T mispricing, not post-T drift.** Specifically, T-15 s through T-0 s window: does pre-T price diverge from imminent spot-determined fate?
6. **Out-of-scope for v2, on the roadmap for v3:** rate-limit ceiling test, full-hour final-stretch book sampling, 2h lead-lag run, Polymarket WS integration, wallet-flow sidecar.

---

## Opportunity refinement (methodology critique + new data, ~03:30 UTC)

After a second-opinion review flagged three methodology errors (below) I pulled additional data and revised the opportunity writeup. Full details in `OPPORTUNITY_HOURLY_LADDER_MM.md`.

Critical corrections:
1. **Executable monotonicity-arb sweep: confirmed mirage.** 0 arbs across BTC + ETH "above-K" cohorts at bid/ask. All stale-print arbs disappear when you switch from `lastTradePrice` to executable quotes.
2. **Volume attribution was wrong.** The $233k "BTC cohort" claim aggregated above-K + dip-to + hit markets. Breakdown: above-K is **$82/strike/day**; barrier markets are **$50k-167k each** BUT most is a final-hours settlement rush, not steady-state flow.
3. **Real book structure on balanced-probability markets** (example: ETH-above-2400 at 12.5h to expiry, last=0.71): penny stubs at 0.01/0.99 with $48k depth each, plus real MM depth at 0.20 ($12.7k) and 0.93 ($2.9k). **73¢ of untouched space at fair=0.71.** That's the real LP niche.
4. **Revised monthly-revenue estimate:** $300-2,000/month on $10k capital (down from the $4.5k-$16k first draft), $3-10k/month realistically at $50k, assuming:
   - Adverse selection takes 30-60% of gross spread captured
   - We catch 10-30% of in-the-window retail flow
   - Polymarket fees are zero or near-zero (unresolved, pending $10 experiment)

### The three methodology errors (would have made the backtest 3-10x too optimistic)
- **Queue-position / "I'd have filled at X"**: historical fills tell you what happened, not what a quoting MM would have captured. Need to distinguish tape-walking trades from in-spread fills.
- **Adverse selection unmodeled**: fills are disproportionately "toxic" (spot just moved). Must mark P&L at `fair_value(fill_ts + 10s)` and apply cancel-latency filters.
- **Stale-print arb signals**: monotonicity violations on `lastTradePrice` don't exist at executable bid/ask.

### Unresolved critical unknowns (in priority order)
1. **Polymarket maker fee** (`maker_base_fee: 1000` field, unit unclear). Requires one $5-10 live trade to settle. Blocker for all capital deployment.
2. **Real competitive density**: how fast do existing quoters react? Needs a sub-second book-update sampler (sandbox-blocked the background spawn tonight).
3. **Proper backtest P&L** with adverse-selection modeling. Budget 6-10h, not 4h.

### Workflow going forward
1. Fee experiment — $10 trade (user has to execute; requires funded Polymarket wallet)
2. Revised backtest on 1 week of historical trade data with corrected methodology
3. 2-week paper run (decision gate to real capital)

## FURTHER UPDATE ~16:35 UTC — Recon A kills the `above-K` MM strategy

Four-minute observation of `ethereum-above-2400-on-april-18` (11.5h to expiry) with simultaneous ETH spot:

- ETH spot moved +0.15% over 4 min
- Rational inside bid tracked spot from 0.50 → 0.55 (spot-leader, ~30s lag)
- Rational inside spread held steady at 2-3¢ the entire time
- This is an **active professional MM**, not a retail quoter

**Also a correction on my earlier analysis:** CLOB `/book` returns bids sorted *ascending* (lowest first), so `bids[0]` is the WORST bid, not the best. Gamma-api's `bestBid` field was the true inside quote all along. The "73¢ empty space" I claimed existed in the first draft writeup **does not exist** — the real inside quote is 2-3¢ and actively managed.

**Revised verdict on the MM opportunity (the `above-K` ladder version):** dead for a laptop-grade operator. Net expected edge near zero after adverse selection against faster / smarter competition. Down-rank from "strongest current opportunity" to "likely dead without stronger infra."

**The methodology rules stated earlier would have caught this.** Rule 2 (write the counter-memo from the same data) produced Hypothesis 1 — "the 0.20 bid isn't retail, it's a sophisticated MM doing exactly our strategy." Recon A confirmed it within 4 minutes of foreground data. Rule 1 (÷5 the estimate) no longer matters because the estimate is zero.

**What remains open:**
- Barrier markets as vol-event plays (Recon B stalled because probe-tracked barriers hadn't resolved yet; will resolve over the next 1-12h on their UMA cycle)
- UMA disputes (Recon C: 0 disputes in 1000-market sample; rare but not yet eliminated)
- New-cohort first-60s pricing (Recon D: 5m cohort opens seeded at 0.51 and stays there until final minute; no mispricing at listing)
- Week-long watcher (e8) to measure MM presence density across many markets and times
- Long-tail non-crypto markets (not yet investigated)

**Meta-lesson:** the optimistic first draft was saved by a review cycle, not by the methodology. That's what the new memory rules are meant to institutionalize going forward. Saved as `feedback_research_methodology.md` in memory for future sessions.

---

## Probe state at ~15:00 UTC (≈27 min in)

- 986 crypto markets discovered, 108k snapshots collected, 48 clean resolutions, 0 unresolved.
- On pace for ~1000+ clean resolutions over 24h. That's an order of magnitude more than the 50-resolution threshold in the report rubric.
- Expected outcome: the probe will deliver a **"strong signal, proceed"** recommendation by any reasonable rubric. The binding uncertainty is now v2 design choices (Chainlink integration, pre-T analysis window), not whether the market exists.

---

## Sports / event resolution-lag arbitrage — new promising angle (~04:30 UTC 2026-04-18)

Per user-directed recon: "after any major game ends, immediately check the corresponding Polymarket market. Is the winning side YES trading at <0.99? If consistent 2-4¢ gap, you've found a strategy."

Scanned ~200 recently-closed Polymarket markets with 24h volume > $10k. **50 had a post-"snap" arbitrage window** (first trade ≥0.95 followed by more trades at 0.95-0.99 for the winning side). Median window: **11.7 min**. Notional-weighted edge: **3.4%**. Total notional in windows: **$598k** across 76 scanned.

Counter-memo hypotheses tested live on top 5 arb hits (746 trades, 411 distinct wallets):

- **H1 (pro dominance) — fails for sports, confirms for non-sports events.** Sports arb windows have diffuse flow: 411 wallets across 5 markets, 0.14-4.36% of volume in first 30s. Non-sports events (WTI oil) saw 89% in first 30s — one whale dominates instantly.
- **H2 (counterparty clustering) — clean.** Large buyers per market are different wallets each time. No dominant operator.
- **H4 (dispute risk) — initial signal near zero.** 5/5 recently-closed high-vol markets cleanly resolved. Small sample but supportive.
- **H6 (population scaling) — held.** Edge and span hold across broader samples.

**Unresolved blockers:**
- **H3 (fees)** — `maker_base_fee: 1000` in unknown units; needs $10 live test
- **H5 (latency)** — NZ to Polymarket Polygon = ~200-300ms; may put us behind pro arb bots; needs live test

Revised estimate with all methodology rules applied: **$500-5,000/month at $5-20k capital** for a NZ laptop operator. Requires H3 + H5 to pass.

Full writeup: `OPPORTUNITY_SPORTS_EVENT_LAG_ARB.md`.

## Long-tail non-crypto LP — killed

Surveyed 50 random balanced non-crypto, non-major-sports markets. Median spread **3¢** (already tightly quoted — pros ARE there). The wide-spread markets (68¢ on UFC, 62¢ on "Trump visits Washington") have **$0 24h volume** — no flow to capture. "Long tail pros skip" hypothesis fails because the long tail also skips itself. **Down-rank and stop investigating.**

## Current state and what blocks further progress

- **Probe:** still running (~5h in); delivering clean resolution data. Will hit 24h mark around 14:21 UTC 2026-04-19.
- **Week watcher:** written (`experiments/e8_week_watcher/`), sandbox declined the 168h background spawn, user must launch manually:
  ```
  cd ~/dev/event-impact-mvp
  nohup uv run python experiments/e8_week_watcher/watcher.py --hours 168 > experiments/e8_week_watcher/watcher.log 2>&1 & disown
  ```
- **Sports arb execution build:** requires **H3 + H5 live tests** before any code commit. Both are $5-10 experiments on user's funded Polymarket wallet.
- **Barrier markets as vol-event plays:** pending probe-tracked resolutions over the next 1-12h.

---

## Live Arb Scan (e9) — 2026-04-18 ~05:40 UTC

Major update to the barrier-arb picture. My earlier scan used `last > 0.98` as the "certainty" threshold and returned zero executable arbs. Switching to `last > 0.95` (or `< 0.05`) reveals the arb **does exist right now**.

**Live findings at scan time:**
- 4 crypto barrier arbs, **$18,280 capturable at ask < 0.99**
- 2 sports arbs, $1,098 capturable
- 4 weather/event arbs from broader non-crypto scan

**Top opportunity:** `bitcoin-above-76k-on-april-18` — YES ask at 0.968, **$10,864 capturable** in ~10h to expiry. BTC currently $77,144, crash risk for NO outcome ~1.5%. Net EV per share ~1% before fees.

**Dynamics measured over 3 min:** ~$6,000 of arb asks got taken in 2 min, new asks refilled to baseline. Active churn, not stale.

**Implications:**
- Barrier arbs ARE accessible at laptop speed — they persist for minutes at a time
- Competition exists (someone takes ~$6k every 2 min on a single market) but doesn't fully drain the book
- The 95-99% certainty zone is the sweet spot (not the 99%+ zone where book is empty)
- Cross-category scale: 4 crypto + 2 sports + 4 other = ~$20k capturable simultaneously across ~10 markets

**Revised estimate applying methodology rules:**
- Gross potential (if we won every ask): ~$20k visible at any moment × multiple cycles per day
- Realistic capture rate: 2-10% (fighting with existing bots)
- ÷5 safety rule: additional discount
- Fees + latency: additional friction
- **Net realistic: $5-30k/month at $10-20k capital** — higher than earlier "dead barrier arb" claim because I'd been using wrong threshold

**Still unresolved:**
- H3 (fee structure) — $10 live trade needed
- H5 (latency from NZ) — timing test needed
- Competition density — the recurring scan script will measure this over 24h+

Full details + recurring scan: `experiments/e9_live_arb_scan/`

---

## Geopolitical informed-trading probe (e10) — 2026-04-18 ~08:00 UTC

New experiment opened after a question on whether the project could "latch onto" an insider-trading angle following a Reddit thread on a Polymarket Iran/US war market. Scope deliberately narrowed to **one thing**: does flag-rate on geopolitical markets exceed flag-rate on low-news control markets, at a rate a manual reviewer can defend? Not a leak detector; an instrument-calibration study that gates whether wallet-level forensics (e11) is worth building.

**Core design:**
- Sample 29 hand-curated markets (18 geopolitical: Iran regime/ceasefire/nuclear/military, Israel-Lebanon, Russia-Ukraine, China-Taiwan, UK politics + 11 controls: Eurovision, Oprah/Kim Kardashian 2028, tennis, World Cup, aliens). 60s cadence via `probe.api.PolymarketAPI.get_markets_bulk`. Single HTTP request per minute.
- 8 RSS feeds (verified live 2026-04-18). Staggered 45–120s per-feed poll. Dropped Reuters/AP/Haaretz/Kyiv Independent — all dead endpoints.
- News→market match when a market's keywords appear ≥2× in a feed item's title+summary.
- Detection (offline, `analyze.py`): z-score of 10-min Δprice vs clean baseline (non-news-matched windows). Filter: `z ≥ 3` AND `volume_delta ≥ $500` AND theme-relevant feeds healthy at event start AND not in first-30min / final-60min of market lifetime. Co-movement filter records same-theme markets with z ≥ 1 in the same window.

**Design calibrations worth preserving** (before any data was collected):

1. **REPORT.md headline = control-vs-candidate flag-rate ratio.** Computed per 1k market-hours. Ratio ≤ 1.0× = clean null regardless of how compelling individual events look.
2. **Feed health is theme-aware.** Each feed has `themes: [...]` in `feeds.yaml`. BBC silent during a Middle East market move = disqualifying; SCMP silent during same move = irrelevant.
3. **Pre-committed manual review rubric** in `MANUAL_REVIEW_RUBRIC.md`. Six trivial explanations must be explicitly ruled out before `unexplained-by-monitored-feeds` verdict is admissible. Blunts fatigue-bias.
4. **Framing rule compiled into code, not judgment-called at report time.** Ratio→verdict table. Phrases *suspicious*, *consistent with informed trading*, *insider-like*, *leak* never emitted. Strongest allowed phrasing: `unexplained by our monitored feed set`.

**Gamma-api quirk discovered during verification:** `tag=`, `category=`, `tag_id=` filter params on `/markets` are silently ignored (byte-identical responses regardless of value). Committed to slug-substring discovery + manual curation. Memory saved at `.claude/projects/.../memory/gamma_api_filter_quirk.md`.

**Outstanding design question:** should Trump's Truth Social be tied into the feed set? Several tracked markets are literally `trump-announces-*` markets; his post *is* the news event. Rejected for v1 because adding feeds mid-run corrupts the control comparison. Deferred to e10 v2 if the v1 verdict is ambiguous or the `unmonitored-source-broke-first` disqualifier eats most candidates.

**Run state as of entry:** launched 08:04 UTC, 48h run. ~20min in: 551 snapshots, 345 real news→market matches, 8/8 feeds alive, 165 new discovery candidates logged. One concern: kyiv-post feed stale (~5h since last publish) — if persistent, russia-ukraine events may hit the 3h hard-exclusion and drop out.

**Decision gate** (pre-committed in `README.md`): ≥3 events passing all of {news_lead ≥15min, volume_delta ≥$500, z ≥3, isolated nearby_markets, theme-relevant feeds healthy, manual verdict = `unexplained-by-monitored-feeds` after ruling out all 6 disqualifiers} AND candidate/control flag-rate ratio ≥3× → proceed to e11 wallet forensics. Otherwise kill the direction.

Full narrative: `experiments/e10_geo_informed_trading/DESIGN_LOG.md`.

---

## Session 2026-04-19 — two theses falsified, master plan revenue number unsupported

Two empirical results from today, both negative, both invalidate pieces of earlier writeups. Full write-ups linked.

### 1. Polymarket barrier tail-scalp — falsified via Impressive-Steak counterfactual

Context: `experiments/e9_wallet_competitor_intel/` identified `Respectful-Clan` (0x6e1d5040…) as an apparently-successful bot running a mechanical tail-insurance strategy: buy barrier/ladder NO at 0.90-0.99, let expire, collect pennies. `DEEP_DIVE.md` proposed backtesting + shadow-copying. The master-plan / `FINDINGS.md:272` revenue estimate of `$5-30k/month at $10-20k capital` rested on this edge being real.

User proposed the right test: if the rule is real, it should fire on Respectful-Clan's winners and filter out `Impressive-Steak`'s losers (same strategy shape, −$82k realized). Per-position test using `avgPrice` buckets from `/positions` output showed:

- Both wallets earn **identical +1.5% cashPnl ROI** on the `avgPrice ≥ 0.95` bucket.
- Both wallets realize **negative P&L** on closed positions in that bucket (−$71k Impressive-Steak, −$38k Respectful-Clan).
- All of Respectful-Clan's alpha is in two mid-band directional bets (avgPrice 0.30-0.70, +40.8% ROI on $525k gross) — macro calls on BTC, not a replicable rule.

**Implication: the `$5-30k/month` revenue number in `FINDINGS.md:272` is unsupported by the wallet-level evidence.** The rule the number was based on is empirically a coin-flip once fees are netted.

Full write-up: `experiments/e9_wallet_competitor_intel/COUNTERFACTUAL.md`.

### 2. Funding-rate arbitrage — falsified via live funding-rate pull

Context: after the tail-scalp fell over, I pitched funding-rate arb as a lower-drama alternative, citing "10-30% APY on BTC historically" and "$1-10k/year at $10-50k capital." User asked for a sense-check.

Pulled current rates + 90-day history via `ccxt`:

- **Current BTC perp funding: −9.1% annualized** (shorts pay longs). ETH −16.1%. SOL −8.1%. Classic long-spot / short-perp carry currently *costs* money.
- **90-day BTC mean: −0.02% APY.** Median +0.30%. 53% of periods positive (coin flip). p90 is +6.2% which nets ~4% after fees.
- **90-day ETH mean: −1.23% APY.** 48.5% of periods positive.
- Binance round-trip fees: 0.25% across both legs. At median BTC rate you never break even. At p90 you need to hold 15+ days to cover fees.

The "10-30% APY" number came from 2020-2023 bull-market recall, not data. In the current flat regime the strategy is below fee threshold. This is the second time in the same thread where I pitched a number without running the sense-check first; both times the user had to prompt for it.

Full write-up: `experiments/e11_funding_arb_sensecheck/README.md`. Reproducible script: `probe.py` in the same directory.

### Consolidated null-result memo

`docs/NULL_RESULTS.md` is new. Single place that lists every thesis this project has definitively ruled out with the disproving evidence. Entries: mechanical tail-scalp (this session), funding-rate arb (this session), above-K hourly ladder MM (2026-04-18), long-tail non-crypto LP (2026-04-18), the inverted signal-quality metric (a priori flag).

Survives so far section: sports settlement-lag arb, pending H3+H5 live tests at $5-10 cost. That's the thinnest list the project has had.

### Meta-pattern flagged

Both falsifications followed the same shape: confident number → user requests sense-check → data pull produces negative result → prior writeup gets invalidated. The pattern is documented in the bottom of `NULL_RESULTS.md`. Operational rule going forward: any pitch with a revenue number gets a data-pull sense-check *before* being written up, not after.

