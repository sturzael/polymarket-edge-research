# e13 — External repo audit (discovery only)

**Time-box: 2 days. Hard cap.** No edits to `experiments/e12_paper_trade/` or `~/.claude/plans/is-there-anythign-in-bright-cook.md` from this experiment. Output is `findings.md` with concrete numbers and Y/N recommendations the user merges by hand.

## What this is

Four external repos surfaced as candidates to harden the surviving sports-lag and crypto-barrier theses:

1. **SII-WANGZJ/Polymarket_data** — 107GB / 1.1B trade records on HF, with on-chain `maker_fee` / `taker_fee` / `protocol_fee`. Could answer H3 (fee gate) and re-derive H1 (wallet diversity) at full-history scale, plus support a real backtest of both surviving theses before paper-trading.
2. **OctagonAI/kalshi-trading-bot-cli** — 5-gate risk engine, half-Kelly sizing, daily-loss-limit. Patterns the e12 plan is missing.
3. **`polymarket-apis`** (PyPI) — Pydantic-typed Polymarket clients. Possibly nicer than hand-rolled aiohttp.
4. **harish-garg/Awesome-Polymarket-Tools**, **mvanhorn/last30days-skill** — index / unrelated.

## Run order

```
uv add huggingface_hub pyarrow polymarket-apis
uv run python experiments/e13_external_repo_audit/01_sii_dataset_probe.py
# If 01 fails its kill criteria → skip 02-05, go straight to findings.
uv run python experiments/e13_external_repo_audit/02_sii_fee_realization.py
uv run python experiments/e13_external_repo_audit/03_sii_sports_lag_backtest.py
uv run python experiments/e13_external_repo_audit/04_sii_crypto_barrier_backtest.py
uv run python experiments/e13_external_repo_audit/05_sii_wallet_diversity.py
uv run python experiments/e13_external_repo_audit/07_polymarket_apis_eval.py
# 06 is desk research only — already written.
```

Each probe is independent; a failure in one doesn't block the others.

## Storage caution

The full SII dataset is 107GB. Don't `hf download` the whole thing. The probes:
- Pull `markets.parquet` (68MB — the only full file we cache)
- Use `pyarrow.dataset` over the `HfFileSystem` for everything else, reading row-group filtered slices into memory without persisting to disk

`data/` is gitignored. If you re-run after deleting it, only `markets.parquet` re-downloads.

## What it produces

`findings.md` — final decision log with:
- Concrete numbers from each probe (median realized fee, historical net edge per strategy, top-10 wallet share, etc.)
- Y/N recommendations to merge into the e12 plan
- Failure flags + what's blocked

Then stop. The user decides what changes go into `is-there-anythign-in-bright-cook.md`.
