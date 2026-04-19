# e12 — Paper-trade harness for sports settlement-lag arb

**Spec:** [`docs/PLAN_E12_PAPER_TRADE.md`](../../docs/PLAN_E12_PAPER_TRADE.md). This README is just the operational runbook.

## Run order (per the plan)

```
# Phase 0 — must pass before anything else
uv run python -m experiments.e12_paper_trade.shakedown

# Phase 1
uv run python -m experiments.e12_paper_trade.slug_audit
uv run python -m experiments.e12_paper_trade.pre_run --hours 1

# Run daemon (start NOW per the v3 plan; pause-resume around V2 cutover 2026-04-22)
uv run python -m experiments.e12_paper_trade.daemon

# Anytime: check status
uv run python -m experiments.e12_paper_trade.report
uv run python -m experiments.e12_paper_trade.report --fee-bps 100
uv run python -m experiments.e12_paper_trade.report --fee-bps 300
```

## Files

```
config.py            all economic assumptions parameterized
schema.sql           sidecar SQLite schema
http_client.py       shared httpx + pyrate-limiter
gamma_client.py      polymarket-apis PolymarketGammaClient wrapper
trader_client.py     pm-trader Engine wrapper, one Engine per cell
shakedown.py         Phase 0: pm-trader sanity + zero-fee assertion + V2 readiness
slug_audit.py        Phase 1a: validate sports slug patterns
pre_run.py           Phase 1b: 1-hour observe-only detection counter
sports_feeds.py      ESPN + nba_api + MLB-StatsAPI unified game-end stream
detector.py          dual-path entry detection (feed + book-poll)
risk.py              drawdown breaker + event concentration cap
daemon.py            main loop, restart-safe
missed_scanner.py    populates missed_opportunities table every 5 min
resolver.py          marks resolved positions; pulls disputes
report.py            per-cell stats; --fee-bps re-scoreable
v2_migration.py      pre/post 2026-04-22 cutover snapshot + verify
```

`cells/` contains one pm-trader sqlite DB per `(strategy × size_model × entry_cap)` cell. `sidecar.db` is our metadata. Both gitignored.

## V2 cutover (2026-04-22)

Daemon runs on V1 starting now. On 2026-04-22 ~09:30 UTC a cron-scheduled signal pauses the daemon. After V2 stabilizes (+24h+), run `v2_migration.py verify`; if clean, daemon resumes and tags subsequent positions `protocol_version='v2'`. See plan §"V2 cutover plan" for the full pre-commit (discard V2 if breaking semantics).

## Decision criterion

Pre-committed; do not modify mid-run. See plan §"Decision criterion" for the three-band rule + 20-trade early kill + missed-opportunity diagnostic.
