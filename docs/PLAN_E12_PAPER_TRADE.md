# Paper-trade harness for sports settlement-lag arb (v3)

## Context

Two-day falsification cycle killed 8 of 9 theses on this repo. The `e12_paper_trade` design then went through two external audits that materially reshaped the plan:

- An `e13_external_repo_audit` investigation running in parallel, which historically backtested both surviving theses against the 954M-row SII-WANGZJ on-chain Polymarket dataset
- A live protocol-docs + academic-lit sweep via three parallel research agents in this thread

The current state after those audits:

**KILLED by e13 historical backtest:**
- `crypto_barrier` — n=5,220 entries, **notional-weighted net edge −63.4% at any fee**, 37% crash rate. As-designed, this strategy destroys capital. Drop entirely; salvage variants (tighter spot-distance filter) are a separate exploration, not part of e12.

**SURVIVING (with specific caveats):**
- `sports_lag` — n=47 entries, **+3.99% net edge at realized 0 bps fees**, 14.4 min avg hold. Sample-thin; edge directionally confirmed but confidence band is wide. Edge is robust to fee assumption across 0–300 bps.

**Fee gate resolved empirically:**
- e13 joined 143 sports post-resolution trades to on-chain fee fields: `taker_fee = 0` and `maker_fee = 0` across **all** price bands (0.95–0.99). The H3 "need a $10 live fee test" blocker is resolved. Default `FEE_BPS = 0`.
- Note: Polymarket's docs publish non-zero rates (Sports 3 bps, Crypto 7.2 bps). The empirical zero may reflect a per-market `feeRate` override set to zero, a maker-only fee structure, or the pre-V2 schedule that dominated the dataset (cut at 2026-03-31). **Phase 0 shakedown verifies pm-trader bills $0 on a live sports buy; if it doesn't, halt and reconcile.**

**Yellow flag (academic):**
- Saguillo 2508.03474 (Arxiv 2025) measured Polymarket arb duration collapsing from 12.3s (2024) → **2.7s (2025)**, with **73% of arb profits captured by sub-100ms bots**. This is for general arb, not specifically post-resolution sports lag — but signals the ecosystem has tightened. Our 14.4 min sports_lag window (from e13) is far longer than Saguillo's 2.7s, so this strategy class may still have retail-paced windows. Treat as a caveat to watch, not a kill.

**Academic framing confirmed:**
- Della Vedova 2026 (SSRN 6191618, "Execution, not Information") empirically validates the premise: bots pay 2.52¢ less per contract than casual traders across 222M trades. Execution edge is a real, measurable phenomenon. No paper has isolated the specific post-resolution sports window — that is the gap our paper trade fills.
- Akey et al. 2026 (SSRN 6443103) warn that **market-making is the only strategy class with predicted positive returns**; taker strategies underperform on average. sports_lag is technically a taker strategy. This is a prior worth respecting, not a kill.

**Protocol reality:**
- **V2 cutover 2026-04-22** (3 days from now). CTF Exchange V2 + CLOB V2 with no V1 backward compatibility. Order struct changes (removed `nonce`/`feeRateBps`/`taker`; added `timestamp`/`metadata`/`builder`). Our paper trade doesn't submit on-chain, so order-struct changes are mostly insulated — but gamma-api response shapes, fee schedule, and matching semantics may change. Plan explicitly schedules a pause-verify-resume around cutover.
- Gamma rate limits: **4000 req/10s general, 300/10s on `/markets`**. Prior plan guessed 5/s and was 60× conservative.
- Fee formula: `fee = shares × feeRate × p × (1−p)` — symmetric, peaks at p=0.5. NOT `min(p, 1−p)` (prior plan had this wrong). Per-market `feeRate` fetchable via `getClobMarketInfo(conditionID).info.fd.r`.
- CLOB priority: price-time (not pro-rata). Cancel-before-match latency: not publicly documented — remains empirical unknown.
- UMA resolution: 2h liveness, $750 bond each side. Sports dispute rate inferred <0.5% post-MOOV2 (platform-wide ~2%).

**Known operators:**
- `LlamaEnjoyer` (full wallet `0x9b979a065641e8cfde3022a30ed2d9415cf55e12`, pseudonym Digital-Shelf, Twitter @Verrissimus). Pulled 500 trades over 125 days from polymarket data-api in `experiments/e13_external_repo_audit/data/llamaenjoyer/`:
  - Portfolio value: $101,504. Total bought: $2.21M (399 trades). Total sold: $885k (101 trades). Net deployed: $1.32M.
  - Median entry price: 0.981. Distribution: **41% of buys at price ≥ 0.99**, 26% at 0.95–0.99, 33% at < 0.95.
  - Slug mix: 45% sports, 6% Fed/politics, 3% geopolitics, 1% crypto, 44% other.
  - Recent textbook sports-lag entries: UFC Reyes @ 0.999 size 34,425 ($34k), La Liga Atletico-NO @ 0.999 size 151,305 ($151k), Arsenal-NO @ 0.999 size 20,000.
  - Fed-rate "100% loss" positions are negative-risk hedge structures (buy all 3 outcomes summing < $1.00; one pays $1), not actual losses.
  - **Strategic divergence from this plan's operating point:** he operates at 0.99–0.999 with $34k–$151k size; per-trade edge ~0.1%; profitable absolutely because of position scale. e12 plan targets 0.95–0.97 with $100–$300 size; per-trade edge ~3–4%; relies on edge magnitude rather than scale. The 0.95–0.97 zone may have far less depth because operators like LlamaEnjoyer (and the bots Saguillo describes) take it before it gets there. **Open question:** should e12 add a 0.99 cap variant to measure whether the volume-rich zone has any edge left for a small operator? See "Known limitations" → "Operating-point gap."
