# Plan history — how we got here

Short narrative of each pivot. Full plan doc at `~/.claude/plans/your-actual-end-buzzing-crown.md`.

## v0 — crypto funding-rate arbitrage POC

Initial framing: solo operator, crypto, paper-first, full-time. Drafted a 4-week funding-rate arb POC (cross-exchange / basis arb), Python + ccxt, VPS-ready, Brier-ish decision rubric. User rejected: too safe, too conventional, "not SaaS — optimize for finding something surprising."

## v1 — seven asymmetric opportunities

Generated a ranked shortlist of seven genuinely different high-upside edges:
1. Filing Reader (SEC/FDA/court docket NLP → equity options)
2. Signal-to-Settle (news/social → prediction markets via LLM judgment)
3. Pinnacle-to-Kalshi (sharp-to-soft prediction market arb)
4. Liquidation Radar (crypto cascade front-running)
5. Cliff Watcher (token unlock trading)
6. Cross-language News Arbitrage (Caixin/Nikkei → ADRs/crypto)
7. First-Mover Farm (early LPing on new prediction platforms)

User selected 2 + 6 for parallel POCs.

## v2 — event-impact MVP

Re-scoped to a shared measurement harness rather than two separate POCs:
- Fast Event Mode (on each news event, compute T0-30s to T0+5m reaction with a z-score classifier)
- Expiry Microstructure Mode (primary same-day signal loop — Polymarket 5m markets, 1 Hz intensive sampler in final 60s, calibration + lead-lag)
- Batch Analysis (24–48h baseline comparison with KS test)
- Cross-language RSS + Haiku translation
- Optional sidecar wallet-flow watcher

User then flagged five analytical problems:
- `err_H = |poly − outcome|` is minimized at certainty → rubric inverted
- "Mispricing" flag was hindsight-biased
- Reference-feed mismatch could invalidate all "mispricing" signals
- 1Hz REST + midpoint too coarse; need WS + separate bid/ask
- 18h build estimate optimistic → 25–30h realistic

All deferred until v3.

## v3 — cheap reconnaissance probe (current)

Simplified to: before any measurement, run a 24h probe to answer "do short-duration Poly crypto markets exist often enough?" Minimal scope, single SQLite, markdown report with explicit recommendation.

Implemented. Running since 14:21 UTC 2026-04-18. Answer already leaning positive (607 5m markets / 6 underlyings / ~400s resolution lag).

User then expanded scope: run seven parallel experiments alongside the probe to answer sub-questions that don't require probe completion. This is the current phase.

## v4 — paper-trade harness (2026-04-19)

Project re-opened to validate the surviving sports_lag thesis (and, originally, crypto_barrier) with a continuous paper-trade harness before committing capital. Plan evolved through four significant revisions in a single session:

**v4.0 — initial scaffold.** Design a continuous daemon that polls gamma-api, detects qualifying entries, simulates fills, persists positions, resolves them on settlement. Two strategies (sports_lag, crypto_barrier) × two size models (fixed $100, depth-scaled). Fee as parameterized placeholder. Observer-only pre-run to validate entry frequency before commitment. SQLite-persisted state, restart-safe.

**v4.1 — adopt `polymarket-paper-trader` (253⭐).** Open-source library covers book-walking fills, exact Polymarket fee formula, multi-account isolation, limit-order lifecycle. Cuts ~50% of build effort. Our code shrinks to strategy-specific layer on top.

**v4.2 — external-repo sweep.** Agent-driven scan of 5 candidate repos surfaced by the user (Polymarket/agents, Jon-Becker, poly_data, poly-maker, trump-code) plus a follow-up sweep for 7 toolchain gaps. Integrated `polymarket-apis` (typed Pydantic), sports-result feeds (ESPN/nba_api/MLB-StatsAPI), `python-binance` for crypto spot, `httpx + PyrateLimiter` for async. Parked Goldsky subgraph client as v2 upgrade; confirmed `poly-maker` kill via author's own README.

**v4.3 — three-track deep research.** Parallel agents swept Polymarket official docs, academic literature, and UMA dispute / operator wallet data. Three findings materially reshaped the plan:
- Fee formula was `p×(1-p)` not `min(p, 1-p)` — 2× shape error.
- V2 cutover on 2026-04-22 (3 days out) with no V1 backward compat — forces a pause/verify/resume protocol.
- Rate limits are 4000/10s Gamma vs our 5/s guess (60× conservative).
- Saguillo 2508.03474: arb duration collapsed 12.3s → 2.7s in 2025, 73% bot-captured. Yellow flag.
- Della Vedova 2026: direct academic validation of the execution-edge premise.

**v4.4 — e13 historical-backtest audit returns.** Parallel `e13_external_repo_audit` investigation against SII-WANGZJ's 954M-row on-chain dataset delivers concrete numbers:
- **crypto_barrier: −63% net edge, 37% crash rate (n=5,220) — DROPPED.**
- **sports_lag: +3.99% net edge, 14.4 min hold (n=47) — kept with sample caveat.**
- **Fees: 0.0 bps across all sports post-resolution trades (n=143) — H3 gate resolved empirically.**
- H1 wallet-diffuse contradicted at low sample size (top-10 = 68%); deferred pending deeper rerun.
- Octagon risk gates (drawdown breaker, event concentration cap) integrated.

Final v4 plan documented at `docs/PLAN_E12_PAPER_TRADE.md`. Strategy scope reduced from two to one. Fee default = 0 with shakedown assertion. V2 cutover scheduled into the run window. Run terminates at 50–100 completed trades or 7-day hard stop.

