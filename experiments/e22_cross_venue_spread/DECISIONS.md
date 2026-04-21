# e22 Decisions log — cross-venue same-event spreads

## 2026-04-20: Venue inventory first, then triangulate

Before measuring spreads, need to know which venues have enough sports market
inventory to even have overlap with Polymarket. Ran `scripts/01_venue_inventory.py`
hitting pmxt 2.31.1 across all supported venues.

**Result:**
- Polymarket: 70k markets, 23,698 in Sports category (NBA 910, NFL 555, football 2047, MLB 811, NHL 857)
- Kalshi: 41k markets, 18,228 in Sports (NFL 249, football 2252, NHL 172)
- Smarkets: 65k markets, 58,391 football, 2146 basketball, 1172 cricket, 1115 baseball
- Limitless: 313 markets, mostly crypto hourly binaries; 1 nba, 1 nfl
- Baozi: 3 markets; venue not viable for sports overlap
- Myriad: 100 markets, 27 tagged sports, mostly futures (Worlds, La Liga)
- Probable: 20 markets, all US-politics-futures
- Opinion: 401 — auth required
- Metaculus: auth token required

**Viable overlap venues for sports: Polymarket <-> Kalshi <-> Smarkets.**
Limitless/Myriad/Probable have too little inventory; skip for now.

## 2026-04-20: Matching strategy for overlapping events

The hard problem is that the SAME real-world event (e.g. Lakers vs. Warriors
on 2026-04-22) is represented differently on each venue. Polymarket titles
look like "Lakers vs. Warriors — Will the Lakers beat the Warriors?", Kalshi
uses short codes, Smarkets uses "Team A v Team B" format.

Approach:
1. For Polymarket & Kalshi & Smarkets, filter to NBA/NFL/MLB/NHL/soccer markets
   with a near-future resolution_date (within 7 days).
2. Extract team tokens from titles (lowercase, strip "vs"/"v"/"x"/"at", drop
   "the", keep tokens >=3 chars).
3. Match pairs by (set-of-team-tokens, resolution_date within 24h).
4. For matched triples, fetch current YES-equivalent price on each venue and
   compute pairwise spreads.

## 2026-04-20: YES-equivalent price definition

Each venue reports market outcomes differently. Using pmxt `UnifiedMarket.yes`
when present; else use outcome[0].price as YES. For soccer where 3-way
markets exist (home/draw/away), skip the draw binary for now and match on
"who wins" as home-team YES.

## 2026-04-20: Historical / T-7d retrospective

pmxt does not expose a clean archive of resolved markets with T-7d price
history. `fetch_ohlcv` exists on each exchange — try that for resolved
markets; if empty or no history, fall back to "current snapshot" only and
flag the retrospective arm as Tier 3.

## 2026-04-20: Fixed random seed 42

All sampling/ordering uses random_state=42 for reproducibility, matching e16.

## 2026-04-20: pmxt live prices do NOT work uniformly

`pmxt.Polymarket.fetch_markets()` returns real live prices inside outcomes.
`pmxt.Kalshi.fetch_markets()` returns only metadata (price=0, vol=0) — live
prices require auth (RSA key pair). Kalshi public REST `/markets` also
returns `yes_bid=null`, `yes_ask=null`. `/markets/{ticker}/orderbook` returns
only an `orderbook_fp` fingerprint, not the book itself.

`pmxt.Smarkets.fetch_markets()` similarly returns 0-valued prices. Live
prices ARE obtainable via direct Smarkets v3 REST API:
`GET /markets/{id}/quotes/` returns per-contract `bids` and `offers` with
prices in basis-points-of-percent (5319 = 53.19%).

Decision: abandon pmxt client for live data. Use direct APIs:
- Polymarket: `https://gamma-api.polymarket.com/markets`
- Smarkets: `https://api.smarkets.com/v3/events/|markets/|quotes/`
- Kalshi: UNREADABLE without API key. Use ticker-name parsing only to
  count overlap, not to measure spread.

## 2026-04-20: Smarkets market-name filter (bug & fix)

Initial "match-winner" filter caught `"half-time/full-time"` as a winner
market (because `"full-time" in nm` matched). That parlay market's
contracts have completely different price semantics, producing fake
spreads up to 48pp for NBA games.

Fix in script 08: match whitelist of exact names (`"winner"`, `"winner
(including overtime)"`, `"match odds"`, `"moneyline"`, `"full-time
result"`, `"result"`, `"game winner"`) and exclude parlay-variant names
containing "over/under", "handicap", "spread", "points".

## 2026-04-20: Polymarket market schema varies by sport

- **Football/soccer**: one market per team-to-win, question="Will X win",
  outcomes=["Yes","No"], Yes price = team win probability.
- **NBA/MLB/NHL/NFL** (US game-winner markets): question = event title,
  outcomes = ["TeamA","TeamB"], outcomePrices = [team_A_prob, team_B_prob].

Extracting team prices for US sports requires the 2nd path (outcome label
is team name).

## 2026-04-20: retrospective T-7d not possible (TIER 4 on that arm)

Smarkets public v3 API does not expose settled/past events (`state=settled`
returns empty, `state=resolved` returns 400) nor any historical price
endpoint (`/trades/`, `/price_history/`, `/history/` all 404). Kalshi
public API has no candlestick endpoint on elections subdomain. Therefore
the "per-venue T-7d calibration against resolution" arm cannot be
completed with public data.

## 2026-04-20: vol-filter for matching noise

Many PM sports markets have vol=0 and show default 50/50 prices from
liquidity-free fill. Filter to pm_vol24h >= $1 to drop these pairs before
computing spread statistics.
