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

---

## Session 2026-04-19 — paper-trade plan + external audits

Project re-opened to design a paper-trade harness for the surviving theses. What started as "wire up pm-trader and start polling" turned into a four-front audit that materially reshaped the plan. All findings below are concrete numbers pulled in this session, not carried forward from earlier sessions.

### External-repo sweep (evaluated for integration into e12)

**Integrated:**
- [`agent-next/polymarket-paper-trader`](https://github.com/agent-next/polymarket-paper-trader) (253⭐, PyPI) — book-walking fills, exact Polymarket fee formula, multi-account. Execution layer for e12.
- `polymarket-apis` (PyPI, v0.5.7) — typed Pydantic Gamma/CLOB client. Drop-in for hand-rolled aiohttp.
- Sports-result feeds: [`pseudo-r/Public-ESPN-API`](https://github.com/pseudo-r/Public-ESPN-API) (454⭐), [`swar/nba_api`](https://github.com/swar/nba_api) (3.5k⭐), [`toddrob99/MLB-StatsAPI`](https://github.com/toddrob99/MLB-StatsAPI) (783⭐).
- `httpx + PyrateLimiter` for async rate-limit.

**Independent confirmations of kills:**
- [`warproxxx/poly-maker`](https://github.com/warproxxx/poly-maker) (1k⭐) — author: "not profitable in today's market, will lose money." Re-confirms the hourly-ladder MM kill (e11).
- `@defiance_cr` open-sourced and shut down his MM bot for the same reason.

**Deferred / parked:**
- [`Jon-Becker/prediction-market-analysis`](https://github.com/Jon-Becker/prediction-market-analysis) (3k⭐) — 36 GiB historical parquet. Fallback dataset if SII fails.
- [`warproxxx/poly_data`](https://github.com/warproxxx/poly_data) (1.3k⭐) — Goldsky subgraph for v2 hot-market flagging.
- [`sstklen/trump-code`](https://github.com/sstklen/trump-code) (735⭐) — Polymarket↔Kalshi cross-platform arb. Separate future plan.
- [`evan-kolberg/prediction-market-backtesting`](https://github.com/evan-kolberg/prediction-market-backtesting) (628⭐) — originally Phase 0 fee cross-check; obsoleted by SII on-chain fee truth.

### Polymarket protocol docs sweep (direct from docs.polymarket.com)

Several assumptions treated as empirical unknowns are actually documented:

- **Fee formula:** `fee = shares × feeRate × p × (1−p)`. Peaks at p=0.5. Prior plan had `min(p, 1−p)` — a 2× shape error.
- **Per-category published rates:** Crypto 7.2 bps, Sports 3 bps, Finance/Politics/Tech 4 bps. See e13 SII finding below — empirical on-chain is zero.
- **Rate limits:** Gamma general 4000/10s, `/markets` 300/10s. Prior plan's 5/s guess was 60× conservative.
- **CLOB priority:** price-time (not pro-rata). Tick sizes 0.1/0.01/0.001/0.0001 per-market.
- **UMA resolution:** 2h liveness, $750 pUSD bond per side. Auto-proposer posts within minutes → ~2–2.5h total settlement undisputed.
- **🚨 V2 cutover: 2026-04-22** — CTF Exchange V2 + CLOB V2 with no V1 backward compat. Paper trading mostly insulated (not on-chain), but gamma shapes and fees may drift. e12 plan pauses/verifies/resumes.
- **Cancel-before-match latency:** NOT publicly documented. Remains empirical unknown.

Saved to memory at `~/.claude/projects/.../polymarket_protocol_facts.md`.

### Academic literature sweep

- **Della Vedova 2026** (SSRN 6191618, "Execution, not Information") — EXACT thesis match. 222M trades. Bots pay 2.52¢ less per contract than casual traders. Execution skill drives PnL, not prediction. No paper has isolated the specific post-resolution sports window — e12 fills that gap.
- **Becker 2026** "Microstructure of Wealth Transfer" — Sports has one of the smallest maker-taker gaps (2.23pp). Closer to efficient than entertainment/world-events.
- **Akey, Grégoire, Harvie, Martineau 2026** (SSRN 6443103) — Top 1% = 84% of gains. Market-making is the only strategy class with predicted positive returns. Yellow flag for sports_lag (taker strategy).
- **Saguillo et al. 2508.03474** — Arb opportunity duration collapsed **12.3s (2024) → 2.7s (2025)**. 73% of arb profits captured by sub-100ms bots. Our 14.4 min sports_lag window is 300× longer — currently insulated, compression trend to watch.

### UMA disputes + operator wallets

- Platform dispute rate ~2% (217 / 11,093 settled markets, UMA blog). Sports inferred **<0.5%** post-MOOV2.
- Known sports-arb operator: `LlamaEnjoyer` (0x9b97…e12) — demonstrably trades UFC post-event ($67k gain in the UFC Fortune/Tybura blunder case).
- Top-3 arb wallets across all categories: $4.2M over 12 months on 10,200 bets.
- Retail is the seller side at 0.95–0.99 post-resolution — behavioral, persistent counterparty (QuantVPS blog confirms "retail impatient exits at 0.997–0.999").

### e13 external-repo audit — concrete numbers from SII-WANGZJ/Polymarket_data

Parallel investigation against 954M on-chain rows (19-day fresh). Full report at `experiments/e13_external_repo_audit/findings.md`.

**Investigation 1b — realized fees (n=143 sports post-resolution trades):**
- taker_fee_bps median / p95: **0.0 / 0.0**
- maker_fee_bps median / p95: **0.0 / 0.0**
- Zero across all price bands (0.95–0.99)
- **Interpretation:** H3 fee gate empirically resolved. Takers pay zero on-chain for sports post-resolution trades in the SII sample. Published docs rates (Sports 3 bps) may be ceiling / legacy / per-market-override capable. Phase 0b shakedown verifies pm-trader agrees on live sports buys.
- **Caveat:** n=143. Fees may differ for non-sports, large notional, or post-dataset-cutoff.

**Investigation 1c — sports_lag historical edge (n=47 entries):**
- Gross edge: **+3.99% notional-weighted**
- Net edge at 100 bps: +3.95%; 300 bps: +3.87%; realized 0 bps: **+3.99%**
- Avg hold: 14.4 min (matches the OPPORTUNITY doc's 11.7 min median claim)
- Thesis directionally confirmed. Robust to any fee assumption 0–300 bps.
- **Caveat:** n=47 plateaued at row group 41/76. Deeper rerun with `MAX_TRADE_ROW_GROUPS=300` queued in e13.

**Investigation 1d — crypto_barrier historical edge (n=5,220 entries):**
- Hit rate: 62.66%. **Crash rate: 37.34%**
- Gross edge (notional-weighted): **−63.44%**
- Net at 100 bps: −63.47%; 300 bps: −63.53%. Notional: $890k
- **Killed.** Fees are noise vs crash losses. The ~1% net EV estimate in `e9_live_arb_scan/README.md` was wildly optimistic. Added to NULL_RESULTS.md.
- Possible salvage: tighter spot-distance filter (≥5% from strike) — needs external BTC/ETH minute-bar overlay, separate investigation.

**Investigation 1e — H1 wallet-diversity re-derivation (n=121 wallets, 41 markets):**
- Top-10 wallet share: **68.19%** (vs original H1's "411 wallets, flow-diffuse")
- Gini 0.83. **Verdict: H1 FALSE at this sample size.**
- **Caveat:** n=336 rows is 3 wallets/market vs H1's 82 wallets/market. Deeper rerun needed. If confirmed, realistic capture rescales 3–5× down; doesn't kill strategy.

**Investigation 2 — Octagon risk-gate patterns:**
- Recommended: `MAX_DRAWDOWN_PER_CELL = 0.20`, `MAX_OPEN_PER_EVENT = 3`. Integrated into e12.
- Skipped: half-Kelly, daily loss limit, JSON envelope, Kalshi cross-venue.

**Investigation 3 — `polymarket-apis` (PyPI v0.5.7):**
- `PolymarketGammaClient.get_markets()` works (10 typed markets in 0.41s). Integrated.
- `PolymarketReadOnlyClobClient.get_market()` reachable but returned 0 tokens on sampled market — retest queued in e12 slug_audit.

### Net effect on e12 plan

The findings converged on a much tighter scope:

- **Dropped:** crypto_barrier entirely. FEE_BPS=100 placeholder. Nautilus Phase 0 cross-check.
- **Added:** FEE_BPS=0 default + Phase 0b zero-fee assertion. Octagon risk gates (drawdown, event concentration). V2 cutover pause/verify/resume on 2026-04-22. `polymarket-apis` gamma client. Poll cadence revised 20s → 2s.
- **Preserved:** sports-result feeds + book-poll dual-path detection, two size models, sample-size-driven termination, time-weighted return reporting, pm-trader as execution layer.

Full revised plan at `docs/PLAN_E12_PAPER_TRADE.md`.

### Open questions queued for future passes

1. Sports_lag sample plateau — rerun e13's `03_sii_sports_lag_backtest.py` with higher row-group cap.
2. H1 wallet-diversity at scale — rerun e13's `05_sii_wallet_diversity.py` with `MAX_USER_ROW_GROUPS=400+` and looser filters.
3. crypto_barrier salvage — overlay Binance minute bars; recompute crash rate by spot-distance bucket.
4. CLOB token retrieval — verify `PolymarketReadOnlyClobClient.get_market` returns populated tokens on active sports markets.
5. Fee-structure recency — Phase 0b shakedown assertion is the continuous check as V2 cutover approaches.
6. Cancel-before-match latency — undocumented; would need on-chain observe-only probe.

---

## Geopolitical informed-trading probe (e10) — stopped early 2026-04-19 02:52 UTC

48h run halted at **6.79h of snapshot span** after the 6h analysis gate revealed two calibration bugs that would have poisoned any 48h verdict. Headline: **null result at 1.12× candidate/control ratio** — framing rule triggered correctly, control comparison blocked a tempting false positive on the Iran-ceasefire cluster.

**What worked:**
- Pre-committed ratio→verdict table prevented narrative creep: 3 Iran-ceasefire markets moved in lockstep with $9–13k volume deltas at 20:40 UTC; reviewer-brain would have circled these as suspicious. Report correctly labeled them theme co-movement (`nearby=2`) and the overall ratio verdict as null.
- Control markets flagged at 80.90/kmh vs candidate 90.64/kmh — near-parity is the entire reason the ratio is honest.
- Infrastructure clean: 10,266 snapshots on exact 60s cadence, 404 news items from 8 feeds, 627 news-market match rows, 165+ discovery candidates logged without auto-add.

**What broke:**
- **`low_confidence` threshold** (60min feed silence) too tight for feeds that naturally publish every 10–20 min. 17/17 events flagged ⚠️. The mark became meaningless. Post-mortem fix: use `feed_health` polling-silence rather than publishing-silence, or move threshold to 120–180min.
- **Baseline σ estimator** unstable at 6.79h — illiquid markets produced z=6+ on Δprice=±0.003. Ratio stayed honest (noise is symmetric across candidate/control) but absolute flag count is overstated. Post-mortem fix: require ≥24h span before running detection, or shrinkage toward cross-market prior.
- **Kyiv-post feed dead at launch and stayed dead** (last pub 5h before launch, 12h before stop). Russia-Ukraine theme hard-excluded the entire run — zero coverage on that theme.

**Interesting observation, not a signal:** `will-the-us-confirm-that-aliens-exist-before-2027` flagged twice with 0 matching news items across all 8 feeds. It's a control market, z=4.42 on ±0.010, and one event had $102k single-order volume — almost certainly a whale bet, not informed flow. Noted as the profile the detector was built to find; if it can't distinguish this from a real leak, it isn't a leak detector.

**Decision gate: not met.** Ratio 1.12× is nowhere near the 3× threshold. **E11 (wallet-level forensics) is NOT unlocked.** Kill the direction as currently scoped. If revisited: needs threshold fixes + baseline ≥24h + Truth Social feed (via `trumpstruth.org` mirror) because several tracked markets are literally Trump-announcement markets where his post *is* the news event.

**Consolation prize:** 10k snapshots + 627 matched news rows are a usable dataset for a different, weaker question — "does news volume on a market's keywords predict next-hour volatility?" — if the feed infra is worth recycling.

Full retrospective: `experiments/e10_geo_informed_trading/FINDINGS.md`.

