# e15 — Neg-risk multi-leg arb paper-trade

**Status:** running. 36-hour data snapshot below (2026-04-19 03:31 UTC → 2026-04-20 22:37 UTC).

Supporting infra: 4 launchd agents documented in [docs/RUNBOOK.md](../../docs/RUNBOOK.md). Paper-trade operates at $500/position, was initially capped at 10 concurrent but raised to 200 on 2026-04-20 for "learning mode" — enter every qualifying opportunity regardless of concurrent-position count, then measure what the strategy class actually does.

## Early data (36 hours)

### Throughput

- **25 hourly ticks** completed on paper_trader; **35 scans** on arb_logger (logger started slightly earlier).
- Arb_logger avg **31.5 opportunities per scan** (15.5 GUARANTEED, 16.0 PROBABILISTIC). **Remarkably stable** — range 24-37 opps/scan, no decay observed. Consistent with Q3 finding that long-duration arbs persist 43h+ median.
- Paper_trader avg **3-4 qualifying per tick**. Most are already held (UNIQUE event_slug), so new entries are 0-2 per tick typically.

### Positions entered (n=14 over 36h)

| event | cost | entry edge | days to res |
|---|---:|---:|---:|
| colombia-presidential-election | $500.00 | +2.20% | 63.4 |
| nba-2025-26-sixth-man-of-the-year | $500.00 | +7.30% | 71.0 |
| english-premier-league-2nd-place | $98.30 | +1.70% | 37.4 |
| english-premier-league-last-place | $95.43 | +4.90% | 37.7 |
| next-james-bond-actor-635 | $93.09 | +2.30% | 71.6 |
| colorado-republican-senate-primary-winner | $49.50 | +1.20% | 71.7 |
| nba-2025-26-coach-of-the-year | $33.66 | +1.40% | 70.1 |
| iowa-democratic-senate-primary-winner | $27.69 | +1.10% | 42.1 |
| nba-rookie-of-the-year-873 | $16.39 | +3.00% | 28.7 |
| **nba-2025-26-defensive-player-of-the-year** | $11.90 | **+99.80%** | 70.1 |
| sper-lig-2025-26-champion | $10.77 | +5.20% | 34.5 |
| uefa-europa-league-winner | $6.04 | +2.30% | 34.7 |
| champions-league-top-scorer-655 | $2.75 | +4.40% | 40.7 |
| los-angeles-mayoral-election-117 | $2.65 | +1.30% | 42.1 |

Total deployed: $1,448. Max per position: $500 (cap). Median position size: ~$30 — most entries are depth-limited rather than budget-limited (book depth is the binding constraint).

### **Finding 1: Probable phantom entry at +99.8% edge**

The `nba-2025-26-defensive-player-of-the-year` entry at **+99.8% edge** is almost certainly a stale-quote phantom. That implies `sum_asks ≈ 0.002` at the time of scan — buying all legs for $0.002 total and getting $1 back per set. Real markets don't price that way. The $11.90 position size (depth-constrained) suggests the book showed only a tiny quantity at the phantom price.

**Expected outcome:** this position's realized payout will not match the paper-trade entry. Resolution at T+70 days will confirm. Until then: phantom_audit (weekly) will flag this when it re-queries the live book.

### **Finding 2: Edge inversion on tracked events (forward_trader signal)**

The `forward_trader` agent takes hourly snapshots of 6 hand-picked events. Over the first 23 hourly snapshots:

| event | edge mean | edge range | entered in paper-trader? |
|---|---:|---:|---|
| uefa-europa-league-winner | **+1.45%** | 0.0% to +3.0% | yes, at +2.3% |
| la-liga-winner-114 | -0.08% | -0.6% to +0.2% | no |
| fed-decision-in-april | -0.25% | -0.3% to -0.2% | no |
| colombia-presidential-election | **-1.85%** | -4.2% to +2.2% | yes, at +2.2% |
| nba-western-conference-champion-933 | -2.93% | -4.6% to -1.2% | no |
| nba-eastern-conference-champion-442 | **-3.46%** | -5.9% to +1.2% | no |

Two of the six events are transiently visiting positive edge and spending most of their time at clearly negative edge (`colombia` avg -1.85%, `nba-eastern` avg -3.46%). These are **phantom arbs masquerading as opportunities** — the gamma snapshot we query is stale relative to real-time market depth.

**Implication for paper-trader:** the `colombia` $500 position was entered during one of those transient +2.2% spikes. If the event resolves to a winner that's priced inside the basket (it should, colombia is GUARANTEED), PnL will be determined by actual resolution. But the entry was NOT at a real captured opportunity — if we'd tried to execute at that moment, slippage or ticker-update lag would likely have pushed us out.

This is the **silent-failure mode** from the postscript and project rule #5: "pattern exists historically ≠ pattern is capturable now." We're now measuring it live.

### Finding 3: Portfolio hit concurrent cap (pre-raise)

Before the `MAX_CONCURRENT` raise, the last 3 ticks showed `n_skipped_cap=5` — more qualifying arbs appearing than available slots. That's a capacity-limit artifact in our test harness, not the strategy. Raising to 200 removes the constraint and lets us observe actual opportunity-flow rate going forward.

## What we can't conclude yet

- **Realized PnL.** First resolution is NBA Rookie of the Year at T+28 days (~2026-05-18). Full basket resolves by ~2026-06-22 (colombia). Until then, any PnL claim is speculation.
- **Fraction of entered positions that are phantoms.** The 99.8% edge entry is an obvious one; the +2.2% ones are more subtle. Phantom_audit next Sunday will give us a first-pass estimate. Full clarity only after resolutions.
- **Whether opportunity flow sustains.** 36 hours is not enough to distinguish "stable" from "decaying but slowly." A 2-week window will.

## Decision gate (pre-committed)

Per [docs/RUNBOOK.md](../../docs/RUNBOOK.md):
- **Continue / deploy real capital:** `report --fee-bps 0` shows >$40/month net positive
- **Kill:** net ≤ $0 after fees, OR any TAIL outcome (GUARANTEED classified market resolves with no listed winner)
- **Extend observation:** ambiguous zone ($0-$40/month) → run another 30 days

Apply Rule 1 (÷5 haircut on estimates) and Rule 3 (measure raw before parameterized) at decision time.

## What to monitor

```bash
# positions + open deployed
uv run python -m experiments.e15_neg_risk_arb.paper_trader status

# realized PnL re-scored at fees
uv run python -m experiments.e15_neg_risk_arb.paper_trader report --fee-bps 0
uv run python -m experiments.e15_neg_risk_arb.paper_trader report --fee-bps 300

# tracked-event edge history
uv run python -m experiments.e15_neg_risk_arb.forward_trader status

# phantom audit (runs automatically Sundays 9am)
tail -100 experiments/e15_neg_risk_arb/logs/phantom_audit.log
```

## Operational state

4 launchd agents under `launchctl list | grep com.elliot.polymarket`:
- `com.elliot.polymarket-paper-trader` (PID varies, auto-restart)
- `com.elliot.polymarket-arb-logger`
- `com.elliot.polymarket-forward-trader`
- `com.elliot.polymarket-phantom-audit` (scheduled Sun 9am)

Plist sources in [~/.config/launchagents/](file:///Users/elliotsturzaker/.config/launchagents/) (git-tracked). Symlinked into `~/Library/LaunchAgents/`.