- Top-3 arb wallets captured $4.2M across 10,200 bets over 12 months (category split not published)
- `@defiance_cr` open-sourced and shut down his MM bot: "no longer profitable"
- Retail is the seller side of the post-resolution window (behavioral, persistent)

## Scope

Build `experiments/e12_paper_trade/` as a restart-safe continuous daemon:

- **Single strategy:** `sports_lag` only (crypto_barrier is dropped; see NULL_RESULTS.md)
- **Two size models:** `fixed_100`, `depth_scaled` (25% of ask depth at target) → 2 pm-trader accounts
- **Poll cadence:** 2–3s book-poll (not 20s) — well within Gamma limits and closer to the ecosystem's compression
- **Detection:** sports-feed-triggered Path A (ESPN/nba_api/MLB-StatsAPI) + book-state Path B
- **Fee assumption:** `FEE_BPS = 0` default, parameterized; shakedown asserts pm-trader agrees
- **Risk gates:** 20% cell drawdown breaker, 3 concurrent positions per event cap
- **Metadata client:** `polymarket-apis` typed Pydantic (not hand-rolled aiohttp)
- **V2 cutover:** scheduled pause on 2026-04-22, resume after verification
- **Sample target:** 50–100 completed trades OR 7-day hard stop, whichever first
- **Decision:** keep if net edge ≥ 0.5% at 0 bps; kill on negative or < 0.5% net

Out of scope: crypto_barrier (dead), live order placement, VPS provisioning, historical backtest (owned by e13), sub-second WebSocket detection (future upgrade), Kalshi cross-venue arb (separate plan).

## Dependencies

```
uv add polymarket-paper-trader
uv add polymarket-apis               # typed Pydantic gamma client
uv add httpx pyratelimiter            # async + rate-limit for any remaining raw HTTP
uv add espn-api nba_api MLB-StatsAPI  # sports result feeds
uv add python-binance                 # BTC/ETH spot (future; not on critical path now that crypto_barrier is dropped)
```

Binance public endpoints work from NZ without auth. python-binance stays in deps for future work even though crypto_barrier is out of e12.

## Files to create

```
experiments/e12_paper_trade/
├── README.md
├── config.py              # all economic assumptions parameterized
├── http_client.py         # shared httpx.AsyncClient + PyrateLimiter (for non-gamma endpoints)
├── gamma_client.py        # polymarket-apis PolymarketGammaClient wrapper
├── shakedown.py           # Phase 0: pm-trader sanity + zero-fee assertion
├── slug_audit.py          # Phase 1a: validate sports slug patterns vs recent resolutions
├── pre_run.py             # Phase 1b: 1-hour observe-only detection counter
├── sports_feeds.py        # unified game-end stream (ESPN + nba_api + MLB-StatsAPI)
├── detector.py            # sports_lag only; dual-path (feed + book-poll)
├── risk.py                # drawdown breaker + event concentration gate
├── trader_client.py       # thin wrapper over pm-trader
├── daemon.py              # main loop
├── v2_migration.py        # one-shot: pre/post 2026-04-22 cutover verification
├── resolver.py            # mark resolved; compute PnL via pm-trader history
├── report.py              # time-weighted return; --fee-bps re-scoreable
├── schema.sql             # sidecar with event_id
└── sidecar.db             # gitignored
```

## Parameterized config (`config.py`)

```python
# Fees
FEE_BPS = 0                  # empirical from e13 (n=143 sports post-resolution trades)
                             # shakedown verifies pm-trader agrees; report re-scoreable via --fee-bps

# Poll cadence
POLL_INTERVAL_S = 2          # well within Gamma 300/10s on /markets
FILL_RECHECK_DELAY_S = 1     # for fill-confirmation; not used in v1 since pm-trader is synchronous

# Sample and run bounds
SAMPLE_TARGET_TRADES = 75
MAX_RUN_HOURS = 168

# Account setup — 2 size models × 2 entry caps = 4 cells (2x2 grid)
# The two entry caps run in parallel; tells us whether edge concentrates at
# the tighter price (where most opportunities have moved on) or persists at
# the looser one (where fills are more frequent). Free information vs single-cap.
SEED_BALANCE = 10_000
ENTRY_TARGET_CAPS = [0.95, 0.97]   # tested in parallel
ACCOUNTS = [
    ("sports_lag", "fixed_100",   0.95),
    ("sports_lag", "fixed_100",   0.97),
    ("sports_lag", "depth_scaled", 0.95),
    ("sports_lag", "depth_scaled", 0.97),
]
# Account-name convention: sports_lag__fixed_100__cap95, ...__cap97, etc.

# Entry sizing
DEPTH_SCALED_FRAC = 0.25
# Note: ENTRY_TARGET_CAP is now per-cell (see ACCOUNTS); each cell uses its
# own cap to filter detections. Detection scan uses max(ENTRY_TARGET_CAPS)=0.97
# so both cells can evaluate the same detection.

# Risk gates (Octagon-derived, per e13 Investigation 2)
MAX_DRAWDOWN_PER_CELL = 0.20      # kill cell at 20% drawdown
MAX_OPEN_PER_EVENT = 3            # max 3 concurrent positions per event_id

# Rate limits (per docs.polymarket.com/quickstart/introduction/rate-limits)
GAMMA_GENERAL_LIMIT_PER_10S = 4000
GAMMA_MARKETS_LIMIT_PER_10S = 300
GAMMA_EVENTS_LIMIT_PER_10S = 500
```

