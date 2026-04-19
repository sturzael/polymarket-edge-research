# e10 — findings (stopped early)

## TL;DR

Stopped at **6.79h** of a planned 48h run on 2026-04-19 02:52 UTC. Headline verdict **was as the framing rule required — "null result — no signal distinguishable from control noise"** (ratio 1.12×). But that number is not trustworthy yet: two calibration bugs in the analysis layer mean the 17 flagged events are almost certainly noise, and the real absolute flag rate would tighten substantially with more baseline data. The framing rule + control comparison worked exactly as designed — they prevented a spurious "we found something" reading from the Iran-ceasefire cluster. What did NOT work is the `low_confidence` feed-silence flag and the baseline-σ estimator on short data. Both are fixable; neither was fixed before stop.

## Run summary

- Launched: 2026-04-18 08:04 UTC (PID 19678).
- Stopped (SIGINT): 2026-04-19 02:52 UTC — 6.79h of snapshot span, 18h 48min of wall time (the analysis-window span is shorter than wall time because wall includes startup and the watcher reports span from first-snapshot-ts to last-snapshot-ts).
- Reason for early stop: at the 6h gate, analysis revealed calibration issues that would have poisoned the 48h verdict. Continuing would have accumulated more data under a broken report generator. Cheaper to stop, fix, re-run if wanted.
- Final artefacts preserved in `e10.db`:
  - markets: 29 (18 candidate + 11 control)
  - snapshots: 10,266
  - news_items: 404
  - news_market_matches: 627 (373 real + 254 `__nomatch__` sentinels)
  - feed_health: 2,395
  - flagged_events: 17 (11 candidate + 6 control)

## Headline numbers

| metric | candidate | control |
|---|---|---|
| markets | 18 | 11 |
| market-hours observed | 121.4 | 74.2 |
| flags | 11 | 6 |
| flags per 1k market-hours | 90.64 | 80.90 |
| **ratio** | **1.12×** | |

**Verdict (from the ratio→label table compiled into `analyze.py`):** *null result — no signal distinguishable from control noise*.

Decision gate: the candidate/control ratio ≥ 3× requirement is nowhere near met. No event passed manual review (none were reviewed — see "what did not work" below). Gate did not open.

## What worked

1. **The framing rule blocked a tempting but wrong narrative.** The top-3 flagged events are all Iran-ceasefire peace-deal markets moving up in tandem around 20:40 UTC with $9–13k of volume delta each — exactly the kind of pattern that a tired reviewer would circle as "suspicious." The pre-committed ratio→verdict table forced the report to say "null result", and the `nearby_markets = 2` column on all three events honestly labels them as theme co-movement. Without those calibrations this run would have produced a false positive.

2. **Control markets did their job.** Eurovision, World Cup, tennis, aliens, 2028 US election controls produced 6 flags — nearly matching the candidate rate. This is the single most important finding of the run: our detector is noisy enough that candidate flags must be evaluated against control flags, not against zero.

3. **Infrastructure stood up clean.** 60-second snapshot cadence hit exact cycle counts (29 markets × N cycles = row counts match). 8 feeds polled on their staggered cadences with the `news_items` UNIQUE constraint catching duplicates correctly. Discovery loop accumulated 165+ new candidate markets into `data/candidates_new.jsonl` without auto-adding — curation invariant held.

4. **The gamma-api filter-quirk and dead-feed discovery paid off during verification.** No runtime surprises from ignored filter params or dead RSS endpoints.

5. **Cost was actually weekend-scoped for the build phase.** Despite the Plan agent's "actually two weekends" warning, the build + smoke + launch was 1 evening of work. The analysis-phase calibration is the part that needed another sitting — accurate to the Plan agent's framing.

## What did not work

### 1. `low_confidence` threshold is broken — 17/17 events flagged ⚠️

`FEED_SILENT_SOFT_MINUTES = 60` with a 70-minute window is too tight for feeds that publish ~1 item every 10–20 min. ABC International emitted 42 items over 6.79h (≈1/9min) and Times of Israel emitted 21 (≈1/19min). Any random 70-min window has a meaningful chance of containing 0 items from these feeds purely from Poisson timing — not because they were silent during real news. The flag therefore fires on nearly every event regardless of actual health, rendering the ⚠️ signal useless.

**Fix (post-mortem):** one of —
- raise threshold to 120–180min; or
- compute "silent" as "gap > K × feed's own median inter-item gap" rather than a global constant; or
- use the `feed_health` table's per-poll `items_received` to detect *polling* silence rather than *publishing* silence.

The third is probably best — `feed_health` records what the watcher actually observed on its polls, which separates "feed was healthy and just didn't have news" from "feed was unreachable".

### 2. Baseline σ estimator is statistically thin on 6.79h of data

Baseline σ is computed over non-news-matched 10-min Δprice windows. At 6.79h span that's ≲40 baseline windows per market, some of which are excluded for news-match overlap. On illiquid markets where typical 10-min Δprice is ±0.001, a z=3 firing at Δprice=0.003 can be triggered by a single retail-sized order. This inflates both candidate and control flag rates roughly symmetrically — which is why the **ratio** stays honest at 1.12× — but the absolute flag counts are almost certainly overstated noise.

