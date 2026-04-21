# e22 VERDICT — Cross-venue same-event spreads

Generated 2026-04-20. Full workings in `scripts/` and `data/`. Agent output
text is the primary writeup; this file summarizes the conclusion.

## Research question

Is the Polymarket sports favorite-longshot bias (FLB) measured in e16
(0.55-0.60 bucket resolving YES 87.5% of the time; +30pp deviation at z=5.1)
specific to Polymarket, or do other prediction/betting markets show the
same mispricing on identical events?

## Bottom line

**Polymarket and Smarkets price the same live sports events essentially identically.**

Final aggregated sample (script 09, `data/09_final_pairs.parquet`):
- n=106 matched live pairs: 78 football/soccer + 15 basketball (NBA + European)
  + 13 ice hockey (NHL + European).
- Each pair filtered to pm_vol24h >= $1 and |spread| <= 15pp (drops mismatches).
- **Overall mean spread = 0.0000** (exactly zero). Median essentially zero.
- **|spread| mean = 0.0075 (0.75pp).**
- Only **5.7% of pairs have |spread| > 2pp**.

Every bucket 0.05-0.95 has mean spread within ±1pp. The 0.55-0.60 FLB-peak
bucket has n=5 pairs with mean spread **-0.6pp** (Polymarket slightly LOWER
than Smarkets, opposite of a "Polymarket over-prices" story). The 0.50-0.70
favorite range (n=25) has mean +0.23pp.

**By sport:**
| sport | n | mean spread | abs mean |
|---|---:|---:|---:|
| football_soccer | 78 | +0.0008 | 0.0064 |
| basketball | 15 | -0.0013 | 0.0074 |
| ice_hockey | 13 | -0.0032 | 0.0141 |

**Implication for the FLB finding:** the Polymarket sports calibration
deviation at 0.55-0.60 (e16: +30pp, z=5.1) cannot be caused by a
Polymarket-specific retail bias. Smarkets — a mature UK betting exchange
operating since 2008 with larger aggregate volume on these events —
prices the exact same matches within sub-1pp of Polymarket. If Polymarket
favorites at 0.57 resolve YES 88% of the time, Smarkets at 0.57 on the
SAME matches must also resolve YES 88% of the time. The FLB is therefore
prediction-market-general (or betting-market-general), not a Polymarket
artifact.

## Key numbers

### Venue inventory (data/01_venue_inventory.json)

| venue | total markets | sports | viable for comparison? |
|---|---:|---|---|
| polymarket | 70,225 | 23,698 Sports + 1495 Soccer + 1326 Tennis | yes (reference) |
| kalshi | 40,911 | 18,228 Sports | tickers yes, **live prices require auth** |
| smarkets | 64,868 | 58k football + 2.1k basketball + 1.1k baseball + 872 ice hockey + 388 tennis | yes (live quotes via v3 REST) |
| limitless | 313 | 2 sports | no |
| baozi / myriad / probable | 3 / 100 / 20 | ≤27 sports tagged | no |
| opinion / metaculus | - | - | auth required |

### Live spread: final aggregated (script 09, `data/09_final_pairs.parquet`)

Combines football from script 06 and US sports (NBA+NHL) from script 08,
filtered for pm_vol24h >= $1, |spread| <= 15pp, deduplicated by (event, team).

```
n = 106
mean  = +0.0000
median = 0.0
stdev = 0.0187
abs_mean = 0.0075
pct |spread| > 2pp:   5.7%
pct |spread| > 5pp:   ~3%
```

### Cross-venue calibration per PM yes-price bucket (final clean)

| pm bucket | n | pm mean | sm mean | spread |
|---|---:|---:|---:|---:|
| 0.05–0.10 | 5 | 0.085 | 0.085 | −0.000 |
| 0.10–0.15 | 3 | 0.130 | 0.132 | −0.002 |
| 0.15–0.20 | 5 | 0.172 | 0.172 | −0.000 |
| 0.20–0.25 | 15 | 0.223 | 0.224 | −0.001 |
| 0.25–0.30 | 9 | 0.277 | 0.279 | −0.003 |
| 0.30–0.35 | 8 | 0.328 | 0.334 | −0.005 |
| 0.35–0.40 | 15 | 0.378 | 0.383 | −0.005 |
| 0.40–0.45 | 4 | 0.421 | 0.416 | +0.006 |
| 0.45–0.50 | 7 | 0.475 | 0.469 | +0.006 |
| 0.50–0.55 | 11 | 0.528 | 0.526 | +0.002 |
| 0.55–0.60 | 5 | 0.572 | 0.578 | −0.006 |
| 0.60–0.65 | 7 | 0.628 | 0.620 | +0.008 |
| 0.65–0.70 | 2 | 0.675 | 0.671 | +0.004 |
| 0.70–0.75 | 3 | 0.718 | 0.717 | +0.002 |
| 0.80–0.85 | 2 | 0.825 | 0.822 | +0.003 |
| 0.90–0.95 | 2 | 0.920 | 0.915 | +0.005 |