## Phase 0 — shakedown (`shakedown.py`)

**Must pass before Phase 1.**

### 0a. pm-trader sanity
1. Init throwaway $1k pm-trader account
2. Pick current top-volume sports market via gamma-api
3. Fetch real order book
4. Place $50 market buy via pm-trader; read back fill
5. Verify fill walks real book; fee matches the **published** formula `bps/10000 × price × (1-price) × shares` — note the **p×(1-p)** shape, not `min(p,1-p)`
6. Limit order lifecycle (place → pending → cancel)
7. Determine pm-trader API shape (Python vs CLI)

### 0b. Zero-fee assertion (new, critical)
Buy a $5 position in a recently-resolved sports market (winning side at ~0.97). Read back pm-trader's recorded fee:
- If `fee == 0` → empirically matches SII data. Proceed.
- If `fee > 0` → pm-trader's model disagrees with on-chain reality. **Halt.** Three paths:
  a. Reconcile: check whether pm-trader's `bps` parameter is configurable; set to 0
  b. Investigate: pull the live market's `getClobMarketInfo(conditionID).info.fd.r` to see the actual feeRate override
  c. **MANDATORY backtest re-validation** (replaces the prior "accept conservative assumption" option). If reconciliation (a) and investigation (b) both confirm the live exchange charges the non-zero rate:
     1. Re-run `experiments/e13_external_repo_audit/03_sii_sports_lag_backtest.py` with `DEFAULT_FEE_BPS = <verified live rate>`.
     2. If historical net edge at the live rate falls below the **ambiguous-zone floor (1.5%, see decision criterion below)** → halt the project and re-evaluate the strategy. Do not paper-trade a thesis whose historical edge dies at the realistic fee.
     3. If historical net edge at the live rate stays ≥ 1.5% → proceed, but lock the live rate as the new `FEE_BPS` default and re-run `slug_audit.py` and `pre_run.py` with it before unpausing.

  Rationale: a "more conservative assumption" is still an assumption. The historical backtest is the only check against picking a strategy that survives at fee=0 but dies at fee=published-rate.

### 0c. V2 readiness check
- Confirm pm-trader's installed version. Check its GitHub/PyPI for V2 migration notes.
- If no V2 support announced by 2026-04-22, plan to pause daemon, pin a known-good commit, and re-verify post-cutover.

(Dropped from v2 of this plan: the Nautilus cross-check. Now that e13 has given us on-chain fee truth, the Nautilus cross-check is redundant unless 0b fails.)

## Phase 1 — pre-flight

### 1a. `slug_audit.py`
Pull 20–30 most recent resolved sports markets via `polymarket-apis`. Validate and correct the pattern list (`atp-`, `wta-`, `nba-`, `nfl-`, `mlb-`, `cricipl-`, `ufc-`, `mls-`, `wnba-`, `nhl-`). Output corrected `SPORTS_SLUG_PATTERNS` constant.

Also: verify `PolymarketReadOnlyClobClient.get_market` returns populated tokens on active sports markets (per e13 Investigation 3, the CLOB client was reachable but returned 0 tokens on an inactive event — needs retest with a live sport market before we rely on it).

### 1b. `pre_run.py` (1 hour observe-only)
Run the full detection loop without placing orders:
- Detection count per detection path (Path A = feed-triggered, Path B = book-poll)
- Unique markets per hour
- Extrapolated hours to `SAMPLE_TARGET_TRADES = 75`
- Flag if projection > 7 days → scope change before committing

## Sports-result feeds (`sports_feeds.py`)

Three sources behind one interface, polled every 15s. Output: stream of `GameEndEvent(sport, home, away, winner, ended_at)`:

- **NFL/NHL/soccer/general:** `pseudo-r/Public-ESPN-API` (454⭐, ESPN hidden endpoints)
- **NBA:** `swar/nba_api` (3.5k⭐, live boxscore, 5–10s lag)
- **MLB:** `toddrob99/MLB-StatsAPI` (783⭐)
- **Tennis/cricket/UFC:** no feed path, book-poll only

Degrades gracefully if ESPN endpoints break — falls back to book-poll only.

## Entry rules (`detector.py`)

Dual detection paths, single entry logic. Both feed through the risk gate.

**Path A — sports-feed triggered:**
- `GameEndEvent` fires
- Look up Polymarket market via `PolymarketGammaClient` slug search (team names + date)
- Fetch current order book
- If ask on winner side ≤ 0.98 with depth → candidate

**Path B — book-state poll:**
- Every `POLL_INTERVAL_S` (2s), query `/markets` with audited slug patterns via `polymarket-apis`
- `closed == false AND active == true` (zombie filter)
- `last_trade_price > 0.95` (YES winning) or `< 0.05` (NO winning)
- Within 30 min of last trade
- Ask ≤ 0.98 with depth → candidate

Dedup by `(market_slug, side)` — first path wins on a tie.

Entry target: `min(ask_price, ENTRY_TARGET_CAP)` = `min(ask, 0.97)`.

## Risk gates (`risk.py`)

Two gates, both checked before pm-trader order placement:

1. **Cell drawdown:** `(current_balance - seed_balance) / seed_balance`. If < `-MAX_DRAWDOWN_PER_CELL` (20%), skip; log `skipped_reason='drawdown_breaker'`.
2. **Event concentration:** count open positions on the same `event_id`. If ≥ `MAX_OPEN_PER_EVENT` (3), skip; log `skipped_reason='event_concentration_cap'`.

Skipped detections still land in the `detections` table for analysis.

## Sidecar schema (`schema.sql`)

