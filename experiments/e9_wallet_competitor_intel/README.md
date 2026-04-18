# e9 — Polymarket barrier-market wallet competitor intel

**Question:** who are the top wallets trading Polymarket crypto-barrier markets ("will BTC reach $X", "will SOL dip to $X") — and are they also active on the rest of Polymarket (updown-5m, sports, politics)?

**Scope:** the 40 barrier markets already tracked in `probe/probe.db` (all April 17 cohort). 100% Polymarket data-api — no on-chain, no keys, no permissions.

## Run

```sh
uv run python experiments/e9_wallet_competitor_intel/fetch.py
uv run python experiments/e9_wallet_competitor_intel/analyze.py
```

Outputs land in `./data/` (git-ignored):
- `barrier_trades.jsonl` — raw per-market trades
- `barrier_wallet_aggregate.csv` — per-wallet roll-up
- `top_wallet_history.jsonl` — cross-market trade history for top-20 wallets
- `top_wallet_positions.jsonl` — realized/unrealized P&L for same

Findings written to `./REPORT.md`.

## Follow-ups (out of this pass)

- Polygonscan enrichment via `transactionHash` (funding-source clustering, off-Polymarket activity).
- Historical barrier markets beyond the probe's April-17 snapshot.
- Price-vs-fair edge analysis (did top wallets actually buy cheap, or just move size?).
