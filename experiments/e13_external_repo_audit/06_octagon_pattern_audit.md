# 06 — Octagon Kalshi CLI: pattern audit

Desk review of `OctagonAI/kalshi-trading-bot-cli` patterns against the e12 paper-trade plan. No code download required.

## What e12 currently has

- `ENTRY_TARGET_CAP = 0.97` — single hard cap on entry price
- Two `size_model` variants: `fixed_100`, `depth_scaled`
- `MAX_RUN_HOURS = 168` — wall clock kill
- `SAMPLE_TARGET_TRADES = 75` — sample-driven exit
- Per-account isolation (4 accounts) so failure modes don't cross-contaminate

That's it. No drawdown circuit breaker, no daily loss limit, no concentration cap, no position cap. The harness is essentially trusting the entry rule and seed-balance to bound the worst case.

## What Octagon adds

| Octagon gate | Default | What it protects against | Applies to e12 paper trade? |
|---|---|---|---|
| `risk.kelly_multiplier` | 0.5 | Over-sizing | Yes — sizing question |
| `risk.max_drawdown` | 0.20 | Catastrophic streak | Yes — paper PnL still informs go/no-go |
| `risk.max_positions` | 10 | Concurrent exposure blowout | Yes — capital tied up in `stuck` rows |
| `risk.max_per_category` | 3 | Correlated bets in same theme | Yes — multiple sports markets in a single event are correlated |
| `risk.daily_loss_limit` | $200 | Pathological misfire of detector | Yes |
| `octagon.daily_credit_ceiling` | 100 | API-cost runaway | N/A — we don't pay per detection |
| `alerts.min_edge` | 0.05 | Skip thin signals | Already implicit in `ENTRY_TARGET_CAP` |

## Recommendations to merge into e12

### 1. `max_drawdown` circuit breaker → ADD

If a `(strategy, size_model)` cell loses >20% of seed balance, **stop opening new positions in that cell** for the run. Existing positions resolve naturally. This is cheap (one `if` in the daemon) and gives us strategy-level safety so a misfire in one cell doesn't destroy the dataset for the others.

**Diff to e12 plan:**
```python
# config.py
MAX_DRAWDOWN_PER_CELL = 0.20  # stop opening new positions if cell PnL < -20% seed
```
```python
# daemon.py — inside the loop
if cell_drawdown(account) > MAX_DRAWDOWN_PER_CELL:
    log_skip("drawdown_breaker", account)
    continue
```

### 2. `max_per_category` cap → ADD (lightweight)

For sports especially: an MLB market often has 3-5 ladder markets per game. If we open positions on all of them simultaneously, we're correlated. Cap at 3 open positions per `event_id` per cell.

**Diff:**
```python
# detector.py
MAX_OPEN_PER_EVENT = 3
# ...
open_in_event = count_open_positions(account, c.event_id)
if open_in_event >= MAX_OPEN_PER_EVENT:
    skip("event_concentration_cap")
```

This requires storing `event_id` in the sidecar — a 1-column schema change.

### 3. `daily_loss_limit` → SKIP for v1

Paper trade is bounded by seed_balance per cell. The drawdown breaker (rec #1) already bounds tail risk per cell. Daily-loss is a real-money pattern; in paper-trade it adds noise to the data and we'd rather see the strategy run to natural completion.

### 4. Half-Kelly as a third `size_model` → ADD ONLY IF Investigation 1 confirms historical edge

Half-Kelly needs an edge estimate. The e12 plan doesn't compute one directly — `ENTRY_TARGET_CAP=0.97` implies "buy at ≤0.97, payoff is 1.0" → expected edge per share = `1.0 - entry_price`. Kelly fraction = `edge / (1 - entry_price) = 1.0` for a binary at certain payoff. Half-Kelly = 0.50 of available bankroll, which is wildly aggressive and not interesting as a third arm.

Half-Kelly is only meaningful if entry includes a probability-of-loss term. For sports_lag the assumed loss prob is ~0 (modulo disputes). For crypto_barrier it's the crash rate from Investigation 1. **Decision deferred** until Investigation 1 (specifically `04_sii_crypto_barrier_backtest.py`) reports a crash rate; if crash rate ≥ 5%, half-Kelly becomes genuinely useful for the crypto cell only.

### 5. Cross-venue Kalshi check → SKIP for v1

Kalshi has a real demo env. Running the same detector against Kalshi sports/crypto markets would give an independent venue read on whether the Polymarket lag arb is venue-specific. **Skip** unless Investigation 1 returns a suspiciously strong edge on Polymarket (say, net edge > 5% at realized fees) — that would suggest a Polymarket-specific quirk worth confirming on a second venue. Not in scope otherwise; adds a whole new SDK + auth layer.

### 6. JSON envelope + NDJSON streaming output → SKIP

Octagon's `--json` envelope is great for orchestration. e12's `report.py` is a one-shot CLI run by the user; no orchestration consumer. Add only if we end up wrapping the harness in another layer (we won't for v1).

## Net diff summary for e12

```
config.py:
  + MAX_DRAWDOWN_PER_CELL = 0.20
  + MAX_OPEN_PER_EVENT = 3

detector.py:
  + skip if count_open_positions(account, event_id) >= MAX_OPEN_PER_EVENT
  + skip if cell_drawdown(account) > MAX_DRAWDOWN_PER_CELL

schema.sql:
  + event_id TEXT  -- on position_context

daemon.py:
  + log "drawdown_breaker" / "event_concentration_cap" reasons in detections table
```

Total: ~30 lines, no architectural change.

## Pattern that's interesting but NOT for v1

Octagon's `analyze` command runs the LLM **before** every entry to produce an independent probability estimate, then computes edge as `model_prob - market_prob`. e12's strategies are model-free (the entry rule IS the signal). Adding LLM-in-the-loop for each detection would change e12 from a strategy validator into a strategy generator, which is a different project. Worth tracking as a v2 idea if v1 confirms either edge.

## Pattern that's actively WRONG for our case

Octagon defaults to **half-Kelly with a max_drawdown of 20%**. Half-Kelly compounded across many bets has theoretical positive expectation but a 50% chance of intermittent ≥40% drawdowns. For paper-trade *sample collection*, we don't want sizing variance dominating the results. Stick with `fixed_100` and `depth_scaled` for v1; Kelly waits until we have a believable edge estimate from Investigation 1.
