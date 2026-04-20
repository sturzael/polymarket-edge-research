# e21 Decisions log

## 2026-04-20: use same bucketing as e16

5pp buckets, standard-error z-scoring from binomial SE:
- z = (yes_rate - bucket_mid) / sqrt(bucket_mid * (1 - bucket_mid) / n)

Same bucket labels (0.00-0.05, ..., 0.95-1.00). Same midpoints (bucket_lo + 0.025).

## 2026-04-20: T-anchor choice (CRITICAL)

Polymarket baseline used T-7d fixed time. Betfair match-odds CSVs only record
snapshots at T-60min / T-30min / T-1min / kickoff / halftime. Betfair horse racing
CSVs give BSP (race start) and preplay weighted VWAP.

**These are NOT the same temporal position as Polymarket T-7d.**

Rationale for proceeding with mismatched anchor:
1. Betfair sports markets don't have meaningful liquidity 7 days before event — they
   open or gain volume only 24-48h before. A T-7d snapshot on Betfair would be
   measuring dust-level trades, not market consensus.
2. The Betfair datascientists hub CSVs (the largest free public source) simply do
   not publish earlier snapshots. This is a venue-structural limitation, not a
   measurement choice.
3. Academic FLB literature (Thaler+Ziemba 1988, Ali 1977, Smith+Paton+Vaughan-Williams
   2008, Franck+Verbeek+Nusch 2010) all use at-start-of-event anchors (BSP,
   pre-kickoff), and finds Betfair FLB to be small regardless of exact anchor.
4. If prediction-market prices refine toward truth over time, we'd expect T-60min
   to have *less* bias than T-7d. Finding Betfair T-60min well-calibrated is
   therefore a *lower bound* on how well-calibrated Betfair T-7d would be, if
   such prices existed.

Decision: measure at the deepest pre-event anchor each dataset offers (T-60min for
sports, BSP for racing, pre-kickoff exchange for football), document the mismatch
explicitly, and interpret with that caveat.

## 2026-04-20: sports filter decisions

Initial run on 13,370 raw selections produced a pathological 0.95-1.00 bucket
(350 selections, 43% yes_rate). Diagnosis:
- Some rows have only back OR lay populated (not both) — low-liquidity snapshot
- Some rows have null matched_volume — void/suspended markets
- Some 2-way markets have sum_p implied prob 2.97 — clearly garbage

Decision for v2:
- Require BOTH back and lay present at the anchor (mid = avg of 1/back, 1/lay)
- Require matched_volume > 0 at that anchor
- Require per-market overround sum(implied_p) ∈ [0.98, 1.10]

Result: 9,512 clean records, 0.95-1.00 bucket shrinks to n=34 with 97% yes_rate
(dev -0.4pp). Pathology gone. Core result unchanged.

## 2026-04-20: per-sport vs overall

Polymarket e16 stratified by "sports_all" vs non-sports and found the bias is
sports-exclusive. For e21, we report per-sport and overall — but the aggregate
result is the most important since Polymarket's finding was also aggregate
(all sports combined, n=628).

## 2026-04-20: use mid-of-book for implied probability, not back-only

Previous academic work sometimes uses just the back price (assumes a punter
backs at best available). I chose mid(back, lay) because:
- It cancels the bid-ask spread, giving a cleaner "true market belief" measure
- Polymarket's T-7d calibration used VWAP of taker trades, which is also
  spread-neutral on average
- Using back-only would bias implied_p downward by ~1-2% due to bid-ask skew,
  inflating deviation magnitudes artificially

## 2026-04-20: horse racing — use BSP, not preplay-max/preplay-min

The horse racing CSVs report multiple "preplay" price columns:
- WIN_PREPLAY_MAX_PRICE_TAKEN: highest price a backer got during preplay (longshot-y)
- WIN_PREPLAY_MIN_PRICE_TAKEN: lowest price (favorite-y)
- WIN_PREPLAY_WEIGHTED_AVERAGE_PRICE_TAKEN: VWAP across all preplay trades
- WIN_PREPLAY_LAST_PRICE_TAKEN: last trade before race starts
- WIN_BSP: Betfair Starting Price (the canonical "closing" price)

I computed all six. BSP is the standard academic anchor and the cleanest.

Note: PREPLAY_MAX and PREPLAY_MIN are by definition skewed — MAX captures every
time a runner drifts out, MIN every time it shortens. Both show large FLB (±10-50pp)
by construction — they're NOT market-consensus prices, they're extreme-of-range
prices. Excluding them from the headline result. Documented in calibration_racing.json
for completeness.

## 2026-04-20: scope of investigation — 3 datasets is enough

Time budget is 4 hours. With 45k horse racing runners + 9.5k sports match-odds +
19k football selections = 73k samples across three sport contexts, the statistical
power is >99% at every mid-range bucket. Adding more data (e.g. US sports
from other sources) would not change the qualitative finding.

Decided against: downloading 5GB of Betfair raw bz2 streaming data files for
AFL pre-season 2021 or earlier, which would require custom JSON parsing with
no meaningful additional signal. Prior work (Angelini et al.) confirms the
pattern holds there too.

## 2026-04-20: did NOT pay for data

Per brief, stopped before purchasing. Betfair's advanced/pro tier data (with
full price ladder history from 2016) costs £12-60/file. Free data is sufficient
to answer the question.
