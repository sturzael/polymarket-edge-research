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
