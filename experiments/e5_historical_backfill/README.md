# e5 — Historical backfill spike

**Question:** Can CLOB serve historical resolved markets so we can skip waiting for the probe?

**Method:** A series of one-off spike queries (output in `spike.txt`):
- Gamma `/markets?closed=true` paginated — no updown markets returned
- Gamma `/markets?archived=true` — no updown markets
- Gamma `/events` with various filters — no updown markets
- CLOB `/markets` paginated — scanned 10,000 markets across 10 pages, **zero** updown
- CLOB `/markets/<cid>` on our own freshly-resolved cids — works perfectly, `tokens[].winner` preserved
- `data-api.polymarket.com/trades?market=<cid>` — works, returns 648-1000 trades per 5m market

## Findings

**CLOB /markets/\<cid\> retains the resolution signal indefinitely (at least tested up to 17.8 min post-resolution, no ceiling found).** All three probed cids matched outcome between CLOB and our probe.

**data-api /trades has full per-market history.** For one BTC 5m market: 1000 trades spanning its ~5-min lifetime (range 1776479068–1776479206, roughly 02:24:28–02:26:46 UTC).

**BUT — there is no way to enumerate old updown conditionIds.** Both gamma's and CLOB's paginated `/markets` listings filter out the `*-updown-*m-*` series entirely. The only way to learn a conditionId is at the moment of market creation (via gamma's `active=true&closed=false` listing, which is what our probe does).

## Implication — reframes v2 architecture

The probe's **real value is enumeration, not price data.** Once we've logged a conditionId + nominal_end_ts, we can pull complete price/trade history retroactively via `data-api.polymarket.com/trades` and resolution via CLOB `/markets/<cid>`, at any later time.

This means:
- **The 1Hz intensive sampler the plan called for is not needed for data collection.** We can reconstruct the full trade stream after the fact from data-api.
- **Storage reduces to:** `{conditionId, slug, duration_s, underlying, nominal_end_ts, resolution_source, discovered_at}`. ~200 bytes per market × ~5000 markets/day = ~1MB/day.
- **The intensive sampler IS still needed for live trading** (latency-sensitive decisions), but that's a v3 concern, not v2.

This also means we can validate the full calibration study against markets the probe has already captured, without waiting for the full 24h run — as soon as we have ~100 resolutions we can start the study.

## Open items
- Find an enumeration path for historical updown cids (Polymarket subgraph on The Graph? Polygon on-chain event scan? scraping polymarket.com/markets?) — would unlock ~30 days of backfill at 5000/day = 150k historical resolutions.
- Measure CLOB/data-api retention depth by querying the oldest trades we can find.

## Status
Spike complete. Not a full backfill implementation — reframed as "enumeration, not storage" insight.