**Evidence:** top flagged events by z-score include `will-the-iranian-regime-fall-by-june-30` at z=6.32 with Δprice=+0.010 on a market with current price around 0.08, and `will-spain-win-the-2026-fifa-world-cup-963` at z=6.15 with Δprice=**−0.003**. Z-scores that high on moves that small mean baseline σ is being estimated at near-zero, which reflects thin data, not actual market quietness.

**Fix (post-mortem):** require ≥24h of snapshot span before running detection, or use a shrinkage estimator that regularizes toward a cross-market prior when per-market data is thin.

### 3. Kyiv-post died before launch and stayed dead the whole run

Last publish 2026-04-18 15:11 UTC — 5h before launch, 11h 40min before stop. The 3h hard-exclusion fired continuously for russia-ukraine-themed events. One russia-ukraine market (`russia-x-ukraine-ceasefire-before-2027`) is in `markets.yaml`; it produced zero flags because every candidate event was filtered out on feeds-healthy. We have no russia-ukraine signal data from this run at all.

**Fix (post-mortem):** either drop kyiv-post from the russia-ukraine theme-relevant set and rely on global feeds (BBC, NYT, Guardian, Al Jazeera) or swap in a different Ukraine-specific feed (Kyiv Independent's actual working URL if one exists; Ukrainska Pravda if they publish English RSS).

### 4. Iran-ceasefire cluster swamps the flag list

Of 11 candidate flags, 5 are on `us-x-iran-permanent-peace-deal-by-{april-22,april-30,may-31}` variants. These are five separate markets on the same underlying event. Their prices move in near-lockstep by construction. The nearby_markets filter correctly labels them theme co-movement (nearby=1 or 2 on most), but the top-of-list ranking by news-lead puts them at positions 1–3 anyway.

**Fix (post-mortem):** de-duplicate by keeping only the highest-z event per (market-theme, time-bucket) pair in the ranked list, or collapse per-theme flag counts before computing the ratio so theme-cluster markets don't inflate candidate flag count.

## What we learned about the signal itself

Honestly, not much. The null verdict stands at 1.12× — if anything, that's evidence that the detector (noisy as it is) is not picking up geopolitical-market moves that distinctively precede our monitored news, because it's picking up control-market moves at a roughly equal rate. But the absolute signal is so dominated by noise that we can't rule out a small real effect either. The run told us more about our instrument than about the hypothesis.

The most interesting individual flag was `will-the-us-confirm-that-aliens-exist-before-2027` — flagged twice, with 0 news hits across 8 feeds, and volume deltas of $102k and $1k. On the surface this is "move without news". In practice, it's a control market, it's z=4.42 on a Δprice of ±0.010, and the 102k volume spike is almost certainly a single whale rather than informed flow. But it's the profile the detector was built to find, and worth noting as a calibration target: if our detector can't distinguish the aliens market's random walk from a real leak, we don't have a leak detector.

## What to do with this

**Recommended: stop here.** The hypothesis ("geopolitical markets show moves preceding our news set at a rate distinguishable from controls") has produced a null at 6.79h with significant noise. Running the full 48h without fixing the calibration bugs would not change the verdict — the ratio is robust to those bugs, and the ratio said null. Running the full 48h **with** the calibration fixes might tighten the ratio, but the Plan agent's pushback stands: RSS-based "pre-news" detection is fundamentally weaker than social-media baselines, and the strongest candidate markets in this study (trump-announces-* variants) need Truth Social to be meaningfully tested. That's a bigger rebuild than a threshold tune.

**If you want to resurrect this:**
1. Fix the three calibration issues above (threshold via `feed_health` polling-silence, baseline ≥24h, dedupe by theme-cluster).
2. Add Truth Social via `trumpstruth.org` RSS mirror — specifically because several markets in `markets.yaml` have Trump's announcement as the news event itself.
3. Run for 72+h to build a proper baseline.
4. Budget two full days of analysis time, not one evening.

**If you want to pivot instead:** the 627 matched-news rows and 10,266 snapshots are a usable dataset for a different question — for example, "does news volume on a market's keywords predict next-hour volatility on that market?" That's a weaker question than the leak question, but it's tractable with current data and would give the feed infrastructure a second life.

## Decision gate — final call

- ≥3 events passing the full disqualifier checklist: **not evaluated** (would have been the next manual step; given the 1.12× ratio and 17/17 ⚠️ flags, any positive manual verdicts would not have changed the decision).
- Candidate/control flag-rate ratio ≥ 3×: **not met** (1.12×).

**→ Kill the direction as currently scoped.** E11 (wallet-level forensics) is NOT unlocked by this result. If the direction is revisited later, it should be an e10 v2 with the fixes + social-media baseline, not an e11 built on e10's null.

## Cross-references

- Design log: `DESIGN_LOG.md`
- Pre-committed manual review rubric: `MANUAL_REVIEW_RUBRIC.md` (unused — no events reached manual review)
- Generated report at stop: `REPORT.md`
- Project-wide running log entry: `docs/FINDINGS.md` → "Geopolitical informed-trading probe (e10) — 2026-04-18"
- Raw data (gitignored): `e10.db`, `watcher.log`, `data/candidates_new.jsonl`
