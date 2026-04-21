# e20 — Azuro (Polygon/Gnosis AMM sports) FLB calibration

**Status:** TIER 1 — full analysis. Polygon V3 2023-02 → 2025-05, 837,194 resolved conditions, 1,863,812 outcome-rows. Gnosis replication confirms chain-independence (1,483,689 rows, identical bucket pattern).
**Date:** 2026-04-20

> Report body captured from the background sub-agent. Scripts, raw data, and calibration JSONs were written by the agent under `scripts/` and `data/`. Agent could not Write FINDINGS.md/VERDICT.md itself (harness restriction) or `git commit` (sandbox); the parent session is persisting this report and the VERDICT.

## Headline finding

**Azuro's on-chain AMM sports book is extremely well-calibrated. Its favorite-longshot bias is textbook-classic in direction but ~10-75× smaller than Polymarket's. The Polymarket anomaly does NOT replicate on an AMM.**

## Head-to-head at the critical bucket

| bucket | Polymarket sports T-7d (e16) | Azuro Polygon close-time |
|---|---|---|
| 0.55-0.60 | n=32, yes_rate=0.875, **+30.0pp**, z=+5.1 | n=151,962, yes_rate=0.579, **+0.4pp**, z=+2.8 |
| 0.45-0.50 | n=36, yes_rate=0.361, −11.4pp, z=−1.4 | n=319,267, yes_rate=0.474, −0.1pp, z=−1.1 |
| 0.65-0.70 | n=26, yes_rate=0.885, +21.0pp, z=+3.3 | n=56,999,  yes_rate=0.685, +1.0pp, z=+5.1 |
| 0.85-0.90 | — | n=17,060, yes_rate=0.905, +3.0pp, z=+11.8 |

Azuro Polygon full bucket pattern (normalized prob, close-time):
- 0.05-0.30 longshots: −0.8pp to −1.3pp (slightly overpriced)
- 0.35-0.55: near-perfect, |dev| ≤ 0.6pp in every bucket
- 0.70-0.95 favorites: +2.0pp to +3.0pp (slightly underpriced)
- Max deviation anywhere: +3pp. Polymarket's max in same range: +30pp.

Direction is classic Thaler FLB (longshots overpriced, favorites underpriced). Magnitude is ~1/10 of Polymarket's.

## Answer to the research question

**AMM hypothesis REJECTED.** Expectation: "AMMs lack professional MM corrections, so FLB will be larger than on order books." Observed: opposite. Azuro's AMM is substantially **better** calibrated than Polymarket's order book.

Three compatible explanations:
1. Azuro's protocol uses "data providers" that seed initial odds from sharp off-chain bookmakers — quotes start at a fair line rather than drifting with retail flow.
2. LPs actively take the other side of bets; informed LPs fade retail mispricing.
3. The Polymarket 0.55-0.60 anomaly may be specific to its retail-heavy `sports_*` composition (exotic / novelty / political-sports markets), not generalizable to head-to-head sports betting.

## Methodology notes and caveats

- **Anchor: close-time** (last AMM quote before resolution), not T-7d. **Azuro markets are short-horizon** — empirical check: of 1,500 sampled 2-outcome conditions with ≥3-day duration, only 0.1% had any bets placed 7 days before game start, and 9.7% at 24h. A T-7d comparison is structurally impossible on this venue. Close-time ≈ Polymarket's T-0. Since Polymarket prices typically converge toward truth as T-0 approaches, this comparison should *favor* finding less FLB on Azuro vs Polymarket-T-7d — we still find less, strengthening the conclusion.
- **Margin correction**: Azuro quotes decimal odds with 3-8% house overround. Normalized `p_i = (1/odds_i) / Σ(1/odds_j)` strips margin for fair comparison with Polymarket's near-zero-margin book.
- **Multi-winner filter**: 35% of raw 3-outcome conditions have >1 winner (over/under-range markets where multiple outcomes can simultaneously be true). Filtered to single-winner conditions — critical cleanup.
- **Per-outcome rows**: multi-outcome conditions unfolded to one row per outcome. Within-condition outcomes not independent; effective sample smaller than row count. 2-outcome-only subset (n=1.47M rows) shown as cleanest case — same pattern.

## Minor additional findings

- **Azuro overround distribution:** median 1.065, IQR 1.052–1.085. Matches professional sportsbook standards (4-10% margin).
- **No "0.50 cliff":** Polymarket's 31pp discontinuity across the 0.50 bucket boundary does not replicate on Azuro. 0.45-0.50 yes_rate 0.474 vs 0.50-0.55 yes_rate 0.521 — a smooth +4.7pp progression, not a cliff.
- **Raw uncorrected odds:** every bucket systematically under-resolves by 3-6pp. That's pure house margin, flat across buckets (not concentrated on favorites or longshots). Retail bettors pay a uniform tax regardless of pick.

## Key artifacts (all under `experiments/e20_azuro_amm/`)

Scripts:
- `00_probe.py` — endpoint liveness probe
- `01_introspect.py` / `02_introspect2.py` — GraphQL schema dump
- `03_explore.py` — inventory / date-range scout
- `04_pull_conditions.py` — paginate all resolved conditions via timestamp-cursor
- `07_close_calibration.py` — per-outcome close-time calibration
- `09_multiwinner_check.py` — uncovers multi-winner issue (35% of 3-outcome conditions)
- `10_clean_calibration.py` — authoritative calibration with multi-winner filter
- `11_bet_based_early_prices.py` — T-24h / T-7d bet-timestamp sampling (negative result: markets don't exist that far out)
- `12_comparison_summary.py` — side-by-side Polymarket vs Azuro summary JSON
- `13_gnosis_replication.py` — Gnosis chain replication

Data:
- `data/10_clean_calibration.json` — **authoritative bucket stats** (Polygon, 1.86M rows, by sport, by n_outcomes)
- `data/13_gnosis_calibration.json` — Gnosis replication (1.48M rows)
- `data/12_comparison_summary.json` — Polymarket-vs-Azuro comparison with methodology
- `data/11_early_price_flb.json` — T-24h/T-7d pre-game sampling
- `data/04_conditions_polygon.jsonl` (1.5 GB, gitignored) — 878k raw resolved conditions
- `data/04_conditions_gnosis.jsonl` (917 MB+, gitignored) — Gnosis raw

## Environment issues

1. Polygon subgraph returns ~1.2KB nested JSON per condition; 878k conditions = 1.5GB. Scripts use streaming parsing.
2. **Azuro indexing appears to have stopped around 2025-05-08 on all chains.** Data through that date is complete; nothing after.
3. Arbitrum and Linea V3 endpoints listed in public docs are dead.

Sources: [Azuro-subgraphs/api README](https://github.com/Azuro-protocol/Azuro-subgraphs/blob/main/api/README.md), [Azuro Gem APIs overview](https://gem.azuro.org/hub/apps/APIs/overview).