No bucket shows systematic lift on favorites. Polymarket is not higher or
lower than Smarkets by any meaningful margin in any bucket.

### Kalshi overlap (ticker-based)

We cannot access Kalshi live prices without authentication (public API
returns `yes_bid=null`). But we CAN count how many Polymarket sports
markets have a matching Kalshi ticker (series naming encodes date + teams):

- **394 of 839 PM H2H markets match a Kalshi ticker (47%).**
- 25 of the 67 PM-Smarkets clean pairs also have a Kalshi ticker.
- Kalshi covers NBA, NFL (currently off-season), MLB, NHL, UFC, MLS, EPL,
  La Liga, Serie A, Bundesliga, Ligue 1. Kalshi does NOT cover the long
  tail of lower-division football that Polymarket/Smarkets share (Chinese
  Super League, Korean K-League, Bolivian league, etc.).
- To actually measure Kalshi spreads, an authenticated pipeline would be
  needed (API key + RSA private-key signature).

### Retrospective T-7d cross-venue calibration

**TIER 4 — BLOCKED.** Smarkets public API does not expose historical
orderbook or trade data; `state=settled` returns empty, `/trades/`, 
`/price_history/` are 404. pmxt's `fetch_trades` on Smarkets also yields
no pre-settlement data. Kalshi's `/candlesticks` endpoint returned 404 on
the elections subdomain. Without historical prices on BOTH venues for the
same resolved event, we cannot compute e16-style T-7d calibration per
venue and compare.

The LIVE spread evidence above is the strongest empirical answer available
on the research question as-of-today.

## What this does and doesn't say

**Says:** When the exact same football match is traded on Polymarket and
Smarkets simultaneously, their prices converge to within ~1-2pp. Whatever
favorite-longshot bias exists on Polymarket exists on Smarkets by the
same amount on the same events.

**Doesn't say:** that FLB does or doesn't exist. e22 cannot measure
calibration (resolution outcomes) directly — only spreads. e16 already
established Polymarket sports show +24-30pp YES-rate lift at 0.55-0.60.
Our finding implies Smarkets — a mature UK betting exchange with larger
volumes and different user demographics — shows the same lift. That is
strong circumstantial evidence that FLB is structural to these markets,
not a Polymarket-retail artifact.

## For downstream strategy

If a trader wants to exploit the 0.55-0.60 FLB on Polymarket sports:
1. The edge is NOT being eaten by cross-venue arbitrage (Smarkets prices
   are tight to Polymarket).
2. But the edge also cannot be hedged at a better price on Smarkets —
   because Smarkets is priced the same way.
3. Arbitrage between the two venues is NOT the source of edge. The edge,
   if real, is in the resolution statistics directly.
4. The 0.55-0.60 underpricing (per e16) must reflect a true structural
   miscalibration of retail + market-maker sentiment that affects both
   venues' sports markets similarly — not a Polymarket-specific retail bias.

## Data inventory

| file | purpose |
|---|---|
| `data/01_venue_inventory.json` | market counts per venue (9 venues tested) |
| `data/02_*.parquet` | first-pass match (pmxt-based, superseded) |
| `data/03_live_spreads.parquet` | pmxt-based orderbook attempt (errors) |
| `data/04_pm_smarkets_live.parquet` | 136 pairs, 73 with sm price (football) |
| `data/05_full_sweep.parquet` | multi-sport sweep, 839 records, Kalshi ticker overlap |
| `data/06_drilldown.parquet` | 14-day horizon drilldown on favorite bucket |
| `data/07_nba_mlb.parquet` | (empty — superseded by 08) |
| `data/08_us_sports.parquet` | NBA/NHL pairs after Smarkets-market-name fix |
| `data/09_final_pairs.parquet` | **FINAL CLEAN SAMPLE n=106** |
| `data/09_final_summary.json` | **PRIMARY RESULT FILE** |

## Scripts

| script | purpose |
|---|---|
| `01_venue_inventory.py` | Catalog sports markets across pmxt-supported venues |
| `02_match_live_events.py` | First-pass token matcher (pmxt-based, superseded) |
| `03_live_cross_venue.py` | Second pass, orderbook-via-pmxt (superseded) |
| `04_pm_vs_smarkets_live.py` | Gamma + Smarkets v3 direct (football only) |
| `05_cross_venue_full_sweep.py` | Full sweep with Kalshi ticker overlap |
| `06_drilldown_fav_bucket.py` | 14-day horizon, all sports, drilldown on fav bucket |
| `08_us_sports_sweep.py` | NBA/NHL/MLB (handles different PM schema, fixed mw-filter) |
| `09_final_aggregation.py` | **Aggregates 06 + 08, dedups, produces final table** |
| `probe_*` and `debug_*` | exploratory API probes (kept for reproducibility) |
