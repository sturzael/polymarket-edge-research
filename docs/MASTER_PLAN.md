# Master Plan — Polymarket Resolution-Lag Arbitrage

Last updated: 2026-04-19. This replaces and consolidates `OPPORTUNITY_HOURLY_LADDER_MM.md` (dead), `OPPORTUNITY_SPORTS_EVENT_LAG_ARB.md` (alive but deferred), and the ad-hoc opportunity writeups in FINDINGS.md.

## Executive summary

**The edge we're taking:** buy cheaply-mispriced winning-side tokens on Polymarket binary markets where the outcome is economically determined but hasn't yet formally resolved via UMA. Hold to resolution, collect $1 per share.

**The evidence:** three independent lines converge on the same opportunity shape:
1. `Respectful-Clan` (`0x6e1d5040…`) runs this strategy live at ~$1.65M book with **+$99k realized in 38h**. Validated via e9 wallet competitor intel.
2. Our own e9 live-arb scan detected **$18,280 of simultaneous capturable depth** at `ask < 0.99` across 4 crypto barrier markets right now.
3. The 16.91-hour probe confirmed the market infrastructure — 1,316 clean resolutions with 388s median lag, 841 markets with deep final-15s trade data.

**Realistic monthly income** at $10-20k at-risk capital, after methodology rules applied AND accounting for regime-dependence uncertainty: **$0-15k/month with wide confidence interval**. The lower bound is honest-to-zero (regime-conditional strategy eats inverse loss in unfavorable regime); the upper bound assumes the rule holds across regimes, which is currently unvalidated.

**⚠️ CRITICAL UNRESOLVED QUESTION:** The primary evidence (Respectful-Clan's +$99k/38h and our probe's 1316 resolutions) all came from a BTC DOWN regime. A "buy NO on reach-upside barriers" strategy looks like free money when BTC is trending down. When regime flips, the same strategy eats the inverse loss. **This must be empirically resolved before any capital is deployed.**

**Critical path to deployment:** 4 steps. Total ~5-10 days of work + 2 user-led $10 live tests.

---

## The full opportunity landscape (ranked)

| # | Strategy | Accessibility (laptop / NZ-VPS / US-East-VPS) | Status | Primary evidence |
|---|---|---|---|---|
| **1** | **Tail-insurance barrier arb** | ✅ / ✅ / ✅ | **PRIMARY — build this** | Respectful-Clan +$99k/38h; e9 live scan $18k available |
| 2 | Sports resolution-lag arb | ⚠️ / ✅ / ✅ | Deferred, secondary | 50 arb hits, $598k/day, 411 distinct wallets (diffuse) |
| 3 | 4h barrier markets | Unknown / likely ✅ | Unknown — needs recon | 16.4% of probe universe, unanalyzed |
| 4 | Hourly ladder MM | ❌ / ❌ / ❌ | Dead | Recon A showed 2-3¢ spread already held by pro MM with 30s reaction |
| 5 | 5m updown HFT arb | ❌ / ❌ / ⚠️ | Dead on laptop, marginal on US-East VPS | 85% of flow captured in first 60s |
| 6 | Long-tail non-crypto LP | ❌ / ❌ / ❌ | Dead | Median spread 3¢; wide-spread markets have $0 flow |
| 7 | UMA dispute arb | ⚠️ | Deferred | 0/1000 disputes in sample; extremely rare |

The plan centers on **#1 with #2 as the follow-on diversifier**. Everything else is either dead or deferred.

---

## Primary strategy: Tail-insurance barrier arb

### Mechanism in one paragraph

Polymarket lists barrier-style markets like `will-bitcoin-reach-90k-in-april`. When current spot is mechanically far from the strike and expiry is close, the `NO` outcome is near-certain. Despite that, the winning side often has `ask` orders resting at 0.90-0.98 (not 0.99+) — placed by retail liquidating positions, hedged positions being closed out, or similar. Buy at those asks, hold ~hours to days until UMA resolves the market, collect $1 per share.

