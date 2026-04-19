# Two Days Hunting for Edge on Polymarket

A structured research project investigating whether a solo operator could find tradeable edge on Polymarket using an LLM-assisted research workflow (Claude Code + conversational review).

**TL;DR — project closed 2026-04-19.** Ten thesis classes investigated. All ten dead at $1k-bankroll laptop scale. Sports settlement-lag arb's +3.99% historical edge did not survive contact with live market reality (the 0.95-0.97 entry zone is empty in real time; only futures populate it). Negative-risk multi-leg arb was the late-stage candidate; Q3 retrospective showed 2.2% frequency × 5% edge × $19k median depth = ~$400-900/year best case at $1k bankroll, eaten by execution risk. The empirical record is consistent: **a $1k laptop operator from NZ cannot extract systematic edge from Polymarket using any strategy class we identified.**

The durable output is methodological (six falsification rules) and instrumental (paper-trade harness, retrospective analysis framework, neg-risk arb scanner). At higher capital ($10k+) or with VPS/atomic-multi-leg infrastructure, the conclusion changes; specific reopen conditions are documented.

👉 **[Read the project postscript](docs/PROJECT_POSTSCRIPT.md)** — final synthesis, what was tested, why each strategy died, what survives as durable tooling, conditions for reopening.

For the original synthesis (pre-postscript), see [`SYNTHESIS.md`](SYNTHESIS.md). The paper-trade harness plan and earlier portfolio plan are preserved at [`docs/PLAN_E12_PAPER_TRADE.md`](docs/PLAN_E12_PAPER_TRADE.md) and [`docs/PLAN_E14_PORTFOLIO_BUILDOUT.md`](docs/PLAN_E14_PORTFOLIO_BUILDOUT.md).

## Repository structure

- [`docs/PROJECT_POSTSCRIPT.md`](docs/PROJECT_POSTSCRIPT.md) — final endpoint; start here
- [`SYNTHESIS.md`](SYNTHESIS.md) — pre-postscript synthesis (still useful for methodology + microstructure findings)
- [`docs/`](docs/) — chronological findings, plan history, individual opportunity writeups, counter-memos
- [`probe/`](probe/) — 24h Polymarket market-structure reconnaissance probe
- [`experiments/e1`](experiments/e1_post_expiry_paths/) – [`e15`](experiments/e15_neg_risk_arb/) — individual thesis investigations
- [`src/`](src/) — scaffolding from an earlier plan iteration (not used in final synthesis)

Raw data artifacts (SQLite DBs, trade-history JSONL) are gitignored for size and privacy reasons. All code is included and the data is regenerable by re-running the collectors.

## Hard-won API gotchas

Saved here because they cost real debugging time and aren't documented anywhere else:

- **gamma-api silently drops past-expiry markets from listings.** Use CLOB for resolution detection.
- **gamma-api's `condition_ids` filter requires repeated query params, not comma-separated.** With `aiohttp`, pass a list of `("condition_ids", cid)` tuples.
- **CLOB's `/markets?condition_id=X` silently ignores the filter** and returns unfiltered results. Use `/markets/<cid>` (singular path) instead.
- **CLOB's `/book` endpoint returns bids sorted ascending (lowest first).** `bids[0]` is the WORST bid, not the best. Use `max(float(l["price"]) for l in bids)` for best bid.
- **Polymarket resolution lag averages ~400 seconds past nominal expiry**, not seconds. Budget accordingly.
- **For `*-updown-*m-*` markets, `endDate − startDate` gives the parent series duration**, not the per-contract duration. Parse the slug regex for authoritative duration.
- **Polymarket fee formula is `shares × feeRate × p × (1−p)`**, a symmetric curve peaking at p=0.5. Not `min(p, 1−p)`. Per-market rate via `getClobMarketInfo(conditionID).info.fd.r`. Published taker rates (Crypto 7.2 bps, Sports 3 bps) may be ceilings or legacy — on-chain sports taker fees measured zero in a 143-trade sample. Verify empirically.
- **Gamma rate limits are documented at 4000/10s general, 300/10s on `/markets`, 500/10s on `/events`.** Guessing conservative rates is unnecessary.
- **CLOB priority is price-time, not pro-rata.** Cancel-before-match latency is NOT publicly documented — treat as empirical unknown.
- **UMA resolution: 2h liveness, $750 pUSD bond per side.** Sports auto-proposer posts within minutes of game end → ~2–2.5h total to settlement undisputed. Dispute rate platform-wide ~2%, sports <0.5% post-MOOV2.
- **🚨 CTF Exchange + CLOB V2 cutover: 2026-04-22.** No V1 backward compat. Order struct changes; any harness built against V1 order format breaks.

Any future researcher in this space starts several days ahead by knowing these.

## Methodology rules that earned their keep

Two rules accumulated during the project and proved load-bearing. Apply to any speculative-opportunity research, not just this domain.

**Rule 1 — Divide monthly revenue estimates by 5 before acting on them.** Initial estimates in this project were systematically 3–10× too high across every thesis. Applying ÷5 produced numbers that subsequent analysis validated as roughly correct.

**Rule 2 — Write the counter-memo from the same data.** Before acting on a "this works" finding, write the companion "here's why this doesn't work" memo using the same dataset. Identifies silent-failure modes — ways the strategy generates ≤$0 without a loud signal anything's wrong. Killed two theses in this project.

**Rule 3 (added late-project) — Measure raw before parameterizing.** Pull the actual data first, then apply fee / latency / capture-rate models. Establishes the empirical floor before optimism kicks in.

**Rule 4 — Sample-size drives the window, not vice-versa.** Decision criteria (e.g., "75 trades / cell, kill if net edge < 0.5%") must be set BEFORE seeing results. Pre-commit ambiguous zones to prevent observed-edge from biasing the bar.

**Rule 5 — Distinguish "pattern exists historically" from "pattern is capturable now."** Sports_lag had +3.99% historical edge but zero live opportunities at the original entry zone. Backtest is necessary but not sufficient; live observation must close the loop.

**Rule 6 — Phantom edge = market correctly pricing tail risk you didn't model.** Nobel +42% / Apple CEO +37% looked like arb; were the market pricing P(unlisted winner). Always check whether the "edge" is the implied probability of an outcome you missed.

## Reproducing the work

The code is Python 3.12, managed with [`uv`](https://github.com/astral-sh/uv):

```
uv sync
# then run any of the experiments or the probe:
uv run python -m probe.main --hours 24
uv run python experiments/e11_full_scan/scan_all.py
```

All collectors use public, free APIs (gamma-api.polymarket.com, clob.polymarket.com, data-api.polymarket.com, api.binance.com, deribit.com).

## Disclosure

No capital was deployed. No trading was conducted. The findings are based entirely on observation of public Polymarket data, public wallet activity, and public market infrastructure. No accusations of informed trading or other misconduct are made against any named wallet or operator; wallet analysis is at the behavioral-pattern level only.

The LLM-assisted workflow accelerated this work meaningfully and also introduced specific failure modes documented in the synthesis. The appropriate posture: **the LLM is an exceptional research assistant and an unreliable analyst. Its polish level is not correlated with its accuracy.**