```sql
CREATE TABLE position_context (
  pm_trade_id TEXT PRIMARY KEY,
  account TEXT NOT NULL,              -- 'sports_lag__fixed_100__cap95' etc.
  strategy TEXT NOT NULL,             -- always 'sports_lag' in v3
  size_model TEXT NOT NULL,
  entry_cap REAL NOT NULL,            -- 0.95 or 0.97 (per 2x2 grid)
  detection_path TEXT NOT NULL,       -- 'feed' | 'book_poll'
  market_slug TEXT NOT NULL,
  event_id TEXT,                      -- for per-event concentration cap
  side TEXT NOT NULL,
  detected_at TEXT NOT NULL,
  entry_ask REAL NOT NULL,
  entry_bid REAL,
  ask_size_at_entry REAL NOT NULL,
  protocol_version TEXT NOT NULL,     -- 'v1' | 'v2' — set at insertion based on V2 cutover state
  market_context JSON,
  resolved_at TEXT,
  resolution_price REAL,
  resolution_status TEXT              -- 'open' | 'resolved_win' | 'resolved_loss' | 'disputed' | 'stuck'
);

CREATE TABLE detections (
  id INTEGER PRIMARY KEY,
  ts TEXT NOT NULL,
  strategy TEXT NOT NULL,
  detection_path TEXT NOT NULL,
  market_slug TEXT NOT NULL,
  event_id TEXT,
  last_trade REAL,
  best_ask REAL,
  ask_size REAL,
  -- skipped at evaluation time:
  skipped_reason TEXT,                -- null if placed; else 'already_open' | 'no_depth' | 'zombie'
                                      --                       | 'drawdown_breaker' | 'event_concentration_cap'
                                      --                       | 'cap_too_tight'  -- detection above this cell's entry cap
                                      --                       | 'early_killed'   -- cell already killed by 20-trade rule
  -- fill-side instrumentation (populated when we attempt + receive a fill):
  fill_attempted_at TEXT,             -- when pm-trader market_buy was called
  fill_completed_at TEXT,             -- when fill came back
  fill_price REAL,                    -- actual fill price (vs best_ask at detection)
  fill_qty REAL,                      -- vs ask_size at detection (partial fills surface here)
  latency_ms INTEGER,                 -- detection_ts → fill_completed_at, ms
  slippage_bps REAL                   -- (fill_price - best_ask) / best_ask × 10000
);

-- Distinguishes "no edge exists" from "edge exists but I'm too slow."
-- Without this, a null result is ambiguous; with it, we know whether to
-- abandon the strategy or move to WebSockets / co-location.
CREATE TABLE missed_opportunities (
  id INTEGER PRIMARY KEY,
  market_slug TEXT NOT NULL,
  event_id TEXT,
  detected_via TEXT NOT NULL,         -- 'post_facto_scan' | 'partial_fill_residual'
  arb_window_start_ts TEXT NOT NULL,
  arb_window_end_ts TEXT NOT NULL,
  best_price_observed REAL,           -- best ask seen during the window
  total_capturable_usd REAL,          -- sum of ask depth × price under our cap
  reason_we_missed TEXT NOT NULL,     -- 'no_detection' | 'detected_too_late'
                                      --   | 'attempted_no_fill' | 'partial_fill'
                                      --   | 'cap_too_tight'
  our_detection_id INTEGER,           -- FK to detections.id if we did detect
  our_fill_id TEXT                    -- FK to position_context.pm_trade_id if partial
);
```

**`missed_scanner.py`** (new daemon worker, runs every 5 min):
For every sports market that resolved in the last 60 min, pull its trade tape from gamma-api during the post-resolution window. Compute `total_capturable_usd` at our `max(ENTRY_TARGET_CAPS)=0.97`. Cross-reference against `detections` and `position_context`. Categorize:
- We **never detected** it → `reason_we_missed='no_detection'` (slow-poll problem; suggests WebSockets)
- We **detected but didn't attempt** → `reason_we_missed='cap_too_tight'` (best_ask was above all cell caps)
- We **attempted but no fill** → `reason_we_missed='attempted_no_fill'` (latency / contention)
- We **got partial fill** → `reason_we_missed='partial_fill'` (insufficient depth)

## Daemon loop (`daemon.py`)

```
ensure_accounts_exist()
start_task(sports_feeds.listen, on_event=handle_game_end)
start_task(missed_scanner.run_periodic, interval_s=300)
while not reached_sample_target() and not past(MAX_RUN_HOURS):
    if v2_cutover_pause_active():        # paused via cron at 2026-04-22 ~09:30 UTC
        sleep_until(v2_migration.verified_clean())
        # if not verified within 72h, daemon stays paused; operator decides
        # whether to accept V1-only sample or extend further

    protocol_version = current_protocol_version()  # 'v1' before cutover, 'v2' after verified

    for c in detector.find_entries_book_poll():
        log_detection(c)
        maybe_place(c, protocol_version)

    resolver.check_open_positions()
    sleep(POLL_INTERVAL_S)

def handle_game_end(evt):
    c = detector.check_entry_from_feed(evt)
    if c:
        log_detection(c)
        maybe_place(c, current_protocol_version())

def maybe_place(c, protocol_version):
    if already_open_position(c.slug, c.side, c.account):
        log_detection(c, skipped_reason='already_open'); return
    for (strategy, size_model, entry_cap) in ACCOUNTS:    # 2x2 grid
        account = f"{strategy}__{size_model}__cap{int(entry_cap*100):02d}"
        if c.best_ask > entry_cap:
            log_detection(c, account, skipped_reason='cap_too_tight'); continue
        if risk.cell_drawdown_exceeded(account):
            log_detection(c, account, skipped_reason='drawdown_breaker'); continue
        if risk.event_concentration_exceeded(account, c.event_id):
            log_detection(c, account, skipped_reason='event_concentration_cap'); continue
        if early_killed(account):                          # 20-trade early kill
            log_detection(c, account, skipped_reason='early_killed'); continue
        size_usd = compute_size(size_model, c)
        det_id = log_detection(c, account, fill_attempted_at=now())
        pm_trade = trader_client.market_buy(account, c.slug, c.side,
                                            size_usd, target_price=entry_cap)
        update_detection_fill(det_id, pm_trade)            # populates fill_price, latency_ms, etc.
        insert_position_context(pm_trade, c, size_model, entry_cap, protocol_version)
```

