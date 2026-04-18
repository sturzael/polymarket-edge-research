# event-impact-mvp — documentation

**👉 Start with `WHAT_WORKS_ON_POLYMARKET_BARRIERS.md` — the synthesis of everything learned.**

**For a build-oriented plan, see `MASTER_PLAN.md`** (which the synthesis updates and partially supersedes).

What lives where:

- `/probe/` — 24-hour Polymarket reconnaissance probe (running). Answers "do short-duration crypto markets exist often enough?"
- `/experiments/` — one-off investigations that inform the v2 design. Each subdir has its own README + outputs.
- `/docs/FINDINGS.md` — chronological running log of everything learned, in order.
- `/docs/PLAN_HISTORY.md` — evolution of the plan across user course-corrections (context for why we pivoted twice).
- `/src/` — scaffolding for the (paused) main MVP. Currently only `prices.py` and `storage.py` landed; the rest of the MVP plan is on hold pending the probe + experiment outcomes.
- `/docs/MASTER_PLAN.md` — the unified plan consolidating all opportunities, evidence, build phases, and kill criteria.
- `/docs/OPPORTUNITY_SPORTS_EVENT_LAG_ARB.md` — alive, secondary diversifier (Phase 4).
- `/docs/OPPORTUNITY_HOURLY_LADDER_MM.md` — dead (kept for reference).
- `/docs/COUNTER_MEMO_MM_OPPORTUNITY.md` — methodology artifact.

## Experiment index

| # | Topic | Result | Status |
|---|---|---|---|
| e1 | Post-expiry price path | **16/20 snap within 30s.** Tradable window is pre-T, not post-T. | complete |
| e2 | Deribit IV snapshot | First snapshot captured; second scheduled ~24h later. | snapshot 1 complete |
| e3 | Cross-exchange lead-lag | **+100ms Binance→Coinbase lead detected.** Rig works. | smoke complete; 2h run pending |
| e4 | CLOB book depth | Mid-life books = 1¢/99¢ stubs. **Midpoint is fiction.** | partial |
| e5 | Historical backfill | CLOB retains resolution data per-cid. **No historical cid enumeration path.** | spike complete |
| e6 | Rate-limit discovery | Baseline latencies healthy (100-270ms). Ceiling untested. | partial |
| e7 | Resolution-source audit | **88% of crypto markets resolve against Chainlink Data Streams.** | complete |

See `FINDINGS.md` for the synthesized v2 design implications.

## Running the probe

```
cd ~/dev/event-impact-mvp
probe/status.sh                          # status snapshot
uv run python -m probe.report            # generate REPORT.md (works mid-run)
tail -f probe/probe.log                  # watch live
pkill -INT -f probe.main                 # stop cleanly
```

## Hard-won API gotchas (full detail in FINDINGS.md)

1. `gamma-api.polymarket.com/markets?condition_ids=X,Y` silently returns `[]`. Use **repeated** query params.
2. `gamma-api.polymarket.com/markets/<conditionId>` returns 422. Use `/markets?condition_ids=<cid>` instead.
3. `gamma-api` **drops past-expiry markets from listings** within seconds. Use CLOB for resolution detection.
4. `clob.polymarket.com/markets?condition_id=X` **silently ignores the filter** and returns the default page. Use `clob.polymarket.com/markets/<cid>` instead.
5. CLOB `tokens[].winner` is the authoritative resolution signal (not gamma's `outcomePrices`).
6. Real Polymarket resolution lag is ~400s (~6.6 min) past nominal 5m-market end. Not seconds.
7. For `*-updown-Nm-<ts>` markets, `endDate − startDate` gives the parent series duration, not the per-contract duration. Parse the slug regex for authoritative duration.
