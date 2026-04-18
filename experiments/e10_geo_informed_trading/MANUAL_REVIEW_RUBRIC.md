# e10 manual review rubric

**Pre-committed before analyzing any data.** Every flagged event must be tested against each disqualifier below. If ANY disqualifier applies, the `manual_verdict` must be one of the disqualifier labels — not "plausible leak". "Plausible leak" is only an allowed verdict when all six disqualifiers have been explicitly ruled out.

This rubric exists because, during manual review, humans (including the reviewer) tend to label events "plausible leak" when the narrative is compelling and "explained" when they're tired. The rubric forces a specific negative-ruling-out pass before any positive label.

## Disqualifiers

### 1. `thin-book-noise`
The move was driven by a single small order or a narrow series of orders that don't reflect informed-trading flow.

Test: `volume_delta` in the flagged window, broken down into per-5min buckets if possible, shows one dominant burst followed by no activity. Or: order book depth at the pre-move price (captured in future runs via CLOB book snapshot) was thin enough that $500 of volume would mechanically move ≥3σ.

### 2. `theme-co-movement`
Another market in the same theme moved ≥1σ in the same window. The `nearby_markets_json` column already records this; if non-empty with ≥1 entry at z ≥ 1.0, the flag is not isolated.

Test: `nearby_markets_json` length ≥ 1. Label the verdict `theme-co-movement` and move on.

### 3. `unmonitored-source-broke-first`
A news item appeared AFTER the move on our feeds, but a public-but-not-monitored source (major Twitter/X account, Telegram channel, Reddit thread, government press page, a wire service we don't scrape) had the story before our move window.

Test: manually search Twitter/X and Google News for 2–4 of the market's keywords, restricted to the 4h preceding the move. If *anything* public predates the move by more than 2 minutes, disqualify. If you can't close this gap (Twitter search is unreliable), label `unmonitored-source-unverifiable` and count it as a disqualifier for decision-gate purposes.

### 4. `market-artefact`
The move is a known market-design artefact: market just opened (<30min), market is in final 60min before resolution, UMA/Polymarket resolution-criteria dispute was posted to Discord or the market description, or the market was re-keyed/renamed.

Test: check the condition_id on polymarket.com for recent dispute discussion or criteria clarification around the flag window. Also check that the exclusion windows in `analyze.py` actually fired (start_ts + 30min / end_ts - 60min).

### 5. `quote-widening-only`
The price move reflects a bid/ask widening (e.g. best_bid dropping from 0.20 to 0.15 while best_ask stays at 0.25) rather than actual trades. `mid` drops but no one was transacting; `lastTradePrice` unchanged; volume_24hr barely ticked.

Test: compare `mid` trajectory in the window to `last_trade_price` trajectory and per-window `volume_delta`. If `last_trade_price` barely moved and `volume_delta < $200`, disqualify.

### 6. `reference-market-correlation`
A related but non-event market moved in sync (e.g. oil-above-$90, S&P-above-X) due to broader market conditions — macro risk-on/off moves push geopolitical markets mechanically even when no news broke.

Test: during manual review, pull 1-2 reference market prices (oil futures front-month via public source, VIX, SPX) for the flag window. If they moved more than 1σ of their own daily range, disqualify.

## The only allowed positive verdict

`unexplained-by-monitored-feeds` — every disqualifier has been explicitly ruled out. Even this phrasing is deliberately conservative. Do NOT use `suspicious`, `consistent with informed trading`, `insider-like`, or `leak` as verdicts. The REPORT.md framing rule (see `analyze.py`) enforces the same language in the generated report.

## Counting for the decision gate

A flag counts toward the ≥3-events threshold only if:
- `manual_verdict == 'unexplained-by-monitored-feeds'`
- AND the event was on a candidate (non-control) market
- AND all six disqualifiers have a written rationale in the verdict comment

If any of those fail, the flag is a disqualifier-labeled event and does not count. This is the point of pre-committing the rubric: the language rationale lives next to the verdict, so a later re-read can check the work.
