# Fast-bot plan of attack — from paper-trade to executable arb capture

**Date:** 2026-04-21. **Author:** AI-assisted. **Status:** Phase 1 complete. Phase 2+ proposed.

## Honest competitive read (read this first)

Polymarket neg-risk arbs exist at a range of edge sizes and time windows:

| edge size | typical duration | who captures |
|---|---|---|
| >50% (phantoms / placeholder baskets / new-market seeding) | <100ms | colocated bots in AWS us-east-1, running Rust/Go, dedicated hardware. **Not you.** |
| 5-50% | 1-30s | professional MM firms with latency-optimized stacks. **Possibly you if VPS + WebSocket.** |
| 1-5% | minutes to hours | solo operators with basket-execute logic. **You, if infrastructure is built.** |
| <1% | hours to days (Q3 long-duration) | anyone paying attention. **You, even on laptop — but edge is thin.** |

The +99.8% nba-dpoy we saw was in bucket 1 — never ours. Our realistic targets are buckets 3 and 4 (1-5% edges that persist seconds-to-minutes, plus the long-tail Q3 arbs).

**Yield expectation:** LlamaEnjoyer's public record is $4.2M across 10,200 bets / 12 months, operating at 0.99-entry with $34-151k positions. That's pro-grade. A solo VPS bot at $1-5k bankroll capturing 1-5% edges probably yields **$500-3000/year**. Not life-changing, real money, worth building if the infrastructure takes weeks not months.

## Phase 1 — fix phantom inflation (DONE, 2026-04-21)

### 1a. Widen placeholder slug detection ✅

`scanner.py` now flags `player-N`, `option-N`, `candidate-N`, `other-N` as placeholders via regex. Events with any of these get classified PROBABILISTIC (paper_trader skips).

Root cause: `nba-2025-26-defensive-player-of-the-year` had 11 child markets named `player-0` through `player-10` that my original `PLACEHOLDER_SLUGS = ("will-option-", "will-other-")` list missed. Scanner classified the event GUARANTEED; paper_trader entered at +99.8% edge against fake depth; phantom "resolved" with $5,940 paper PnL.

### 1b. Pre-entry phantom filter ✅

`paper_trader.py` now rejects any qualifying opportunity with `sum_asks < 0.05`. No real orderbook prices a basket at ≥95% edge stably — that's always stale-cache or placeholder-basket artifact.

### 1c. Backfill flag ✅

Existing phantom position #11 (`nba-dpoy`) is tagged `PHANTOM: sum_asks<0.05, paper PnL unreliable` in closures.notes. Paper PnL reports can exclude phantom-flagged rows.

### 1d. Restart ✅

paper_trader PID 38857, running with patches.

## Phase 2 — WebSocket observer (no trading, just latency measurement) [next, 1-2 days]

Before spending on VPS or execution infra, measure whether we can even SEE arbs fast enough. Polymarket has a public WebSocket at `wss://ws-subscriptions-clob.polymarket.com/ws/market` that streams orderbook deltas. Subscribe to the asset_ids of every active GUARANTEED neg-risk event's children, maintain in-memory book state, compute sum_asks on every tick.

**New module:** `experiments/e17_realtime_arb_observer/`