## V2 cutover plan (`v2_migration.py`)

The 2026-04-22 cutover happens during the run window. Daemon runs on V1 from now until cutover, pauses through it, and resumes on V2 after verification. Every position is tagged `protocol_version` ('v1' | 'v2') so the report can stratify.

1. **2026-04-22 ~09:30 UTC (pre-cutover):** daemon receives a `pause` signal (cron-triggered). Logs current state snapshot + runs `v2_migration.py snapshot`:
   - `markets.parquet` schema + 50 sampled rows
   - `getClobMarketInfo(conditionID).info.fd.r` for 5 active sports markets
   - `polymarket-apis` Pydantic model field set
   - Persist to `data/v2_pre_snapshot.json`
   - Stop placing new orders ~30 min before scheduled cutover time. Existing positions resolve naturally.
2. **2026-04-22 ~10:00 UTC:** Polymarket brings V2 live (~1h downtime expected). Daemon stays paused.
3. **2026-04-22 +24h (or until library patches land):** run `v2_migration.py verify`:
   - Re-pull the same surfaces; diff against `v2_pre_snapshot.json`
   - **Schema drift:** any added/removed field in the gamma `Market` model that `polymarket-apis` doesn't yet handle → patch the library or pin to a fork; daemon stays paused
   - **Fee schedule:** if fee rate is now non-zero, apply Phase 0b's mandatory backtest re-validation rule (re-run `e13/03` with the new rate; halt if historical edge falls below 1.5% ambiguous-zone floor)
   - **CLOB tokens:** `PolymarketReadOnlyClobClient.get_market` returns populated tokens on active sports markets
   - Re-run `shakedown.py` (0a + 0b) against V2-live exchange
4. **Pre-committed: don't mingle V1 and V2 data if V2 broke something.** If verification reveals breaking semantic changes (fee schedule moves, matching priority changes, slug patterns shift), the report.py should treat V1 and V2 cells as separate datasets, not a continuous run. Specifically: if any of {fee_bps changes by ≥ 50, slug pattern coverage drops by ≥ 20%, observed best_ask distribution shifts by ≥ 10%} → discard V2-tagged positions from the v1-vs-v2 comparison; treat the V1-only sample as the canonical edge measurement.
5. **Resume:** daemon restarts after verify passes; subsequent detections/positions sidecar-tagged `protocol_version='v2'`. Earlier positions are tagged `v1`.
6. **If verification fails persistently (e.g. > 72h):** keep daemon offline; treat the V1-only sample as the canonical dataset; report at full sample using V1 data only.

## Resolver (`resolver.py`)

For each open position > 10 min old:
- Fetch market state via `PolymarketGammaClient`
- `closed == true` + clean `outcomePrices` → `resolved_win` / `resolved_loss`
- `umaResolutionStatus != resolved` → `disputed` (log for empirical H4 rate)
- Age > 24h still open → `stuck`

pm-trader owns PnL via natural resolution mechanic.

## Report (`report.py`)

Joins pm-trader trade history with sidecar on `pm_trade_id`. Accepts `--fee-bps` (defaults to 0).

Per `(size_model)` cell:

```
sports_lag × fixed_100  (fee_bps = 0)
  Positions opened: N       Resolved: R    Disputed: D    Stuck: S    Open: O
  Gross edge: E %           Net edge: E' %
  Fill rate: F %            Avg slippage (bps): B
  Hit rate: H %
  Avg hold: T min           Time-weighted return: W %/year
  Total net PnL: $X

  Path split:
    feed-triggered:   N_A positions  avg_lag_from_game_end: L sec
    book-polled:      N_B positions

  Risk-gate skips:
    drawdown_breaker:       K events
    event_concentration:    K events

  V2 migration: ok / pending / failed
```

