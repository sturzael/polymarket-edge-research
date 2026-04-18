# e10 — Geopolitical Informed-Trading Probe

## Question

Do Polymarket geopolitical markets show price moves that precede our monitored public-news set, at a rate distinguishable from low-news control markets?

This is **not** an insider-trading detector. It is an instrument-calibration study. The output is a short ranked list of "moves not explained by our monitored RSS set" for manual review, plus a candidate-vs-control flag-rate comparison.

## What this can and cannot do

- **Can:** produce a short ranked list of candidate pre-news moves, each with enough context for an analyst to eyeball. Compare flag rate on geopolitical markets to control markets.
- **Cannot:** prove a move preceded *all* public information. RSS lags Twitter/Telegram by minutes-to-hours. A true leak detector needs social-media timestamp baselines (out of scope for e10).

## Design

### Detection

For each tracked market:
1. Compute rolling 24h std of 10-minute Δprice, using only windows that do NOT overlap any news-match timestamp (±30min) — clean baseline.
2. Sweep timeline in 10-minute steps; for each window compute `z = |Δprice| / σ_baseline`.
3. For windows with `z ≥ 3`, require **all**:
   - `volume_delta ≥ $500` in the window (from diff of `volume_24hr`) — discard thin-book noise.
   - All monitored feeds have published in the last 3h (`feeds_healthy = 1`) — discard feed-outage false positives.
   - Not in first 30min of market lifetime or final 60min before resolution (pricing artefacts).
4. Look up `news_market_matches` in `[t_move_start - 60min, t_move_end]`. Record:
   - `first_matching_news_ts` (or null)
   - `news_lead_minutes = t_move_start - first_matching_news_ts` (negative = move led news)
5. Co-movement check: record any same-theme markets with `z ≥ 1` in the same window as `nearby_markets`. Two or more = theme-wide news propagation, not an isolated leak — deprioritize.
6. Rank by `news_lead_minutes` descending.

Run the same detector on control markets (Eurovision, entertainment, sports). If control markets flag at similar rate, detector isn't finding anything real.

### Sampling

- `SnapshotSampler` every 60s: bulk-fetch all tracked markets via `PolymarketAPI.get_markets_bulk`. One HTTP request per minute.
- `MarketDiscovery` every 6h: re-run slug-substring matching against gamma-api. Log new candidates to `data/candidates_new.jsonl` for manual review — do NOT auto-add to `markets.yaml` (preserves curation invariant).
- `NewsPoller` per-feed, staggered 30–120s cadence. `feedparser`. Dedup on `(source, guid)`.
- `NewsMatcher` every 30s: tokenise new news items, match against each market's keywords (≥2-keyword match required).
- `FeedHealthMonitor` every 5min: record items_received per feed; warn if any feed silent >3h.

### Storage

Single SQLite at `e10.db` (WAL enabled). Tables: `markets`, `snapshots`, `news_items`, `news_market_matches`, `feed_health`, `flagged_events`. See `watcher.py` `SCHEMA`.

## Manual review rubric

The decision gate below counts only events whose `manual_verdict` is `unexplained-by-monitored-feeds`. That verdict is only admissible when the six disqualifier checks in `MANUAL_REVIEW_RUBRIC.md` have all been explicitly ruled out, each with a written rationale in the verdict column. This is pre-committed to blunt the post-hoc pattern-matching failure mode.

## Report framing rule (pre-committed)

The report generator (`analyze.py::classify_ratio`) maps the candidate/control flag-rate ratio to a verdict sentence:

| ratio | verdict |
|---|---|
| < 1.0× | null result — control flags at or above candidate rate |
| < 1.5× | null result — no signal distinguishable from control noise |
| < 3.0× | weak signal; individual events may or may not survive the manual review rubric |
| ≥ 3.0× | candidate signal above control baseline; apply decision gate + manual review rubric to top events |

The phrase "suspicious", "consistent with informed trading", "insider-like", and "leak" are never emitted by the report generator. Strongest admissible phrasing is `unexplained by our monitored feed set`. Pre-commit this language before seeing the data.

## Pre-committed decision gate

Written here BEFORE running so goalposts don't move during analysis.

**Proceed to e11 (wallet-level forensics)** if we flag ≥3 events where all hold:
- `news_lead_minutes ≥ 15`
- `volume_delta ≥ $500`
- `z_score ≥ 3`
- `nearby_markets` is empty or single-entry (isolated, not theme-wide)
- `feeds_healthy = 1`
- Manual verdict after eyeballing: "plausible leak, not explained by social media or theme co-movement"
- Candidate-market flag rate meaningfully higher than control-market flag rate (rule of thumb: ≥3×)

**Kill the direction** if 0 events pass the above, OR top-ranked candidates all explain trivially (tweet 30s before, thin-book echo, stale price, theme-wide move), OR control markets flag at similar rate.

**Extend to a third 48h run** if 1–2 ambiguous candidates pass.

## Known pitfalls (do not forget before writing the report)

- **RSS timestamp quality.** "Move before RSS" ≠ "move before all public info". Don't overclaim.
- **Selection bias.** Markets picked for being newsworthy will see more news-timed moves. Control set is the counterweight; respect its verdict.
- **Thin-book noise.** Expect 60–80% of raw flags to be single-small-order bid-widening events. `volume_delta` filter is load-bearing.
- **Theme co-movement ≠ leak.** Iran news moves both Iran-strike and oil-above-$90 markets. Co-movement filter handles this.
- **Reputational caution.** If a market in this study involves specific individuals, do not name-and-shame in writeups — describe patterns, not accounts. Wallet-level attribution (e11) inherits 10× this concern.

## Operational

### Prerequisites

Dependencies already in `pyproject.toml`: `aiohttp`, `aiosqlite`, `feedparser`, `pyyaml`, `pandas`, `numpy`. No new deps needed.

### Build validation

```
# Confirm probe.api imports cleanly
uv run python -c "from probe.api import PolymarketAPI, now_utc_ms; print('ok')"

# Smoke run (5–10 min; 2 markets, 2 feeds)
cd experiments/e10_geo_informed_trading
uv run python watcher.py --smoke --hours 0.1
```

### Full run

```
cd experiments/e10_geo_informed_trading
nohup uv run python watcher.py --hours 48 > watcher.log 2>&1 &
disown
tail -f watcher.log
```

### Health checks while running

```
sqlite3 e10.db "select source, count(*), datetime(max(seen_ts)/1000,'unixepoch') from news_items group by source"
sqlite3 e10.db "select count(*) from snapshots"
sqlite3 e10.db "select * from feed_health order by ts desc limit 12"
```

### Analysis

```
uv run python analyze.py  # produces REPORT.md + populates flagged_events
sqlite3 e10.db "update flagged_events set manual_verdict = ? where id = ?"
```

## Explicit non-goals

- Real-time alerting / webhooks
- Wallet-level / on-chain forensics (deferred to e11, conditional on decision gate)
- Twitter / Telegram social baseline (acknowledged gap)
- Production pipeline / product pivot — v3 crypto roadmap continues unaffected

## Verification log

- 2026-04-18 — gamma-api `tag=` and `category=` params confirmed silently ignored (identical responses regardless of value). Committed to slug-substring discovery instead.
- 2026-04-18 — RSS feed probe: BBC World, Al Jazeera, Times of Israel, Kyiv Post, SCMP, NYT World, Guardian World, ABC News International confirmed returning XML. Reuters worldNews (connection refused), Reuters /world/rss (401), rsshub apnews (403), Haaretz `/srv/htz---all-headlines` (404), Kyiv Independent `/feed` (404) dropped.
