# Runbook — what's running and how to revive it

**Last updated:** 2026-04-20. **Purpose:** 30-day paper-trade experiment to empirically measure neg-risk arb PnL + tracked events' edge persistence, then evaluate whether a directional strategy (calibration bias) is worth deploying capital on.

**Companion findings docs:**
- [e15 paper-trade findings (36h snapshot)](../experiments/e15_neg_risk_arb/FINDINGS.md)
- [e16 calibration study (sports favorite-longshot bias)](../experiments/e16_calibration_study/FINDINGS.md)

## Architecture (after 2026-04-19 launchd migration)

Four launchd agents — hourly loops for the 3 collectors + weekly audit. Plists are git-tracked in `~/.config/launchagents/` (your `.config` repo) and symlinked into `~/Library/LaunchAgents/`. `KeepAlive=true` auto-restarts on crash; `RunAtLoad=true` starts at login; `ThrottleInterval=60` prevents crash-loop spam.

| launchd label | Module | What it does | DB | Log |
|---|---|---|---|---|
| `com.elliot.polymarket-paper-trader` | [paper_trader.py](../experiments/e15_neg_risk_arb/paper_trader.py) | Auto-enters GUARANTEED arbs ≥1% edge at $500/position, **up to 200 concurrent** (raised from 10 on 2026-04-20 for learning-mode; enters every qualifying opportunity). Resolves at event close. | `data/paper_trader.db` | `logs/paper_trader.log` |
| `com.elliot.polymarket-arb-logger` | [logger.py](../experiments/e15_neg_risk_arb/logger.py) | Records every opportunity every scan (census data — frequency, persistence, shape). | `data/arb_log.db` | `logs/logger.log` |
| `com.elliot.polymarket-forward-trader` | [forward_trader.py](../experiments/e15_neg_risk_arb/forward_trader.py) | Hourly snapshots of 6 hand-picked events. | `data/forward_trader.db` | `logs/forward_trader.log` |
| `com.elliot.polymarket-phantom-audit` | [audit_open_positions.sh](../experiments/e15_neg_risk_arb/audit_open_positions.sh) | **Weekly (Sundays 9am local)**. Runs phantom_check on every open position — verifies paper-fill depth was real, not gamma cache. | — | `logs/phantom_audit.log` |
| `com.elliot.polymarket-arb-observer` | [observer.py](../experiments/e17_realtime_arb_observer/observer.py) | **Real-time WebSocket subscriber.** Subscribes to every active GUARANTEED neg-risk event's YES tokens, maintains in-memory orderbook state, detects sum_asks<1.0 moments with ms-level timing. Answers: how fast do arbs die, are they captureable? | `e17_realtime_arb_observer/data/observer.db` | `e17_realtime_arb_observer/data/observer.log` |
| `com.elliot.polymarket-calibration-fwd` | [forward_validator.py](../experiments/e16_calibration_study/forward_validator.py) | **Hourly snapshots of active sports markets 6.5-7.5 days from resolution.** Forward-validates the e16 T-7d favorite-longshot bias (peak +25.8pp at 0.55-0.60 bucket). Wait ~30 days → compare forward yes_rate to historical. | `e16_calibration_study/data/forward_validator.db` | `e16_calibration_study/data/forward_validator.log` |

Paths in this table are relative to `experiments/e15_neg_risk_arb/`.

## Status bar (SketchyBar)

A `polymarket` pill lives in the top bar showing open positions, deployed capital, realized PnL, and age of last paper-trader tick. Colored green < 90m stale, yellow < 180m, red ≥ 180m (daemon probably dead).