### The rule (reverse-engineered from Respectful-Clan + our own e9 scan)

**Entry conditions (all must hold):**
- Market type: `barrier_reach` or `barrier_dip` (crypto specifically)
- Current spot is **≥15% away from strike** in the NO-favoring direction
- Time to expiry is **≥30 minutes** (too close = UMA resolution may already be staged)
- Winning side's `best_ask` is **≥0.90 and <0.99**
- Ignore markets with `lastTradePrice` in [0.05, 0.95] (outcome still uncertain; this is not tail-insurance territory)

**Order placement:**
- **Take liquidity** — buy at best_ask, up to a pre-configured share count per market
- Max $X per market (position-sizing; prevents concentration)
- Max $Y total concurrent exposure across all markets

**Exit:** no exit logic — hold to UMA resolution. Collect $1 per share if winning side wins, $0 if it flips.

**What we will NOT copy from Respectful-Clan:**
- The $321k directional YES position on "BTC reach $80k" — that's a separate directional bet, not tail-insurance. Out of scope.
- Ladder (`above`/`below` strike ladder) and range (`-between-`) bets at median price 0.74-0.76 — those are spread trading with different risk profiles. Out of scope for v1.
- Buying NO at <0.80 on contrarian bets — that's directional conviction, not mechanical edge. Out of scope.

### Sizing

Respectful-Clan: $1.65M book, 304 concurrent positions → ~$5,400 per position, $41k max.

Our v1 sizing at $10k total capital:
- Max per position: **$100** (100 shares @ $1)
- Max concurrent: **$5,000** (50 positions)
- Discovery cadence: scan every 30 seconds for new qualifying markets

### Expected returns

Three methods converge:

| Method | Estimate |
|---|---|
| Scale Respectful-Clan's $99k/38h to 12% capital × ÷5 rule | $45k/month |
| e9 live-scan: $18k capturable × 4 cycles/hour × 5% capture × 30d | $260k/month gross × frictions |
| Counter-memo frictions (competition, fees, edge decay, capital inefficiency) | 50-70% haircut |
| **Net realistic** | **$5-30k/month** |

Fat tail to **$0** if:
- Fees turn out to be 1%+ (kills the edge)
- Edge decays and the competitor bots retreat (like Pigsty/Archaeologist did with 5m updown in March)
- Polymarket regulatory action limits access
- A single unexpected crash event takes a big loss on held positions

---

## Infrastructure (what the system needs to be)

### Target deployment

