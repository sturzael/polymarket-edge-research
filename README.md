# Two Days Hunting for Edge on Polymarket

A structured research project investigating whether a solo operator could find tradeable edge on Polymarket using an LLM-assisted research workflow (Claude Code + conversational review).

**TL;DR:** Ten trading theses investigated. Nine falsified (including crypto-barrier residual arb, killed on 2026-04-19 by a historical backtest showing −63% net edge / 37% crash rate across n=5,220). One survives (sports settlement-lag arb) with the fee gate now empirically resolved (zero on-chain taker fees across 143 sports post-resolution trades) and a sample-thin +3.99% historical net edge confirmed. A paper-trade harness is planned; decision pends 50–100 paper trades. Honest upside estimate: **$100–$1,500/month at $5–20k capital** for a VPS-operated solo trader, assumption-dependent.

The more durable output is methodological — two rules (÷5 on revenue estimates, counter-memo before action) that repeatedly caught estimation drift, plus new rules from this session (measure raw first, parameterize fees, sample-size drives window).

👉 **[Read the full synthesis](SYNTHESIS.md)** — methodology, findings, what worked and what didn't. For the current paper-trade plan, see [`docs/PLAN_E12_PAPER_TRADE.md`](docs/PLAN_E12_PAPER_TRADE.md).

## Repository structure

- [`SYNTHESIS.md`](SYNTHESIS.md) — the main writeup; start here
- [`docs/`](docs/) — chronological findings, plan history, individual opportunity writeups, counter-memos
- [`probe/`](probe/) — 24h Polymarket market-structure reconnaissance probe
- [`experiments/e1`](experiments/e1_post_expiry_paths/) – [`e11`](experiments/e11_full_scan/) — individual thesis investigations
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
