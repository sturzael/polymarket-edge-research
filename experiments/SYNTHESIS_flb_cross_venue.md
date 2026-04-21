# Cross-venue FLB synthesis — e18 to e22

**Date:** 2026-04-20
**Source experiments:** e16 (Polymarket baseline), e18 (Drift), e19 (Baozi), e20 (Azuro), e21 (Betfair), e22 (cross-venue spread). Agent 1 / e17 (PMXT cross-venue) was run separately by the user and is not reflected here.

## Research question

The e16 calibration study found a statistically significant favorite-longshot bias on Polymarket **sports** markets at T-7 days: 0.55–0.60 bucket → 87.5% yes_rate (+30pp, z=5.1, n=32/628 sports). We spawned 5 parallel sub-agents to test whether this bias is Polymarket-specific, sport-specific, prediction-market-general, or betting-market-general.

## Headline comparison at the critical 0.55–0.60 bucket

| Venue | Anchor | n (in bucket) | yes_rate | deviation | z |
|---|---|---:|---:|---:|---:|
| **Polymarket sports** (e16) | T-7d | 32 | 0.875 | **+30.0pp** | **+5.12** |
| Azuro AMM (Polygon, e20) | close-time | 151,962 | 0.579 | +0.4pp | +2.8 |
| Azuro AMM (Gnosis replication, e20) | close-time | large | ~0.58 | ~+0.4pp | similar |
| Betfair AU sports (e21) | T-60min | 578 | 0.555 | −2.0pp | −0.96 |
| Betfair AU sports (e21) | T-1min | 549 | 0.519 | −5.6pp | −2.65 |
| Betfair horse racing (e21) | BSP | 121 | 0.595 | +2.0pp | +0.45 |
| Betfair football (e21) | pre-kickoff | 734 | 0.563 | −1.2pp | −0.68 |
| Drift Solana (e18) | T-7d | 1 | n/a | n/a | — |
| Baozi (e19) | — | 0 (probe blocked) | — | — | — |
| Smarkets live, same events (e22) | current live | 5 pairs | matches Polymarket ±0.6pp | — | — |

## What the data says

### 1. Polymarket is an outlier *as measured against resolutions*

Two independent large-n venues — Betfair (73k+ selections, traditional exchange) and Azuro (1.86M outcome-rows, on-chain AMM) — both measured FLB against actual resolution outcomes and found essentially **zero bias at 0.55-0.60**. Max Betfair deviation ±6pp across 4 different anchors/sports. Max Azuro deviation +3pp anywhere in its curve. Polymarket's +30pp is 5-75× larger than any comparison venue's measured bias.

### 2. But Smarkets live prices agree with Polymarket within sub-1pp

On n=106 current live sports matches traded on both venues, Polymarket and Smarkets agree within 0.75pp on average. Direct arbitrage would not have flattened this to zero — so it is likely that retail / sharp flow on both exchanges is converging on the same expectations. This *appears* to contradict Betfair and Azuro.

### 3. The resolution of the apparent contradiction: **anchor mismatch**

This is the critical piece:

- **Polymarket +30pp was measured at T-7d.** No other large-sample venue offers liquid T-7d pricing on sports:
  - Azuro: only 0.1% of conditions had bets 7 days before start (e20 structural check).
  - Betfair: markets open 24-48h pre-event; "Betfair sports markets don't have liquid T-7d prices" (e21 caveat).
  - Drift: no new sports listings in 5 quarters; sports bucket essentially empty (e18).
- **Betfair/Azuro measurements were at T-60min / pre-kickoff / close-time** — much closer to the event, when prices have had time to converge toward truth.
- **Smarkets agreement is on "live" events at unknown T-minus** — could be near-close, could be days out, mixed.

So the cross-venue comparison tells us two compatible things at different anchors:
- **Near-close (T-60min to close): essentially no FLB on any venue tested.** Betfair ≤±6pp, Azuro ≤+3pp.
- **At T-7d on Polymarket sports: +30pp.** Cannot be directly replicated on other venues because they don't list that early.

### 4. Smarkets agreement needs careful interpretation

Agent 6's deductive step — "if Polymarket at 0.57 resolves YES 88%, Smarkets at 0.57 on the same events must too" — is tautologically correct for whatever matched sample it used. But:
- n=5 in the 0.55-0.60 bucket (vs 32 in e16).
- "Live" events measured at mixed T-minus times, not systematically at T-7d.
- Agent 6 could not do the retrospective arm (Smarkets public API returns no price history).

Smarkets may or may not show Polymarket's T-7d bias at the same anchor. We can only say: at whatever anchor they were currently priced, they agreed.