Re-run at `fee_bps = 0, 100, 300` for sensitivity (validates e13's fee-robustness finding on live data).

**Decision criterion** (pre-committed before the run; do NOT modify after seeing results):

**Final criterion at full sample (75 trades / cell):**

| Net edge at `fee_bps = 0` (or actual live rate per Phase 0b) | Action |
|---|---|
| < 0.5% OR total PnL negative | **KILL** the cell |
| 0.5% ≤ net edge < 1.5% | **AMBIGUOUS** — do NOT proceed to capital. Extend sample by another 75 trades (or 7-day cap, whichever first), then re-evaluate. If still ambiguous → kill. |
| ≥ 1.5% | **PROCEED** to capital-deployment decision |

**Early-kill criterion (per cell, after 20 completed trades):**
- If notional-weighted net edge < 0% AND total realized PnL < 0 → **KILL the cell early.** Don't burn 3-5 days of attention on a cell that's clearly negative at n=20.
- Otherwise continue to 75. (The 20-trade gate is asymmetric — it can kill but not promote; positive-but-small cells must reach 75 to be evaluated against the bands above.)

Rationale: pre-commit prevents observed-edge magnitude from biasing the bar. Sample-thin "barely positive" results historically translate to negative real-money runs after fees, slippage, and the operator-skill gap (Akey 2026: <30% of Polymarket traders profitable; Della Vedova 2026: bots take 2.52¢ per contract from casual traders). The 20-trade early kill is a separate motivated-reasoning safeguard: "keep grinding because maybe it'll turn around" is a worse failure mode than killing 1-2 cells unnecessarily.

**Per-cell missed-opportunity diagnostic** (from `missed_opportunities` table):

| `reason_we_missed` distribution | Interpretation |
|---|---|
| `no_detection` dominates | We're polling too slowly. Move to WebSockets / lower `POLL_INTERVAL_S`. |
| `cap_too_tight` dominates | Edge exists at higher prices than our caps allow. Loosen `ENTRY_TARGET_CAPS`. |
| `attempted_no_fill` dominates | Latency / contention. NZ-laptop is the bottleneck; consider VPS. |
| `partial_fill` dominates | Our size model is too aggressive vs available depth. Reduce `DEPTH_SCALED_FRAC`. |

**Critical:** a null result (low fill rate, low PnL) without this diagnostic is ambiguous — abandon strategy, or move to WebSockets / co-location? With the table populated, the answer is unambiguous.

## Verification (execution order)

1. `uv add polymarket-paper-trader polymarket-apis httpx pyratelimiter espn-api nba_api MLB-StatsAPI python-binance`
2. Run `shakedown.py` (0a + 0b + 0c). **Halt on zero-fee assertion failure.**
3. Run `slug_audit.py`. Commit corrected pattern list + CLOB-tokens verification.
4. Run `pre_run.py` for 1 hour. Confirm 75-trade target reachable in ≤ 7 days.
5. **Start daemon NOW** in tmux: `uv run python -m experiments.e12_paper_trade.daemon`. All positions sidecar-tagged `protocol_version='v1'` until 2026-04-22 cutover.
6. After 30 min: smoke-test `report.py`. Confirm positions opening on both paths, risk gates logging, no exceptions.
7. Spot-check 3–5 resolved positions against real gamma-api trade tape. >20% fill-model mismatch → pause and debug.
8. **2026-04-22 ~09:30 UTC:** signal daemon to pause (cron-triggered). Run `v2_migration.py snapshot` per V2 cutover plan above.
9. **2026-04-22 +24h:** run `v2_migration.py verify`. If clean, resume daemon (positions now tagged `v2`); if not, stay paused, re-attempt verification daily until clean (or accept V1-only sample if persistent).
10. Run until `SAMPLE_TARGET_TRADES = 75` hit per cell (or 7-day cap from start of step 5).
11. Final `report.py` at `fee_bps = 0, 100, 300`, stratified by `protocol_version`. If V1 and V2 samples agree within noise, treat as one dataset. If they diverge per the Diff 4 pre-commit, treat V1-only as canonical.
12. Apply decision criterion per size_model cell (see "Decision criterion" section for ambiguous-zone handling).

## Known limitations in v3

- **Sample-thin historical confirmation:** e13's sports_lag backtest n=47 is small. Plateau likely due to trades.parquet ordering; a deeper re-run (`MAX_TRADE_ROW_GROUPS=300`) is queued in e13's open-questions list but not blocking this plan.
- **H1 "flow-diffuse" — CONFIRMED at scale:** the initial n=121 probe contradicted H1 with top-10=68%, but the e13/08 follow-up at n=33,130 distinct wallets across 11,345 sports markets (RG coverage 42.6% of users.parquet, no price filter) reverses that: **top-10 = 21.5%, top-50 = 51.3%, top-100 = 65.7%, gini 0.98**. Average 21.9 wallets/market, p95 = 112 wallets/market. The original docs claim of "411 wallets across 5 markets, flow-diffuse" stands directionally; the sports post-resolution arb window IS retail-paced, not pro-dominated. Realistic-capture estimate of 5–15% for a NZ laptop operator stands without rescaling. Continue to monitor during paper trade — if realized fills are consistently the same top-10 wallets, the at-scale finding may not hold inside the post-resolution sub-window.
- **Operating-point gap vs known operators (LlamaEnjoyer):** e13's data-api pull showed LlamaEnjoyer (full wallet `0x9b97…e12`) operates at 0.99–0.999 entry with $34k–$151k position sizes (per-trade edge ~0.1%, profit from scale). This plan operates at 0.95–0.97 with $100–$300 (per-trade edge ~3–4%, profit from edge magnitude). Two risks: (a) the 0.95–0.97 zone may have dramatically less depth than 0.99–0.999 because operators like LlamaEnjoyer (and Saguillo's sub-100ms bots) take it before it reaches our cap; (b) per-trade absolute profit at our scale is ~$4–$10 vs his $35–$150. Fix path: the 2x2 grid's `cap_too_tight` skip rate from `missed_opportunities` will tell us whether (a) is real. If `cap_too_tight` dominates, consider adding a 0.99 cap variant in v2 of the plan. (Not adding to v1 because it'd dilute the n-per-cell budget without first knowing whether 0.95–0.97 has depth.)
- **V2 cutover during run:** 2026-04-22 protocol change forces a pause/verify/resume. Daemon runs on V1 starting now, pauses through cutover, resumes on V2 if verification passes. Every position tagged `protocol_version` so the report can stratify and (per pre-commit) discard V2 if the protocol breaks semantics. Risk of library lag mitigated by pinned versions + explicit `v2_migration.py verify` script.
- **Saguillo arb-compression trend:** general-arb duration collapsed 12.3s → 2.7s in a year. Our 14.4 min sports_lag window is 300× longer — currently safe but not permanently.
- **pm-trader fills against live book at detection:** no sub-second contention model. Realistic for a VPS-grade operator; a miss for anyone fighting sub-100ms bots.
- **UMA disputes counted, not modeled:** H4 inferred <0.5% for sports post-MOOV2. Report flags if rate in paper run exceeds 2%.
- **Fee = 0 finding is dataset-bounded:** SII cuts 2026-03-31. If Polymarket introduces taker fees post-dataset-cut, the shakedown (0b) is the continuous check; daily report re-scored at `--fee-bps 100` and `300` as sensitivity analysis.
- **No order cancel/replace logic.** Fill-or-nothing at detection.

