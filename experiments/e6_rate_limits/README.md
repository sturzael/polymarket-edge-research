# e6 — Rate-limit and latency baseline

**Question:** What are gamma-api / CLOB / data-api rate limits? What's the latency baseline for our collector?

**Status:** Partial. Baseline latencies captured with sequential 1-req/sec sampling. Aggressive burst testing (the bit that would reveal the actual rate-limit ceiling) was blocked by the sandbox as potentially abusive — reasonable caution while the probe is running. Needs a follow-up pass with explicit user sign-off to measure the ceiling.

## Baseline latency (sequential 1 req/s, 10 samples each)

| Endpoint | Statuses | Mean | p90 |
|---|---|---:|---:|
| `gamma-api.polymarket.com/markets?limit=1` | all 200 | 121 ms | 91 ms |
| `clob.polymarket.com/markets` (paginated listing) | all 200 | 267 ms | 417 ms |
| `clob.polymarket.com/markets/<live cid>` | 200 | ~150 ms (from probe runs) | — |
| `data-api.polymarket.com/trades?limit=1` | all 200 | 100 ms | 87 ms |

Zero 429s, no throttling observed at this rate.

## Implied budget for the probe

At current probe cadence:
- Discovery: 15 pages × gamma × every 45s = 0.33 req/s to gamma
- Normal sampler: 1 bulk call × every 15s = 0.07 req/s to gamma
- Final sampler: 1 bulk call × every 5s = 0.2 req/s to gamma
- Resolution checker: up to 30 CLOB calls × every 10s = ~3 req/s to CLOB

Well below conservative limits. If we assume 10 req/s as a safe budget per endpoint, we have 30x+ headroom.

## What we don't know

- The actual rate-limit ceiling (where 429s begin)
- Whether `Retry-After` header is set
- Whether limits are per-IP, per-User-Agent, or global

## Follow-up

Re-run with escalating concurrent bursts (5/s → 10/s → 20/s → 50/s → 100/s) after the probe finishes, so a temporary ban would not disrupt data collection. Requires explicit user approval.

## Status

Baseline captured. Ceiling unknown.