## Meta-verdict

**The Polymarket sports +30pp FLB at T-7d is a specific combination of venue × timing, not a universal betting-market phenomenon.** The evidence:

- *Against universality*: Betfair and Azuro both measure near-zero FLB against actual resolutions at their available anchors. Together this is ~1.9M resolution events showing no +30pp-scale effect at any price level anywhere in their curves.
- *For Polymarket-specificity at T-7d*: the effect exists on Polymarket at T-7d (e16). No comparison venue offers T-7d liquidity on sports so we cannot directly disprove that Smarkets / Betfair / Azuro would also show it at T-7d if they listed that early.
- *For cross-venue current-state agreement*: Polymarket and Smarkets price the same events identically right now. This suggests that whenever both are active on an event, prices are arbitraged / informed to the same level.

**Most likely mechanism:** the +30pp at T-7d on Polymarket sports reflects a period where retail flow dominates thin early liquidity, before sharper market-makers / late information converge the price toward truth. This would be consistent with:
- Polymarket's lower overall liquidity vs Betfair.
- Short-horizon venues (Azuro, Betfair) not experiencing the effect because they don't trade at T-7d.
- Polymarket's "0.50 cliff" (31pp discontinuity across the 0.50 bucket on e16) not replicating on Azuro's 1.86M-row curve.

## Tradability implications

- The ~25-30pp excess vs any comparison venue is Polymarket-specific at T-7d on sports. It's potentially tradeable **on Polymarket in isolation** ("buy favorites at T-7d when price is 0.55-0.60") — this matches e16 section 2f's suggestion.
- **It is NOT arbitrageable against Betfair**: Betfair doesn't offer liquid T-7d sports pricing, so there's no opposing side to hedge against.
- **It is NOT arbitrageable against Smarkets** at current live prices: they agree.
- Worth forward-testing: does the bias survive Polymarket's own 4bps + gas fee stack? e16's section 2f has the numbers.

## Secondary findings

- **Azuro has no "0.50 cliff"** (e20): Polymarket's 31pp discontinuity across 0.50 is unique. This argues for a Polymarket-specific bucketing or trader-base artifact rather than a universal sports-betting pattern.
- **AMM hypothesis rejected** (e20): on-chain AMMs don't inherit uncorrected FLB. Azuro's data-provider-seeded odds + informed LPs fade retail flow effectively.
- **Pari-mutuel hypothesis untestable at scale** (e19): Baozi is too thin to measure, though protocol-level probe pipeline is ready.
- **Drift is dormant** (e18): 15 markets lifetime, 94% volume in 2 election contracts, zero new listings in 5 quarters. Deprioritize.
- **Azuro indexing stopped ~2025-05-08** (e20): future work would need to find a newer subgraph or migrate to whichever indexer Azuro now uses.
- **Kalshi measurement blocked** (e22): requires API key + RSA signature; ticker-level overlap exists (394/839 Polymarket H2H sports markets have matching Kalshi tickers) but live prices not accessible via public API.

## Open questions for future work

1. **Polymarket's own close-time calibration.** If Polymarket's +30pp at T-7d converges toward zero by close, that confirms the anchor-timing hypothesis and rules out a retail-base artifact. Achievable from existing gamma `/trades` data.
2. **Polymarket vs Betfair on the narrow set of sports where Betfair has 48h+ pre-kickoff liquidity.** Tennis / football majors sometimes do. If Polymarket at T-2d is still +20pp while Betfair at T-2d is near zero, that isolates the Polymarket-retail-dominance effect more precisely.
3. **Kalshi authenticated read.** The same-event cross-venue measurement with a proper API key + signature would give the cleanest near-close comparison on US sports.
4. **Smarkets historical arm.** Settled-market history isn't returned by the public v3 API but may be available via paid feeds or scraped archives.

## Agent-level environment issues worth noting

- **Background sub-agents could not `git commit`** in this harness (permission blocked). Agent 5 (Betfair) was the only one that successfully committed — and it swept up Agent 2's staged e18 files as a side effect. All other agents' artifacts are on disk, uncommitted.
- **Write to FINDINGS.md / VERDICT.md was blocked** for several agents; they returned their reports as text and the parent session persisted them to disk.
- **Agent 3 (Baozi) could not run Bash / npm install / RPC calls at all** — delivered a scouting report based on MCP source-code reading only. Probe pipeline is scripted and runnable locally.
- Root `pyproject.toml` gained `pmxt>=2.31.1` during the run — worth reviewing whether this should stay.