---

# External-repo audit findings (consolidated)

Full source-of-truth for every repo/dataset/paper evaluated. Status:

- **integrated** — dependency in this plan
- **cross-check** — used once in a phase, not a runtime dep
- **future** — parked for v2 or separate plan
- **skip** — evaluated, rejected with reason
- **confirmed kill** — independent confirmation of a falsified thesis
- **deferred to e13** — handled by the parallel investigation

## Polymarket execution / paper-trading layer

| Repo | Status | Reason |
|---|---|---|
| [`agent-next/polymarket-paper-trader`](https://github.com/agent-next/polymarket-paper-trader) (253⭐) | **integrated** | Book-walking fills, exact fee formula, limit-order lifecycle, multi-account. Cuts ~50% of build effort. |
| [`evan-kolberg/prediction-market-backtesting`](https://github.com/evan-kolberg/prediction-market-backtesting) (628⭐) | **skip** | Originally planned as Phase 0 fee cross-check. e13's on-chain fee truth (fee=0) makes this cross-check redundant unless shakedown 0b fails. |
| [`nautechsystems/nautilus_trader`](https://github.com/nautechsystems/nautilus_trader) (22k⭐) | **future** | Backing framework for evan-kolberg. Upgrade path if pm-trader outgrows us. |
| [`Polymarket/agents`](https://github.com/Polymarket/agents) (3k⭐, 2024-11) | **future** | Official `py-clob-client` + Pydantic models. Stale. Bookmark for live capital deployment post-paper. |
| [`Polymarket/poly-market-maker`](https://github.com/Polymarket/poly-market-maker) | **cross-check** | Reference for fee formula. Consult during shakedown 0b if fee reconciliation is needed. |

## Polymarket client libraries

| Repo | Status | Reason |
|---|---|---|
| `polymarket-apis` (PyPI, v0.5.7) | **integrated** | Typed Pydantic gamma + CLOB client. e13 Investigation 3 confirmed drop-in replacement. Used in `gamma_client.py`. CLOB token retrieval still needs verification on active sports markets (deferred to slug_audit). |
| `httpx + PyrateLimiter` | **integrated** | Async + rate-limit stack for any non-gamma HTTP. PyrateLimiter 492⭐ standard answer. |
| [`nevuamarkets/poly-websockets`](https://github.com/nevuamarkets/poly-websockets) (71⭐, TS) | **future** | Real-time CLOB WS (book/price_change/last_trade). TS-only; ~80 lines to port. Not needed at 2s polling. |
| [`Polymarket/real-time-data-client`](https://github.com/Polymarket/real-time-data-client) (203⭐, TS) | **future** | Official version of above. |
| [`the-odds-company/aiopolymarket`](https://github.com/the-odds-company/aiopolymarket) (20⭐, stale) | **skip** | Fails maintenance filter. Roll our own with httpx + PyrateLimiter (which is already in deps). |

## Historical data / backtesting

| Repo | Status | Reason |
|---|---|---|
| SII-WANGZJ/Polymarket_data (HuggingFace, 107 GB) | **integrated via e13** | 954M on-chain rows, 19-day fresh. Delivered: fee=0 empirical, crypto_barrier -63% edge, sports_lag +3.99% edge. Open questions queued in e13's findings.md. |
| [`Jon-Becker/prediction-market-analysis`](https://github.com/Jon-Becker/prediction-market-analysis) (3k⭐) | **e13 fallback** | 36 GiB Polymarket+Kalshi parquet. SII passed schema probe; Jon-Becker on standby if SII is unreliable. |
| [`warproxxx/poly_data`](https://github.com/warproxxx/poly_data) (1.3k⭐) | **future (v2)** | Goldsky subgraph for live order-level data with wallet addresses. Cleaner than gamma trade feed. v2 upgrade if hot-market contention flagging needs hardening. |

## Sports result feeds

| Repo | Status | Reason |
|---|---|---|
| [`pseudo-r/Public-ESPN-API`](https://github.com/pseudo-r/Public-ESPN-API) (454⭐) | **integrated** | Multi-sport via ESPN hidden endpoints (NFL/NBA/MLB/NHL). Degrades to book-poll fallback if broken. |
| [`swar/nba_api`](https://github.com/swar/nba_api) (3.5k⭐) | **integrated** | Official NBA.com live boxscore. 5–10s lag. |
| [`toddrob99/MLB-StatsAPI`](https://github.com/toddrob99/MLB-StatsAPI) (783⭐) | **integrated** | Official MLB Stats API. Verify currency at Phase 0. |
| ATP/WTA, cricket, UFC feeds | **skip** | No free Python feed with >50⭐ and active maintenance. Book-poll only for these sports. |

## Crypto spot price

| Repo | Status | Reason |
|---|---|---|
| [`sammchardy/python-binance`](https://github.com/sammchardy/python-binance) (7k⭐) | **integrated** | BTC/ETH spot. Kept in deps even though crypto_barrier is dropped — needed for any future salvage investigation and for future strategies. |
| [`ccxt/ccxt`](https://github.com/ccxt/ccxt) (42k⭐) | **skip** | Overkill for BTC/ETH-only. |

## Microstructure / wallet analysis

| Repo | Status | Reason |
|---|---|---|
| [`pselamy/polymarket-insider-tracker`](https://github.com/pselamy/polymarket-insider-tracker) (107⭐) | **future (v2)** | DBSCAN wallet clustering, first-N-seconds event windows. Standalone scanner (PG+Redis), not a library. Lift patterns if H1 wallet-diversity re-run confirms contested flow. |
| [`leolopez007/polymarket-trade-tracker`](https://github.com/leolopez007/polymarket-trade-tracker) (63⭐) | **skip** | Web tool, not library. |

## Market making / confirmation of kills

| Repo | Status | Reason |
|---|---|---|
| [`warproxxx/poly-maker`](https://github.com/warproxxx/poly-maker) (1k⭐) | **confirmed kill** | Author: "not profitable in today's market, will lose money." Independent confirmation of hourly-ladder MM thesis (e11) kill. |

## Adjacent / novel directions (separate future plans)

| Repo | Status | Reason |
|---|---|---|
| [`sstklen/trump-code`](https://github.com/sstklen/trump-code) (735⭐) | **future (separate)** | Polymarket↔Kalshi cross-platform arb + signal decoding. New edge direction, not e12. |
| Kalshi cross-venue validation | **skip for e12** | e13 Investigation 2c reviewed; default out of scope. Revisit only if sports_lag shows suspiciously strong edge suggesting Polymarket-specific quirk. |

## No suitable repo found

- **UMA oracle / dispute tracking (Python):** no library passes filter. Query UMA subgraph directly via GraphQL from Python. Dune dashboards exist (`primo_data/uma-voter-polymarket-disputes`) but require session/API key.
- **Async Polymarket client with backoff:** use `httpx + PyrateLimiter` (already in deps).
- **Polymarket-specific book archival:** Nautilus has `PolymarketDataLoader` but `/orderbook-history` broke 2026-02-20.

---

# Academic literature summary

From the three-agent research sweep. Used to validate/challenge the paper-trade thesis.

| Paper | Relevance | Key finding | Implication for e12 |
|---|---|---|---|
| **Della Vedova 2026** (SSRN 6191618) "Execution, not Information" | EXACT | 222M trades; bots pay 2.52¢ less per contract than casual traders. Execution skill drives PnL, not prediction. | **Supports the thesis.** No paper has isolated the specific post-resolution window; e12 fills that gap. |
| **Becker 2026** "Microstructure of Wealth Transfer" | PARTIAL | Takers −1.12% / Makers +1.12% excess return. Sports has one of the **smallest maker-taker gaps (2.23pp)** — closer to efficient than entertainment/world-events. | Caveat: sports is more efficient than other categories. Edge is real but thinner than e.g. Taylor Swift markets. |
| **Akey, Grégoire, Harvie, Martineau 2026** (SSRN 6443103) | PARTIAL | 1.4M users. **Top 1% = 84% of gains. Only market-making has predicted positive returns.** <30% of traders profitable. | Yellow flag: taker strategies underperform on average. sports_lag is technically a taker strategy. Sample our edge rigorously. |
| **Saguillo et al. 2508.03474** | PARTIAL | Arb duration collapsed 12.3s (2024) → **2.7s (2025)**. 73% of arb profits captured by sub-100ms bots. Mean arb value ~$40M/year. | Yellow flag. sports_lag 14.4 min window is 300× longer, currently insulated. Watch for compression during paper run. |
| **Le 2026** (arXiv 2602.19520) | TANGENTIAL | 292M trades. Domain-specific calibration dynamics. Polymarket closer to efficient at size. | Secondary — doesn't directly test our thesis. |
| **Anatomy of Polymarket 2024 Election** (2603.03136) | TANGENTIAL | Kyle's λ fell 10× as volume grew. | Confirms efficiency improving over time. |

---

# Net effect vs v2 of this plan (what changed and why)

## Removed
- `crypto_barrier` entirely (e13: -63% historical edge, n=5,220)
- 2 of 4 accounts (`crypto_barrier__fixed_100`, `crypto_barrier__depth_scaled`)
- Crypto-specific entry rules, spot-buffer check, resolution_spot tracking
- Nautilus fee cross-check (e13's on-chain fee truth obsoletes it)
- FEE_BPS = 100 placeholder

## Added
- `FEE_BPS = 0` default with Phase 0b zero-fee assertion
- Octagon risk gates: `MAX_DRAWDOWN_PER_CELL = 0.20`, `MAX_OPEN_PER_EVENT = 3`
- `event_id` column on position_context
- V2 cutover plan (pause/verify/resume on 2026-04-22)
- `polymarket-apis` gamma client as `gamma_client.py`
- Revised poll cadence: 20s → 2s (Gamma rate limits allow 400/s; Saguillo arb-compression makes speed matter)
- Academic-literature caveats (Saguillo compression, Akey taker warning) in Known Limitations
- Known operator wallets reference (LlamaEnjoyer et al.)

## Preserved
- Sports-result feeds (ESPN + nba_api + MLB-StatsAPI)
- Dual-path detection (feed + book-poll)
- Two size models (`fixed_100`, `depth_scaled`)
- Sample-size-driven run termination (50–100 trades)
- Time-weighted return reporting, `--fee-bps` re-scoreable
- Restart-safe SQLite persistence
- pm-trader as execution layer
