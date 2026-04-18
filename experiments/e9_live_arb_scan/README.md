# e9 — Live Arb Scan (recurring)

**Purpose:** Repeatedly measure executable resting arbs on Polymarket across crypto barrier, sports, politics, and entertainment markets. Each run appends one JSON line to `runs.jsonl`. Use to answer "is this opportunity persistent or episodic?"

## Key findings from initial runs (2026-04-18 ~05:40 UTC)

**Confirmed: live executable arbs exist RIGHT NOW on crypto barrier markets.**

| Category | n active | n certainty (last<0.05 or >0.95) | n executable arbs | total capturable <0.99 |
|---|---:|---:|---:|---:|
| Crypto barrier | 63 | 42 | **4** | **$18,280** |
| Sports | 180 | 3 | 2 | $1,098 |
| Politics | 0 | 0 | 0 | $0 |
| Entertainment | 1 | 0 | 0 | $0 |

Plus, broader non-crypto non-sports scan found 4 more arbs (weather markets in HK/Tokyo/Shanghai + Elon tweet counter).

### Top arbs right now

- **`bitcoin-above-76k-on-april-18`** (YES @ 0.968): $10,864 capturable under 0.99. BTC at $77,144 → 1.5% crash-risk gap for ~10h. Net EV after crash risk ~1% before fees.
- `ethereum-above-2500-on-april-18` (NO @ 0.975): $5,064 capturable
- `ethereum-above-2300-on-april-18` (YES @ 0.983): $2,278 capturable

### Dynamics on BTC-above-76k (3-min observation)

At steady state ~$11k of capturable depth under 0.99. In a 3-minute window, **someone took ~$6k of asks and new asks refilled to baseline**. So the arb is actively churning, not sitting idle.

### The filter that was wrong in earlier scans

Earlier "no arb found" scans used `last > 0.98` as the certainty threshold. This **excluded** markets in the 0.95-0.98 range which are exactly where the arb lives — markets that are nearly-certain but where the final few cents of mispricing haven't closed. The fix: use `last > 0.95` (or `< 0.05`) to catch the 95-99% certainty zone.

## How to run

Single run:
```
cd ~/dev/event-impact-mvp
uv run python experiments/e9_live_arb_scan/scan.py
```

Single category only:
```
uv run python experiments/e9_live_arb_scan/scan.py --categories crypto_barrier
```

Recurring 4h runs for 24h (runs in your shell, logs output):
```
for i in {1..6}; do
  uv run python experiments/e9_live_arb_scan/scan.py;
  sleep 14400;
done
```

Recurring with disown (background, survives terminal close):
```
nohup bash -c 'while true; do uv run python experiments/e9_live_arb_scan/scan.py; sleep 1800; done' > experiments/e9_live_arb_scan/recurring.log 2>&1 & disown
```

## Analysis of results

The JSONL log `runs.jsonl` accumulates one record per run. After 24h:
```
cd experiments/e9_live_arb_scan
uv run python - <<'PY'
import json
from pathlib import Path
runs = [json.loads(l) for l in Path('runs.jsonl').open()]
print(f'{len(runs)} runs captured')
for r in runs:
    cb = r['per_category']['crypto_barrier']
    print(f'{r[\"run_at\"][:19]}  crypto: {cb[\"n_executable_arbs\"]} arbs / ${cb[\"total_capture_below_0_99\"]:,.0f}')
PY
```

## Methodology notes

- Uses `last_trade_price < 0.05 OR > 0.95` to infer economic certainty
- Infers winner side: if last < 0.05 → NO winning; if last > 0.95 → YES winning
- Measures executable asks on winning side at prices < 0.99
- Does NOT account for:
  - Fees (unresolved — need $10 live test)
  - Latency from our location (unresolved)
  - Cross-bot competition (we'd be fighting for fills)
  - Small probability of outcome actually flipping (crash risk on crypto barriers)

Apply ÷5 rule on any monthly estimate derived from these numbers.

## Open questions these runs should answer

1. **Persistence**: Does every run find 3-5 executable arbs, or do they come and go?
2. **Refresh rate**: How fast does a market's arb depth regenerate after being taken?
3. **Time-of-day patterns**: US market hours vs Asian vs overnight?
4. **Fresh-vs-old markets**: Do arbs concentrate on newly-listed (< 4h old) or aged (> 12h old) markets?
