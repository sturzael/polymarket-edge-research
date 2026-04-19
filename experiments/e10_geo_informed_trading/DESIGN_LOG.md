# e10 — design log

Companion to `README.md` (scope + run instructions) and `MANUAL_REVIEW_RUBRIC.md` (pre-committed disqualifier checklist). This file preserves the reasoning behind design decisions so future-me can reconstruct *why*, not just *what*.

---

## Origin

2026-04-18, exploring whether the existing crypto-focused reconnaissance project could "latch onto" an insider-trading angle after a Reddit thread alleged informed trading on a Polymarket Iran/US war market. The reddit URL (`/r/PredictionsMarkets/comments/1rx661o/insider_on_iranus_war_market/`) was not fetchable from Claude Code (reddit.com blocked by the sandbox), so the thread's specific claims aren't captured here — work from the general hypothesis only.

## Scope decision

The request was open-ended. Narrowed via explicit options:

| Angle | Taken? |
|---|---|
| Extend probe to detect suspicious crypto flow | no |
| **Geopolitical market monitor (new scope)** | **yes** |
| Wallet-level forensics | no (deferred to e11 conditional on e10 verdict) |
| Copy-trade signal | no (ethically loaded, out of scope) |

| Commitment | Taken? |
|---|---|
| **Research sketch / weekend probe** | **yes** |
| Candidate product direction | no |

So: one more experiment in the `e*` series, following e1–e9 conventions. Goal is **not** to prove insider trading; goal is to cheaply test whether geopolitical markets show price moves preceding our monitored news set at a rate distinguishable from low-news control markets. Decision gate feeds forward into whether wallet-level forensics (e11) is worth building.

## Key design decisions

### Detection approach: z-score flag, not regression
Considered three detection algorithms: (A) z-score move without matching news, (B) regression of Δprice on news-timestamp dummies, (C) clean-baseline variant of A. Option B needs many news events per market to converge; with ~30 markets × 48h there are too few matched events per market for regression. Picked A-with-C's clean-baseline approach: use only non-news-overlapping windows to compute baseline σ, then z-score the entire timeline.

### Gamma-api filter quirk (discovered during verification)
Probed `tag=`, `tags=`, `category=`, `categories=`, `tag_id=` on `/markets`. Two requests differing only in filter value returned byte-identical responses — confirmed the filter parameters are silently ignored. `/tags` endpoint works for enumerating tag labels, but those labels cannot filter `/markets`. Committed to the fallback approach from the plan: slug-substring matching (regex in `watcher.py::GEO_SLUG_RE`) + manual curation of `markets.yaml`. Memory saved at `gamma_api_filter_quirk.md`.

### News feeds: 8 live, 5 dead
Verified every URL with 2026-current curl before committing. Dropped: Reuters worldNews (connection refused — killed 2020), Reuters `/world/rss` (401), rsshub apnews (403), Haaretz (404), Kyiv Independent `/feed` (404). Kept: BBC World, Al Jazeera, Times of Israel, Kyiv Post, SCMP, NYT World, Guardian World, ABC News International. Memory saved at `dead_rss_feeds.md`.

### markets.yaml: 18 geo + 11 control (not the planned ~30 + ~10)
Hand-curation from the top-500 markets by `volume24hr` turned up only 18 obvious geopolitical-with-real-liquidity candidates. The discovery loop logs further candidates to `data/candidates_new.jsonl` for manual review; expanding the set requires human vetting (not auto-add) so the curation invariant is preserved.

## Plan-agent critical pushback (worth preserving)

Before any code was written, an independent Plan agent reviewed the proposed design and pushed back hard on several framings. Captured here because these are calibrations that should NOT be forgotten when reading the code later:

1. **"This cannot prove insider trading. Frame as instrument calibration."** RSS lags Twitter/Telegram by minutes-to-hours. A "move before RSS" is weak evidence on its own. The deliverable is not "we found a leak"; it's "K qualifying pre-news moves, of which J plausibly rule out public-cause explanations". If J ≥ 1 with a clean narrative, that's the hook for e11.