- Plugin: [~/.config/sketchybar/plugins/polymarket.sh](file:///Users/elliotsturzaker/.config/sketchybar/plugins/polymarket.sh)
- Registered in [sketchybarrc](file:///Users/elliotsturzaker/.config/sketchybar/sketchybarrc) — `update_freq=300`
- Clicking the pill opens a terminal at the repo root.
- **If sketchybar isn't running**: `brew services start sketchybar`

## Quick commands

```bash
# Are the agents alive?
launchctl list | grep com.elliot.polymarket

# Per-agent (shows last exit, env, etc.)
launchctl print gui/$UID/com.elliot.polymarket-paper-trader

# Tail logs live
tail -f experiments/e15_neg_risk_arb/logs/paper_trader.log
tail -f experiments/e15_neg_risk_arb/logs/logger.log
tail -f experiments/e15_neg_risk_arb/logs/forward_trader.log
tail -f experiments/e15_neg_risk_arb/logs/phantom_audit.log

# Paper-trader state (open + closed positions + PnL)
uv run python -m experiments.e15_neg_risk_arb.paper_trader status

# Re-score PnL under a fee assumption (Polymarket fee = sets × feeRate × p × (1-p) per leg)
uv run python -m experiments.e15_neg_risk_arb.paper_trader report --fee-bps 0
uv run python -m experiments.e15_neg_risk_arb.paper_trader report --fee-bps 300
uv run python -m experiments.e15_neg_risk_arb.paper_trader report --fee-bps 720

# Forward-trader snapshot history + resolutions
uv run python -m experiments.e15_neg_risk_arb.forward_trader status

# Run the phantom audit on-demand
experiments/e15_neg_risk_arb/audit_open_positions.sh && \
    tail -100 experiments/e15_neg_risk_arb/logs/phantom_audit.log

# Observer status (Phase 2 of PLAN_FAST_BOT)
sqlite3 experiments/e17_realtime_arb_observer/data/observer.db \
    "SELECT COUNT(*) total_arbs, SUM(phantom) phantom_arbs,
            ROUND(AVG(duration_ms)) avg_ms_live,
            MAX(duration_ms) max_ms FROM arbs WHERE ended_at IS NOT NULL;"

# Calibration-fwd status + early analysis
uv run python -m experiments.e16_calibration_study.forward_validator status
uv run python -m experiments.e16_calibration_study.forward_validator analyze
```

## Lifecycle commands

```bash
# Stop one agent
launchctl bootout gui/$UID /Users/elliotsturzaker/Library/LaunchAgents/com.elliot.polymarket-paper-trader.plist

# Start it back
launchctl bootstrap gui/$UID /Users/elliotsturzaker/Library/LaunchAgents/com.elliot.polymarket-paper-trader.plist

# Stop ALL four
for n in paper-trader arb-logger forward-trader phantom-audit; do
    launchctl bootout gui/$UID "$HOME/Library/LaunchAgents/com.elliot.polymarket-$n.plist" 2>/dev/null
done

# Start ALL four
for n in paper-trader arb-logger forward-trader phantom-audit; do
    launchctl bootstrap gui/$UID "$HOME/Library/LaunchAgents/com.elliot.polymarket-$n.plist"
done
```

## Install from scratch (new machine)

```bash
# Prereqs on the new machine:
#   - cloned the event-impact-mvp repo at /Users/elliotsturzaker/dev/event-impact-mvp
#   - cloned the .config repo at /Users/elliotsturzaker/.config
#   - uv installed at /Users/elliotsturzaker/.local/bin/uv
#   - run `uv sync` in the repo

# 1. Symlink the four plists into LaunchAgents
for n in paper-trader arb-logger forward-trader phantom-audit; do
    ln -sfn "$HOME/.config/launchagents/com.elliot.polymarket-$n.plist" \
            "$HOME/Library/LaunchAgents/com.elliot.polymarket-$n.plist"
done

# 2. Bootstrap (load) each
for n in paper-trader arb-logger forward-trader phantom-audit; do
    launchctl bootstrap gui/$UID "$HOME/Library/LaunchAgents/com.elliot.polymarket-$n.plist"
done

# 3. Confirm
launchctl list | grep com.elliot.polymarket

# 4. Reload sketchybar so the polymarket pill appears
brew services restart sketchybar
```

All four are restart-safe — they append to their SQLite DBs and don't re-enter positions already recorded. Gaps only lose data from the gap window.

## Known limitations

- **Laptop sleep pauses everything.** Launchd resumes the agents when the laptop wakes, but ticks missed during sleep are permanently lost. If you need continuous coverage, either `caffeinate -dims &` in a terminal (prevents sleep), or move to VPS.
- **Neg-risk arb opportunities are sparse.** Expect thin sample; Rule 4 (sample size drives window) means ≥30 days runtime + ≥28 days for first resolution before PnL is interpretable.
- **V2 cutover 2026-04-22.** All four agents are READ-only (gamma `/events`, CLOB `/book`) — order-struct changes do not affect them. Their try/except keeps the loop alive across transient API errors. Tail logs on 2026-04-22 for unusual error rates; no pause action required.

## Timeline: when we see realized PnL

First open positions entered 2026-04-19. Realized PnL crystallizes at event resolution:

| position | size | resolves | approx date |
|---|---|---|---|
| NBA Rookie of the Year | $16 | +28.7d | ~2026-05-18 |
| UEFA Europa League Winner | $6 | +34.7d | ~2026-05-24 |
| English Premier League Last Place | $95 | +37.7d | ~2026-05-27 |
| Colombia Presidential Election | $500 | +63.4d | ~2026-06-22 |

**First realized PnL: 2026-05-18** (smallest position). **Full basket resolved: ~2026-06-22.** Use the interim to track leading indicators (entry frequency, edge persistence in forward_trader snapshots, phantom_audit output).

## Decision gate (30 days + first resolution)

Apply Rule 1 (÷5 on estimates) and Rule 3 (raw before parameterized) from [PROJECT_POSTSCRIPT.md](PROJECT_POSTSCRIPT.md):

- **Continue / deploy real capital:** `report --fee-bps 0` shows >$40/month net positive (extrapolates to ~$500/yr floor; ÷5 haircut leaves $100 — still barely viable on $5k)
- **Kill:** net ≤ $0 after fees, OR any TAIL outcome (GUARANTEED should never tail — would indicate classification bug)
- **Extend observation:** ambiguous zone ($0-$40/month) → run another 30 days before spending on VPS

## Emergency fallback (launchd unavailable)

If launchd is the problem and you need to run via `nohup` temporarily:

```bash
cd /Users/elliotsturzaker/dev/event-impact-mvp
PYTHONUNBUFFERED=1 nohup uv run python -m experiments.e15_neg_risk_arb.paper_trader loop --interval-min 60 > experiments/e15_neg_risk_arb/logs/paper_trader.log 2>&1 &
disown
# repeat for logger + forward_trader
```

## File map (research instruments + their purpose)

| Path | Purpose |
|---|---|
| [experiments/e15_neg_risk_arb/scanner.py](../experiments/e15_neg_risk_arb/scanner.py) | One-shot arb finder with GUARANTEED/PROBABILISTIC classification |
| [experiments/e15_neg_risk_arb/paper_trader.py](../experiments/e15_neg_risk_arb/paper_trader.py) | Scanner-driven $5k paper-trade engine |
| [experiments/e15_neg_risk_arb/logger.py](../experiments/e15_neg_risk_arb/logger.py) | Hourly census of all opportunities to SQLite |
| [experiments/e15_neg_risk_arb/forward_trader.py](../experiments/e15_neg_risk_arb/forward_trader.py) | Narrow tracker for 6 hand-picked events |
| [experiments/e15_neg_risk_arb/phantom_check.py](../experiments/e15_neg_risk_arb/phantom_check.py) | Verify depth is real (gamma may cache; CLOB is truth) |
| [experiments/e15_neg_risk_arb/audit_open_positions.sh](../experiments/e15_neg_risk_arb/audit_open_positions.sh) | Weekly wrapper: runs phantom_check on every open position |
| [experiments/e15_neg_risk_arb/retrospective.py](../experiments/e15_neg_risk_arb/retrospective.py) | Historical Q1 analysis (LISTED vs TAIL outcomes) |
| [experiments/e15_neg_risk_arb/q2_persistence.py](../experiments/e15_neg_risk_arb/q2_persistence.py) | Historical Q2 analysis (arb window duration) |
| [experiments/e15_neg_risk_arb/q3_long_duration.py](../experiments/e15_neg_risk_arb/q3_long_duration.py) | Historical Q3 analysis (long-duration arbs) |