- **Provider:** DigitalOcean or AWS, **us-east-1 region (Virginia)**
- **Spec:** 2 vCPU / 4 GB RAM / 50 GB SSD / 1 Gbps. ~$20-30/mo.
- **Why US-East:** Polymarket infrastructure is US-based, Polygon validators cluster US-East. RTT to Polymarket CLOB: 5-15ms. RTT to Binance/Coinbase spot: 20-50ms. Good enough for every opportunity except 5m updown HFT (which we're not targeting).

### Service architecture

```
┌─────────────────────────────────────────────────────────┐
│                         VPS                             │
│                                                         │
│  ┌─────────────┐   ┌─────────────┐   ┌──────────────┐   │
│  │  Discovery  │──▶│   Signal    │──▶│ Order Placer │   │
│  │  (gamma-    │   │  (rule eval,│   │   (CLOB      │   │
│  │   api poll) │   │   spot data)│   │    signed)   │   │
│  └─────────────┘   └─────────────┘   └──────────────┘   │
│         │                                    │          │
│         ▼                                    ▼          │
│  ┌─────────────┐                    ┌────────────────┐  │
│  │   SQLite:   │◀───────────────────│ Position       │  │
│  │  markets,   │                    │ Tracker        │  │
│  │  fills,     │                    │ (mark-to-mkt)  │  │
│  │  resolutions│                    └────────────────┘  │
│  └─────────────┘                            │           │
│         │                                   │           │
│         └────────────┬──────────────────────┘           │
│                      ▼                                  │
│               ┌─────────────┐                           │
│               │  Resolution │                           │
│               │  Watcher    │                           │
│               │  (CLOB poll)│                           │
│               └─────────────┘                           │
└─────────────────────────────────────────────────────────┘
              │
              │ (logs + alerts)
              ▼
        Telegram / email
```

### Components

1. **`discovery.py`** — polls `gamma-api.polymarket.com/markets?closed=false&active=true` every 30s. Filters for barrier markets in scope. Updates `markets` table.
2. **`signal.py`** — on each discovery cycle, for each in-scope market: pulls CLOB `/book` on winning side, checks spot distance from strike, evaluates entry rule. Generates `buy_intent` events.
3. **`spot.py`** — websocket client to Binance + Coinbase for BTC/ETH/SOL/BNB/XRP/DOGE. Keeps latest in memory for signal evaluation.
4. **`order_placer.py`** — takes `buy_intent` events, constructs a CLOB signed order, submits, logs outcome. Respects per-market and concurrent-exposure caps.
5. **`position_tracker.py`** — maintains open-position set from order fills. Marks to market from CLOB book data.
6. **`resolution_watcher.py`** — on each market's post-end_ts window, polls CLOB `/markets/<cid>` for `tokens[].winner`. On resolution, records realized P&L; redemption happens via CLOB's settlement function.
7. **`safety.py`** — hard stops: max total exposure, daily loss limit, emergency kill switch (file-flag `stop_now` in project root halts all new orders).
8. **`alerts.py`** — Telegram/email push when: fills occur, resolution lands, daily P&L threshold crossed, emergency stop triggered.

### Dependencies

- `py-clob-client` (Polymarket's official Python CLOB client) or a lightweight in-house signer
- `ccxt` or raw websocket for spot data
- `web3.py` for Polygon interactions (order signing uses EIP-712)
- `aiosqlite`, `aiohttp`, `pyyaml`, `pandas`
- Polymarket requires a funded Polygon wallet with USDC

### Polymarket account setup (user-led)

1. Create Polymarket account, go through verification
2. Fund with USDC on Polygon (bridge from another chain if needed)
3. Approve USDC for the CTF (Conditional Token Framework) exchange contract
4. Generate API keys for the CLOB client
5. Store signing key securely (HashiCorp Vault / SOPS / encrypted .env; never in repo)

---

## Build phases + kill criteria

Each phase is a decision gate. If kill criteria hit, stop and reassess — do not proceed.

### Phase 0a RESULTS (partial, 2026-04-19)

**First pass on 184 historical resolved barrier markets:**
- 97% NO wins, 3% YES wins (looks like structural edge)
- **All 6 YES wins are from April 2026** (concentrated in recent near-strike conditions)
- Zero YES wins in Dec 2025 or March 2026 samples
- But sample is heavily concentrated in Mar-Apr (175/184), so we don't have real regime diversity

**Critical open question (blocking capital deployment):** does the 15% spot-distance rule filter out the 6 YES-winners? If yes, the rule may be regime-resilient. If no, the strategy is regime-dependent and the ÷5 number is optimistic.

**Outstanding work to complete Phase 0a:**
1. Fetch BTC/ETH/SOL spot price at each of 184 market creation timestamps (Binance OHLCV historical, free)
2. Compute distance-from-strike at creation; apply the 15% rule
3. Stratified stress test: shift historical prices +15% and +20%, re-run rule, measure hypothetical UP-regime loss rate
4. Expand historical sample to 400+ markets covering Jun 2025 - Apr 2026 (need to pull additional cids; Respectful-Clan's history only reaches back to mid-2025)

### Phase 0a: Regime-stratified historical backtest (CLAUDE, 1-2 days, free)

**This gates everything downstream.** Added after LM critique flagged that our evidence comes from a single market regime (BTC trending DOWN).

**Purpose:** determine whether the entry rule is a true mechanical edge or a trend-conditional bet wearing arb costume.

**Method:**
1. Enumerate historical barrier markets going back 30+ days by harvesting condition_ids from `experiments/e9_wallet_competitor_intel/data/barrier_trades.jsonl` (4,946 trades) and from CLOB pagination where possible.
2. For each historical market, pull:
   - Resolution outcome (via CLOB `tokens[].winner`)
   - Trade history (via data-api)
   - BTC/ETH/SOL spot price series for the market's lifetime (via Binance OHLCV REST)
3. Classify each market's *regime* by the underlying's trailing-24h log return at market-creation time:
   - **UP regime**: underlying +1% or more in prior 24h
   - **DOWN regime**: underlying −1% or more
   - **FLAT regime**: within ±1%
4. Simulate the entry rule: for each hypothetical fill opportunity within each market, assume purchase at the ask, redeem at resolution, compute P&L.
5. Report:
   - Win rate per regime
   - Net P&L per regime (after a 0.5% round-trip fee assumption)
   - Sharpe per regime
   - Number of "toxic fills" (markets where the NO outcome flipped to YES) per regime

**Kill criteria:**
- Win rate in the *unfavorable* regime < 90% → **kill as an arb; treat as trend-conditional at best**
- Net P&L in any regime < 0% after fees → **kill**
- Overall sample size per regime < 50 markets → **extend data collection; don't decide yet**

**Success criteria:**
- Win rate ≥ 92% in BOTH UP and DOWN regimes
- Net P&L positive in both regimes after 0.5% round-trip fees
- Sample size ≥ 100 per regime

**If Phase 0a only clears in one direction:** the strategy is a trend-conditional bet, not an arbitrage. In that case we'd:
- Size much more conservatively (max $50/position, max $500 total)
- Only trade when spot-direction matches the favorable regime
- Treat expected P&L as 30-50% of the favorable-regime backtest
- Write this honestly in the revised plan before any live deployment

### Phase 0b: Extended wallet shadowing (CLAUDE, 2-3 weeks passive)

**Purpose:** verify that Respectful-Clan's strategy actually survives the regime change the market is guaranteed to have over 2-3 weeks.

**Method:**
1. Add wallet `0x6e1d5040d0ac73709b0621f620d2a60b80d2d0fa` to a monitoring probe
2. Pull `/positions` and trade history every 4 hours
3. Log: open position count, realized P&L, unrealized P&L, biggest winning/losing positions
4. Track BTC/ETH/SOL daily returns alongside to identify regime shifts

**Kill criteria:**
- Over any 5-day window, realized P&L goes negative for any 2 consecutive days during a regime opposite to the one we observed
- Open position count drops by >50% (suggesting they've stopped trusting their own strategy)
- Drawdown exceeds 30% of prior cumulative P&L

**Success criteria:**
- Realized P&L continues to grow across ≥2 distinct regime shifts
- Strategy maintains similar trade cadence (40-60 trades/hr) throughout

**This runs in parallel with everything else. No capital at risk; only information cost (time).**

### Phase 0c: Live tests (USER, 30 min, $10-20 at risk)

Only run AFTER Phase 0a passes. Unchanged from prior version except for the ordering dependency.

**Purpose:** settle the two biggest unknowns before any code commit.

**Tasks:**
1. **Fee test.** Place one $5 buy limit at 0.968 on `bitcoin-above-76k-on-april-18` (or next-equivalent market). Watch it fill. Record the exact USDC decrement vs the 0.968 × shares expected payment. Delta = fee.
2. **Latency test.** From your VPS (set up first), place a $1 limit on any market. Log order-submission time + order-accepted time. RTT.

**Kill criteria:**
- Fee > 1% per side (2%+ round-trip) → **kill**. Edge doesn't survive.
- Latency > 1 second from VPS → **kill**. Suggests infrastructure problem.

**Success criteria:**
- Fee ≤ 0.5% per side, latency ≤ 200ms.

### Phase 1: Rule-implementation backtest (~1-2 days, free)

Only run after Phase 0a clears AND Phase 0b shows ≥1 week of continued Respectful-Clan success across a regime shift.

**Purpose:** verify the entry rule works against known data before live-trading it.

**Data source:** `probe/probe.db` — has 1,316 resolved crypto markets + 791k snapshots from 2026-04-18/19.

**Implementation:**
1. Write `experiments/e10_rule_backtest/backtest.py`:
   - For each market_snapshot in the probe DB, evaluate the entry rule with contemporaneous spot data.
   - When rule fires, simulate a $100 buy at best_ask.
   - At market's resolution, credit $100 gain or $0 (total loss).
   - Aggregate: total fills, gross capital deployed, realized P&L, win rate, per-market P&L.

2. Also evaluate the rule **ex-post** on Respectful-Clan's actual trades: what fraction of their buys would our rule have fired on?

**Kill criteria:**
- Win rate < 90% (we're buying at 0.90+ and the market has economically decided — missing 1 in 10 is fine; missing 1 in 5 is lethal)
- Gross edge (1 - avg buy price - fees) < 1% per round-trip
- Our rule overlaps with <40% of Respectful-Clan's actual buys (we're missing the thing that actually works)

**Success criteria:**
- Win rate ≥ 95%, gross edge ≥ 2%, overlap with Respectful-Clan ≥ 50%.

**Output:** Go / no-go decision on the rule.

### Phase 2: Minimum viable bot (~3-5 days)

**Purpose:** implement the core loop end-to-end at minimal scale.

**Scope:**
- Discovery + signal + order placement for **barrier markets only**
- **Hard cap $1,000 total capital** for v1 (regardless of what config.yaml would allow). Fail small.
- Max $50 per market, max 20 concurrent positions.
- Alerting on Telegram: every fill, every resolution, hourly P&L.

**What's explicitly out of scope for Phase 2:**
- Sports markets
- Ladder and range markets
- 4h markets (revisit after rec completes)
- Websockets for sub-second latency
- Multi-venue integration
- Advanced inventory / risk rebalancing

**Test plan before going live:**
- Run in **paper mode** for 48h on VPS against live market data: same loop, but `order_placer.py` writes to `paper_orders` table instead of submitting to CLOB
- Compare paper P&L to e9 live-scan expected (should be in the ballpark)
- If paper looks right: enable live orders with $100 cap for first 24h, then ramp

**Kill criteria:**
- After 1 week of live trading at $1,000 cap: realized P&L < 50% of backtest expectation
- 2 consecutive daily losses exceeding 10% of capital (indicates adverse selection, crash event, or rule malfunction)
- Any UMA dispute that costs 100% of a position (extremely rare but catastrophic)

**Success criteria:**
- Realized P&L matches backtest within 30%, drawdown < 15%, no safety-rail incidents.

### Phase 3: Scale to $10k (~1 week of live observation)

**Purpose:** test whether the edge scales linearly with capital or decays (competition detects us, adverse selection bites).

**Process:**
- Gradually raise per-market cap from $50 → $200, total cap from $1,000 → $10,000, over ~5 trading days.
- Monitor daily returns vs. the $1,000-cap baseline: should be 10x if linear.
- If returns/capital ratio drops by >30% as size grows, stop scaling at the prior level.

### Phase 4: Diversify to sports + 4h markets (timing TBD based on Phase 3 results)

**Condition:** only after Phase 3 hits stable returns at $10k for ≥2 weeks.

**What's added:**
- **Sports resolution-lag arb** — requires game-end detector (ESPN or Sportradar feed, free public sources for major leagues). Longer window means simpler execution but needs market-matching infrastructure.
- **4h crypto markets** — 16.4% of probe universe, unanalyzed. Separate rec + potentially different rule. Similar latency regime to barriers.

**Kill criteria per sport:** same shape as Phase 2 — backtest first, paper second, small live third. Each sport is a separate gate.

---

## Research / recon tasks still open

These are cheap investigations that could inform the build but don't block it.

1. **4h market recon** (~2h) — sample 50 4h barrier markets, characterize their arb-window shape. Do they resemble 1h barriers (same strategy) or something else? Complete before Phase 4 but not before Phase 0.
2. **Weekly market recon** (~2h) — 194 weekly markets in probe universe. Probably long resolution lags, different flow. Same question as 4h.
3. **Loser analysis on Respectful-Clan** (~1h) — of their 304 open positions, which are likely to lose? Tells us the realistic loss rate we should model.
4. **Respectful-Clan rule-overlap analysis** (~2h) — for each of their 190 barrier-reach NO buys, can our rule explain the entry? If yes, our rule is their rule.
5. **Austere-Heavy comparison** (~1h) — second-best wallet running the same strategy. Do their entry conditions match Respectful-Clan? If yes, structural edge. If not, idiosyncratic.
6. **Impressive-Steak counter-study** (~1h) — what specifically makes their 0.80 entry bad vs 0.95? Teaches us the threshold we must NOT cross.

---

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Fee structure eats edge | Medium | Fatal | Phase 0 fee test |
| UMA dispute on a held position | Low per-position, medium fleet-level | Loses 1-100% of that position | Position sizing (max $100/mkt), diversification (50+ concurrent), skip disputed-resolution-history market categories |
| Edge decay (market learns/efficient-ifies) | High over 3-6 months | Return to zero | Monitor returns weekly; shut down when realized < 50% of prior month for 2 consecutive weeks |
| Polymarket regulatory action blocking non-US users | Medium over 12 months | Lose access to the venue | Capital cap at "would be fine if this vanishes"; don't compound to $50k+ without regulatory clarity |
| Polygon chain halt / USDC bridge failure | Low | Temporary loss of access | Monitor chain status; emergency stop triggers automatically on persistent connection failures |
| Competitive entry (bigger bots join) | High | Lower returns, not catastrophic | Expected; ÷5 rule already assumes significant haircut |
| Our execution bot malfunctions | Medium | Could lose $1000s in a bad loop | Safety rails: max order size, max orders/minute, daily loss limit, kill-switch file-flag |
| NZ banking / wallet off-ramp issues | Medium | Profits stuck on Polymarket | Test small withdrawals early; establish reliable off-ramp before scaling |

---

## Methodology discipline (durable rules)

These are saved in persistent memory (`feedback_research_methodology.md`). Applied throughout this plan:

1. **Rule 1 — Divide monthly-revenue estimates by 5** before presenting them for decision. Applied in the Executive Summary and throughout.
2. **Rule 2 — Write the counter-memo** alongside any "this works" finding. Sections below labelled "Kill criteria" and "Risk register" serve this role.

**If any future number in this plan updates to >$50k/month at $10k capital: methodology has drifted.** That's the warning shot.

---

## What's already built (current inventory)

### In `probe/`
- 24h reconnaissance probe (completed) with 1,316 clean resolutions + 791k snapshots

### In `experiments/`
- `e1_post_expiry_paths/` — confirmed price SNAP behavior (16/20 markets, median 30s)
- `e2_deribit_iv/` — Deribit IV snapshot 1 captured
- `e3_leadlag/` — 100ms Binance→Coinbase lead-lag detected; rig validated
- `e4_book_depth/` — mid-life books are 1¢/99¢ stubs (documented)
- `e5_historical_backfill/` — CLOB retains resolution data; data-api has trade history
- `e6_rate_limits/` — baseline latencies captured (gamma 120ms, CLOB /markets 270ms, data-api 100ms)
- `e7_resolution_sources/` — 88% of crypto markets resolve against Chainlink Data Streams
- `e8_week_watcher/` — watcher.py written, NOT launched (user approval needed for 168h spawn)
- `e9_live_arb_scan/` — scan.py validates current opportunities; confirmed $18k of simultaneous capturable depth
- `e9_wallet_competitor_intel/` — Respectful-Clan identified + profiled; 2000 trades characterized

### In `docs/`
- `README.md` — entry point
- `FINDINGS.md` — chronological log of everything
- `PLAN_HISTORY.md` — the v0→v1→v2→v3 evolution story
- `MASTER_PLAN.md` — **this document**
- `OPPORTUNITY_HOURLY_LADDER_MM.md` — dead
- `OPPORTUNITY_SPORTS_EVENT_LAG_ARB.md` — alive, secondary
- `COUNTER_MEMO_MM_OPPORTUNITY.md` — methodology artifact

### In memory
- `feedback_asymmetric_thinking.md` — prefer asymmetric upside
- `feedback_research_methodology.md` — ÷5 and counter-memo rules

### Not yet built
- The production bot itself (Phase 2)
- The backtest (Phase 1)
- The Phase 0 live tests (user-led)
- 4h and weekly market recon (pre-Phase 4)
- Polymarket account, VPS, wallet setup (user-led)

---

## The next 7 days — concrete checklist

**Day 0 (today):**
- [x] Probe stopped, final report generated
- [x] Master plan written
- [x] Master plan critique incorporated (regime-dependence gate added)
- [ ] User: decide honestly whether this is hobby research or planned capital deployment

**Day 1-3 (parallel tracks):**
- [ ] Claude: Phase 0a regime-stratified backtest
- [ ] Claude: write Phase 0b wallet-shadowing watcher
- [ ] User: launch Phase 0b watcher to VPS (if VPS exists; laptop works too for this task)

**Day 4:** Phase 0a result is in.
- **If Phase 0a fails:** stop. Write up findings honestly. Do not deploy capital.
- **If Phase 0a passes:** proceed to user-side Phase 0c fee/latency tests.

**Day 5–21 (parallel):**
- Phase 0b continues observing Respectful-Clan across ≥2 regime shifts
- Claude writes Phase 1 implementation backtest
- User decides whether to continue based on Phase 0b weekly reports

**Day 22+ (conditional on Phase 0a AND Phase 0b clearing):**
- Phase 2 bot skeleton + paper trading
- Only after 48h clean paper: Phase 2 live at $500 cap (revised down from $1000 per critique)
- Phase 3 scale only after 3-4 weeks of live results (revised from 1-2 weeks)

---

## Final honest framing (revised after LM critique)

**This plan's numeric estimate is unvalidated.** The $0-15k/month range is the honest representation after accounting for regime-dependence uncertainty. The probability-weighted expectation at $10k capital is not calculable from the data we currently have — because we haven't observed the strategy across regime shifts.

**Three scenarios to consider honestly:**

- **Scenario A (regime-independent edge):** strategy works in both UP and DOWN regimes at ≥92% win rate. Expected monthly: $5-15k at $10k capital. Probability: unknown — Phase 0a will tell us.
- **Scenario B (trend-conditional edge):** works only in DOWN regimes (our current observation). Expected monthly conditional on running-only-in-favorable-regimes: $1-5k (less frequent deployment). Probability: plausibly high given the 69/31 DOWN bias in our data.
- **Scenario C (no edge, just regime luck):** Respectful-Clan's 38h run was favorable-regime luck and the rule is net-negative after fees in any regime. Expected monthly: 0 or negative. Probability: meaningful and deserves to be proven impossible before live deployment.

**Phase 0a is the experiment that moves probability mass between these scenarios.** Without running it, deploying capital is a bet on Scenario A that we have no basis to make.

**The hobby-vs-production question is a real one.** This plan has crossed from "interesting research" into "operational capital deployment." That's a choice the user should make consciously, not drift into. If the answer is "this is still a hobby, I won't actually deploy capital," then Phase 0a becomes an interesting research exercise with no urgency. If the answer is "yes I intend to deploy capital," then Phase 0a is the load-bearing experiment and nothing should happen before it.

The value of doing it isn't just the money — it's:
- Real operational experience running a quant-style strategy
- A validated methodology for finding future opportunities in adjacent spaces
- A working infrastructure that can host other strategies (sports arb, 4h markets, whatever comes next)

If none of that is worth 1-2 weeks of focused build time for an honest $5-10k/month EV, don't do this. If it is, the plan above is the path.
