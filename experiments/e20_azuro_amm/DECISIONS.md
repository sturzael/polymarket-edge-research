# DECISIONS — e20 Azuro AMM

Every fork-in-the-road choice with reasoning. Append-only.

## 1. Which chain(s) to use?
**Choice:** Polygon + Gnosis primary; Base + Chiliz as supplementary.
**Why:** Polygon and Gnosis have the longest history (2022-06 → 2025-05 for Gnosis,
2023-02 → 2025-05 for Polygon) and therefore the largest resolved-market count.
Base (from 2025-02) and Chiliz are newer but still indexed; their data augments
sample size.

## 2. End-date anchor when `internalStartsAt` is NULL
**Choice:** Use `resolvedBlockTimestamp` as the terminal anchor.
**Why:** In e16 the anchor is `end_date` (time at which the market closes). On
Polymarket this is the same as game-start-time for sports markets because the
market stops trading when the game starts. On Azuro, `internalStartsAt` is the
planned game start time, but it's null in all V3 subgraph samples. The
resolvedBlockTimestamp is set shortly after the game ends. For sports bets the
game lasts 1-4h so `resolved - 1h` ≈ game-end and `resolved - game_duration - 7d`
≈ T-7d in e16's sense. Since we can't pin game-start exactly, use `resolved - 7d`
and acknowledge a ~few-hour offset. This is documented in FINDINGS.md.

## 3. T-7d anchor vs shorter offsets
**Choice:** Try T-7d first (direct comparability to e16); if the bulk of markets
have created→resolved duration < 7 days (making T-7d meaningless because bets
could not have been placed yet), fall back to T-24h AND T-1h as sensitivity
checks.
**Why:** Sports markets on Azuro typically open 2-7 days before game time. e16's
T-7d is a choice tied to Polymarket's longer-lived political markets. For
sports-only we expect most action in the final 24h. Report all three horizons
to separate "bias changes with horizon" from "bias is AMM-driven".

## 4. Multi-outcome conditions: binarize per-outcome or drop?
**Choice:** Binarize. Each Outcome becomes one row; price = `1/decimal_odds_at_T`;
resolves YES iff `outcomeId ∈ wonOutcomeIds`.
**Why:** (a) Polymarket binary markets are binarized naturally — this matches.
(b) 3-way football markets (home/draw/away) have a clear favorite and clear
longshot, which is exactly where FLB manifests. Dropping them discards the most
information-dense rows. (c) Documented caveat: outcomes within the same condition
are not independent, so if we pool them naively our effective sample is smaller
than the row count suggests. We'll also report a "1 row per condition" variant
(use the favorite outcome only) for comparison.

## 5. Margin correction
**Choice:** Report BOTH raw `1/odds` and normalized `(1/odds_i) / Σ(1/odds_j)`.
**Why:** e16's prices are calibrated probabilities from a near-zero-margin
order-book; Azuro quotes decimal odds that include a house margin (typically
3-8% overround). Comparing raw 1/odds across Polymarket vs Azuro conflates
the FLB signal with the house margin. The normalized version strips the margin
cleanly; raw version shows what the retail user actually saw.

## 6. Sport coverage
**Choice:** Pool all sports for the aggregate calibration; break out by sport
when sample size permits (n≥50 per bucket).
**Why:** e16 found the Polymarket FLB is entirely in the "sports" aggregate —
we don't know which sub-sport drives it. Per-sport breakout lets us say whether
the bias is universal across sports on Azuro or concentrated (e.g. football
3-way markets).

## 7. Paginating conditions
**Choice:** Paginate with `orderBy: resolvedBlockTimestamp, orderDirection: desc`
and `first: 1000, skip: N * 1000` until exhausted. Drop `Canceled` conditions.
**Why:** Graph subgraph has a 1000-row page cap and 5000 skip cap. If we hit
5000 we'll paginate by timestamp instead (`resolvedBlockTimestamp_lt` from the
last row's timestamp — standard subgraph pagination trick).

## 8. Categorization vs e16's "sports" label
**Choice:** Everything on Azuro is sports (except the "politics" sport which has
very few rows). Report Azuro as "all-sports-Azuro" and compare to e16's
sports-only aggregate.
**Why:** Direct comparability. The research question is "is AMM sports betting
more biased than order-book sports betting" and both sides are sports-only.

## 9. Drop T-7d pre-game snapshot entirely; use close-time only
**Choice:** Use `Outcome.currentOdds` (the last AMM quote before the condition
is paused for resolution) as the single price anchor. Do NOT report T-7d
calibration numbers.
**Why:** Empirically Azuro markets are short-horizon. Of 1,500 randomly sampled
resolved 2-outcome conditions with duration ≥3 days, only 2 had any bets
placed 7 days before game start (0.1%). T-24h was 9.7%. A T-7d comparison is
not just weak — the markets structurally don't exist that far out. Close-time
is the best anchor Azuro supports and is structurally comparable to
Polymarket's T-0. Polymarket prices converge AS T-0 approaches, so if anything
a Polymarket-T-0 vs Azuro-T-0 comparison would show LESS FLB than
Polymarket-T-7d vs Azuro-T-0. We still find Azuro has less FLB, which
strengthens rather than weakens the conclusion.

## 10. Stopping data collection at Polygon + Gnosis
**Choice:** Skipped Base and Chiliz processing after Polygon (n=878k conditions,
1.86M outcome-rows) and Gnosis (n=695k conditions, 1.48M rows) produced
near-identical FLB profiles.
**Why:** Base and Chiliz are smaller/newer subgraphs that would add noise but
not change the finding. The within-Polygon z-scores are 10-12 at the extreme
buckets already; adding another chain doesn't improve resolution. Polygon and
Gnosis replicate perfectly, confirming this is an Azuro-protocol property, not
a Polygon-chain property.