2. **"Weekend probe" is actually two weekends.** Weekend 1: build + smoke-run. Weekend 2: 48h collection + manual review. Flagged up front so expectations are set.

3. **News timestamp quality is the weakest link.** `best_ts = MIN(pub_ts, seen_ts)` is an upper bound on publicness, not the real first-public time. Don't overclaim.

4. **Control markets are load-bearing, not decorative.** Selection bias: markets picked for being newsworthy will see more news-timed moves by construction. Control markets (Eurovision, Oprah 2028, Kim Kardashian 2028, aliens, tennis) are the counterweight. If candidates flag at the same rate as controls, nothing is being detected.

5. **Thin-book noise will dominate.** On most geopolitical markets, $500 of volume can mechanically move price ≥3σ. Expect 60–80% of raw flags to be thin-book artefacts; the `volume_delta ≥ $500` filter is load-bearing.

6. **Theme co-movement ≠ leak.** Iran news moves both `iran-strike-*` and `hormuz-traffic-*` markets. The nearby-markets filter (z ≥ 1 on any same-theme market in the same window) catches this.

7. **Reputational/legal.** Market-aggregate level only. Wallet attribution in e11 would inherit 10× this concern and needs a legal/ethics checkpoint, not just a technical one.

## Smoke run

2026-04-18 ~07:54 UTC, 3-min smoke in `--smoke` mode (3 markets, 2 feeds, 15s cadence): all 7 tables populated, 18 snapshots, 57 news items from BBC + Al Jazeera, 3 real news→market matches, 55 `__nomatch__` sentinels, 182 discovery candidates logged. No exception loops; async task lifecycles clean. Cleaned the smoke DB and candidate file before the real 48h launch.

## Real 48h run

Launched 2026-04-18 08:04 UTC detached (`nohup ... & disown`), duration 48h (ends ~2026-04-20 08:04 UTC). PID 19678. Initial health at ~20min elapsed: 551 snapshots across 29 markets, 345 real news→market matches, 8/8 feeds alive. Watcher log: `watcher.log`. Outstanding concern: kyiv-post feed went stale (last publish ~5h before launch time); if this persists, russia-ukraine theme events will hit the 3h hard-exclusion and drop out.

## Post-smoke calibration (the 4 changes + framing rule)

After the smoke run, a review of the analysis design produced four corrections + one framing constraint. All applied to the analysis side only — no watcher restart:

1. **Control comparison is now the HEADLINE of REPORT.md.** Per-market-hour flag-rate ratio (candidate vs control) is the first section, before coverage stats and the top-20 events. Ratio ≤ 1.0× = clean null regardless of how interesting individual events look.

2. **Per-feed health during each event window.** The earlier `feeds_healthy` boolean was too coarse ("all feeds publishing in last 3h"). Now each flagged event carries a `feeds_detail_json` with per-feed `{items_in_window, last_pub_ts, silent_minutes}` for the theme-relevant feed set, over the window `[t_start − 60min, t_end]`. Any theme-relevant feed silent >60min in that window sets `low_confidence = 1` and prefixes the event with ⚠️ in the report. Rationale: BBC silent during a Middle East market move matters a lot; SCMP silent during the same move doesn't matter at all.

3. **Pre-committed manual-review rubric.** Added `MANUAL_REVIEW_RUBRIC.md` enumerating the six trivial explanations (thin-book-noise, theme-co-movement, unmonitored-source-broke-first, market-artefact, quote-widening-only, reference-market-correlation). Only `unexplained-by-monitored-feeds` is an admissible positive verdict, and only after all six disqualifiers have a written ruling-out. Pre-committing the rubric blunts the fatigue-bias failure mode where reviewers label compelling-narrative events "plausible leak" and tired-evening events "explained".