Goals:
1. **Latency profile** — from first tick showing sum_asks<1.0 to 2.7s later (Saguillo's arb-death-time), how many are still live? What's the median duration?
2. **Arb quality distribution** — of arbs we detect, what fraction are phantoms (sum_asks<0.05)? What fraction are real but transient (<1s)? What fraction are Q3-style long-duration (>1h)?
3. **Geographic latency** — run the observer on NZ laptop first, then VPS. Same WebSocket subscription. Measure which tick one receives first.

Deliverables:
- `observer.py` — asyncio + websockets + py-clob-client
- `data/observer_events.jsonl` — every detected arb with full timing
- `FINDINGS.md` — what fraction of arbs are capturable at each latency tier

Estimated code: ~300 lines Python. No capital at risk.

**Kill criterion:** if NZ-laptop observer shows 99% of arbs die within 200ms of first tick (i.e. they're all captured by fastest bots instantly), drop to Phase 4 scoped to Q3 long-duration arbs only. If NZ observer catches arbs lasting >10s regularly, VPS is a clear next step.

## Phase 3 — VPS deployment comparison [1 day, ~$6]

Provision Hetzner CX21 or DigitalOcean basic droplet in us-east (NYC3 or FRA depending on Polymarket infra). Deploy Phase 2 observer. Run both NZ laptop and VPS in parallel for 48 hours.

Measure:
- Time-to-first-tick delta (NZ vs VPS)
- Number of arbs observed in the "capturable" latency window on VPS but not NZ
- Cost of VPS per captured observable arb (even without execution)

Deliverables: `VPS_LATENCY_REPORT.md`, go/no-go on execution infra.

**Cost:** ~$6/mo, ~$12 for 60-day test.

## Phase 4 — execution infrastructure [1-2 weeks, code only]

If Phase 3 says VPS is worth it, build execution:

### 4a. Basket-execute logic
- `py-clob-client` for signed order submission
- On arb detection: fire all N legs as IOC (immediate-or-cancel) orders in parallel via `/orders/batch` (up to 15 per call, fine for ≤15-leg events)
- Track fills via WebSocket user-data subscription
- Handle partial fills: close residuals via `splitPosition` / `mergePositions` if possible, or accept small residuals as controlled P&L risk

### 4b. Capital + safety
- Dedicated wallet, funded with $500-1000 USDC initially
- Per-arb cap: $50-100 position size while proving out
- Daily loss limit: $50 (auto-halt)
- Global kill switch: stop all execution via launchd signal

### 4c. Monitoring
- SQLite log of every attempted execution (intent, fills, residuals, final PnL)
- Grafana/Prometheus dashboard or simpler daily email summary
- Integration with existing sketchybar pill to show live P&L

**This phase is paper-only first.** We compute what we WOULD have filled and print the decision, without actually placing orders. Only flip to live after 1-2 weeks of shadow-paper shows realistic fill rates.

## Phase 5 — live with tiny capital [ongoing, capped]

Start at $500 wallet, $50/position, max $100 daily. Run for 30 days. Measure realized (not paper) PnL after fees, slippage, residual losses.

Graduation criteria:
- ≥$30 net realized/month → scale to $2k wallet, $200/position
- ≥$100 net realized/month → scale to $5k wallet, $500/position
- Negative or zero → kill the strategy, postscript rule 3 (raw measurements don't lie)

## What the research DID buy us

Not nothing — the e15 paper-trade + e16 calibration gave us:

| asset | value |
|---|---|
| **Classification taxonomy** (GUARANTEED/PROBABILISTIC, placeholder detection) | Prevents entering phantom basket-arbs |
| **Arb-frequency data** | Know what hourly scan returns: ~15-20 GUARANTEED arbs/scan |
| **Q3 long-duration findings** | Know that ~2.2% of resolved events have 24h+ arbs — different strategy class, less latency-sensitive |
| **Paper-trade harness** | Can shadow any execution logic before going live |
| **Sports calibration bias** (e16) | Entirely separate strategy — doesn't need low latency, 20pp edges, 7-day holds |

Without this research, we'd be guessing. With it, we have a specific menu of strategy classes, each with known frequencies and edge distributions.

## What the research DIDN'T guarantee

- That our bot beats bots that have been doing this for years.
- That 1-5% edge arbs are still tradeable in 2026 (may have been arbed tighter since Saguillo 2025).
- That Polymarket's `/orders/batch` works reliably for atomic-like basket fills.
- That slippage doesn't eat the 1-5% edge down to zero on our position sizes.

Phase 2 answers the first one empirically. Phases 3-5 answer the rest.

## Decision points

| decision | data needed | when |
|---|---|---|
| Build Phase 2 observer? | — | now, yes — cheap, high-info |
| Provision VPS? | Phase 2 NZ-laptop results | Day 3-5 |
| Build execution infra (Phase 4)? | Phase 3 VPS latency results | Day 8-14 |
| Deploy real capital (Phase 5)? | Phase 4 shadow-paper results after 1-2 weeks | Day 21-28 |

Each phase has an explicit kill criterion. No more than $20 of hard money spent before Day 21, and even then only on VPS + micro-capital tests.

## One alternative to consider before building the bot

The **sports calibration strategy from e16** has:
- 25.8pp edge at peak bucket (vs 1-5% for neg-risk arbs)
- 7-day hold (so latency is irrelevant — can trade from laptop)
- No basket execution needed (single market at a time)
- Forward validation recipe ready (~2hrs build + 30 days observe)

If the goal is "extract edge from Polymarket with our bankroll," the calibration strategy is structurally simpler AND has a larger edge AND needs no VPS. The fast-bot strategy is a 5-phase 1-2 month build; calibration validation is a ~30 day wait.

Honest recommendation: **run both in parallel**. Phase 2 observer costs nothing and buys us information. Calibration forward-validation is passive observation. Neither commits capital until week 4+. First to produce signal wins our capital allocation.