4. **Theme-relevance map for feeds.** Each entry in `feeds.yaml` now has `themes: [...]`. A feed is theme-relevant to a market if its themes include the market's theme-group (e.g. `middle-east` for `iran-*`/`israel-*` markets) or `global`. Both the hard exclusion check at event admission and the soft ⚠️ silence check are now theme-aware.

### Plus the framing rule (pre-committed in `analyze.py`)

The ratio→verdict table is compiled into code, not judgment-called at report time:

| ratio | verdict label |
|---|---|
| < 1.0× | null result — control flags at or above candidate rate |
| < 1.5× | null result — no signal distinguishable from control noise |
| < 3.0× | weak signal; individual events may or may not survive the manual review rubric |
| ≥ 3.0× | candidate signal above control baseline; apply decision gate + manual review rubric to top events |

The phrases *"suspicious"*, *"consistent with informed trading"*, *"insider-like"*, *"leak"* are NEVER emitted by the report generator. Strongest admissible phrasing: `unexplained by our monitored feed set`. Asserted in the analysis self-test.

### What the reviewer explicitly said NOT to change

- Don't expand the market list.
- Don't add more feeds.
- Don't add social-media scraping even if tempted.
- Don't extend the 48h window unless you already have ambiguous results.
- Don't make flagging more sensitive; if anything, stricter.

Every addition multiplies noise and misinterpretation surface.

## Outstanding design question — Truth Social

Raised during the 48h run: should Trump's Truth Social be tied into the feed set? Several markets in `markets.yaml` are literally `trump-announces-*` markets — for those, his Truth Social post *is* the news event. Adding Truth Social would tighten the `unmonitored-source-broke-first` disqualifier significantly.

**Decision: deferred.** Adding feeds mid-run corrupts the candidate-vs-control comparison — if the rate changes after adding TS, we can't tell whether TS closed a real leak gap or just happened to cover Iran-themed news. Wait for the current v1 verdict against the existing feed set. If the result is ambiguous, or if the `unmonitored-source-broke-first` disqualifier eats most candidates in manual review, add Truth Social for an e10 v2 with a clean control.

If added later, the cheap path is `trumpstruth.org`'s RSS mirror (not scraping Truth Social directly — TOS friction, rate limits).

## Epilogue — stopped early 2026-04-19 02:52 UTC

Run halted via SIGINT after **6.79h of snapshot span** (10,266 snapshots, 404 news items, 627 matches, 17 flagged events). Reason: at the 6h analysis gate the `low_confidence` threshold proved too tight to be informative (17/17 events ⚠️) and baseline σ was statistically thin enough to inflate absolute flag counts. Continuing to 48h without fixing those would have accumulated more data under a broken report generator; cheaper to stop.

**Headline verdict:** ratio 1.12× → *null result — no signal distinguishable from control noise.* Decision gate (≥3× ratio + ≥3 manual-verdict events) not met. **E11 wallet forensics is NOT unlocked.** Direction killed as currently scoped.

The framing rule + control comparison worked exactly as intended: top-3 flagged events were Iran-ceasefire lockstep movers that a fatigued reviewer would have circled as suspicious — report correctly labeled them theme co-movement and refused the spicy verdict. The infrastructure was the win; the hypothesis was honestly a null.

If the direction is ever revisited, the three post-mortem fixes are in `FINDINGS.md`: (a) silence threshold should measure *polling* silence from `feed_health`, not publishing silence; (b) require ≥24h span before running detection; (c) drop kyiv-post from russia-ukraine relevance or swap in a working Ukraine feed. Also: Truth Social integration for `trump-announces-*` markets is the biggest potential accuracy gain, still deferred.

Full retrospective: `FINDINGS.md`.

## Cross-references

- Top-level plan: local-only (Claude plans file, not in repo)
- Project running log entry: `docs/FINDINGS.md` → "Geopolitical informed-trading probe (e10) — 2026-04-18"
- Saved memories: `gamma_api_filter_quirk.md`, `dead_rss_feeds.md`
- Live run artifacts (gitignored): `e10.db`, `watcher.log`, `data/candidates_new.jsonl`
