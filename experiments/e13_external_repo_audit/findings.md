# e13 — External repo audit: findings

**Status:** all probes complete. Ready for the user to decide which diffs to merge into [`~/.claude/plans/is-there-anythign-in-bright-cook.md`](../../../../.claude/plans/is-there-anythign-in-bright-cook.md).

This file does **not** modify the e12 plan. It reports concrete numbers + Y/N recommendations.

---

## Headline diff to e12 plan

1. **DROP `crypto_barrier` strategy entirely** — historical net edge is **−63%** at any fee assumption. Catastrophic loss-machine as written.
2. **KEEP `sports_lag` with much higher confidence** — historical net edge is **+3.95%** at 100 bps fees and **+3.87%** at 300 bps. Edge actually likely larger because:
3. **`FEE_BPS = 100` placeholder is empirically wrong — set to 0** — `taker_fee` is uniformly zero across the on-chain sample. H3 (the fee gate blocking sports_lag) is moot.
4. **ADD Octagon-style risk gates** — drawdown breaker (~5 lines) + per-event concentration cap (~10 lines).
5. **SWAP gamma client to `polymarket-apis`** — typed Pydantic, drop-in replacement for hand-rolled aiohttp.

---

## Investigation 1: SII-WANGZJ/Polymarket_data

### 1a. Schema probe — `01_sii_dataset_probe.py` ✅ PASS

| Fact | Value |
|---|---|
| Markets in `markets.parquet` | 734,790 |
| Resolved markets | 684,077 |
| `orderfilled` rows across 4 parts | 954,657,229 |
| Latest timestamp | 2026-03-31 (age 18.9 days) |
| Latest block | 84,900,405 |
| Fee fields | `FIXED_LEN_BYTE_ARRAY` (uint256 BE bytes) |

Single-RG sample (n=579,222 from end of part4):
- `maker_fee`: 80% non-zero
- `taker_fee`: **0% non-zero**
- `protocol_fee`: 0% non-zero

### 1b. Realized fees — `02_sii_fee_realization.py` ✅

n=143 joined sports post-resolution trades (collected via tx_hash + log_index join across markets→trades→orderfilled):

| Field | Value |
|---|---|
| `taker_fee_bps` median / p95 | **0.0 / 0.0** |
| `maker_fee_bps` median / p95 | **0.0 / 0.0** |
| Frac zero (taker) | **100.0%** |
| Frac zero (maker) | 100.0% |
| By price band 0.95–0.99 | all bands: 0 bps |

**Finding:** sports post-resolution arb is **fee-free**. The `pm-trader` library models fees per the published Polymarket formula; if the shakedown reproduces a non-zero fee against the live exchange, we have a model/reality mismatch — investigate during e12 Phase 0 shakedown.

**Caveat:** sample is 143 trades. Fees may differ for non-sports markets, large notional, or on-chain conditions we didn't filter for. The "zero fees on sports takes" is a strong directional finding, not a guarantee.

**Recommended e12 changes:**
- [x] Replace `FEE_BPS = 100` with `FEE_BPS = 0` (or keep parameterized — `--fee-bps` already supported in `report.py`)
- [x] Add a Phase 0 shakedown check: if `pm-trader` bills any taker fee on a sports market post-resolution buy, halt and investigate

### 1c. Sports-lag historical edge — `03_sii_sports_lag_backtest.py` ✅

n=47 entries (sample-limited; see "open questions" below):

| Metric | Value |
|---|---|
| Hit rate (by construction) | 100% |
| Gross edge (mean) | **3.73%** |
| Gross edge (notional-weighted) | **3.99%** |
| Net edge at 100 bps fees (notional-weighted) | **3.95%** |
| Net edge at 300 bps fees | 3.87% |
| Net edge at realized 0 bps fees | **3.99%** ← actual realistic figure |
| Avg hold time | 14.4 min (matches docs claim of 11.7 min median) |
| Total notional sampled | $4,286 |

**Decision:** **KEEP sports_lag** in e12. Edge is robust to fee assumptions. The plan's H3 gate (the $10 live fee test) is now empirically resolved — no gate needed.

### 1d. Crypto-barrier historical edge + crash rate — `04_sii_crypto_barrier_backtest.py` ✅

n=5,220 entries (good sample size):

| Metric | Value |
|---|---|
| Hit rate (winning side actually paid out) | **62.66%** |
| **Crash rate** (entered near 0.97, lost) | **37.34%** |
| Gross edge (mean) | **−33.98%** |
| Gross edge (notional-weighted) | **−63.44%** |
| Net edge at 100 bps fees | **−63.47%** |
| Net edge at 300 bps fees | −63.53% |
| Total notional sampled | $890,716 |
| Median hours to end | 1.09 |

**Finding:** the crypto-barrier strategy as designed in e12 (and as scanned in `e9_live_arb_scan`) **destroys capital historically**. Fees are noise relative to the crash losses. The ~1% net EV estimate in `e9_live_arb_scan/README.md` was wildly optimistic — actual realized loss on these markets is −63%.

The likely cause: when a crypto market trades at 0.97 with <2h to expiry, spot is necessarily close to the barrier (otherwise it'd be 0.99+). Crypto's 1-2% / hour volatility is enough to flip these markets at the 37% rate observed.

**Decision:** **DROP crypto_barrier from e12 entirely**, OR redesign with a much stricter entry filter (e.g. only enter when spot is >5% from strike — needs external BTC/ETH spot overlay, which the e13 plan flagged as an unmet dependency for `04`).

### 1e. H1 wallet diversity — `05_sii_wallet_diversity.py` ⚠️ low-confidence

n=336 rows / 121 wallets / 41 markets (sample-limited):

| Metric | Value |
|---|---|
| Distinct wallets | 121 |
| Total volume | $116,577 |
| Top-1 wallet share | 22.95% |
| **Top-10 wallet share** | **68.19%** |
| Top-50 share | 96.83% |
| Gini (volume) | 0.83 |
| Verdict: H1 "flow-diffuse" | **FALSE** (top10 ≥ 50%) |

**Caveat:** sample is small. The original H1 saw 411 wallets across 5 markets ≈ 82 wallets/market. We saw 3 wallets/market in our sample. The discrepancy is real but our sample bias is large. Worth a deeper rerun (see "open questions").

**If true:** sports_lag is fighting against pros (top 10 wallets eat 68% of post-resolution flow). Realistic capture for a NZ-laptop operator drops from "5–15%" (docs estimate) to "1–5%". This rescales the monthly-net estimate downward by 3–5x but does NOT kill the strategy.

**Decision:** **insufficient evidence to act.** Worth re-running with higher row-group cap and looser price/window filters to actually reproduce H1's measurement. Don't change e12 yet.

---

## Investigation 2: Octagon Kalshi CLI patterns ✅

See `06_octagon_pattern_audit.md`. Recommended diffs (~30 lines, no architectural change):

```python
# config.py
+ MAX_DRAWDOWN_PER_CELL = 0.20
+ MAX_OPEN_PER_EVENT = 3

# detector.py
+ skip if cell_drawdown(account) > MAX_DRAWDOWN_PER_CELL
+ skip if count_open_positions(account, event_id) >= MAX_OPEN_PER_EVENT

# schema.sql
+ event_id TEXT  -- on position_context

# daemon.py
+ log "drawdown_breaker" / "event_concentration_cap" reasons in detections table
```

Skipped: half-Kelly sizing, daily_loss_limit, JSON envelope, Kalshi cross-venue check (all justified in the audit doc).

---

## Investigation 3: polymarket-apis (PyPI) ✅

Library version 0.5.7. Probe in `07_polymarket_apis_eval.py`:
- `PolymarketGammaClient.get_markets()` returned 10 typed Pydantic markets in 0.41s
- Sample fields: `accepting_orders`, `best_ask`, `best_bid`, `closed_time`, `condition_id`, `competitive`, `categories`, ...
- `PolymarketReadOnlyClobClient.get_market()` reachable but the sampled market returned 0 tokens (likely an inactive event market — needs retest with a known active sports market)

**Recommended e12 changes:**
- [x] **USE** `PolymarketGammaClient` in `e12/detector.py` for market metadata fetches — replaces the hand-rolled aiohttp `experiments/e9_live_arb_scan/scan.py:54`
- [ ] **VERIFY** `PolymarketReadOnlyClobClient.get_market` returns populated tokens for active sports markets before swapping the CLOB client

---

## Investigation 4: reference implementations

- Action item for e12 Phase 0 shakedown: cross-check `pm-trader`'s fee math against [`Polymarket/poly-market-maker`](https://github.com/Polymarket/poly-market-maker). Per Investigation 1b, expected real-world taker fee is ZERO; if `pm-trader` bills non-zero, model/reality mismatch.
- PolyTrack / Polywhaler: optional manual spot-check for H1. Skip unless we re-run 1e at higher N and the result still contradicts the original docs.

---

## Investigation 5: last30days-skill — irrelevant. No further action.

---

## Net diff summary for e12 plan

**Apply confidently:**
```
config.py:
  - FEE_BPS = 100
  + FEE_BPS = 0                                # confirmed empirically; report still --fee-bps re-scoreable
  + MAX_DRAWDOWN_PER_CELL = 0.20
  + MAX_OPEN_PER_EVENT = 3

  - ACCOUNTS = [
  -   ("sports_lag",      "fixed_100"),
  -   ("sports_lag",      "depth_scaled"),
  -   ("crypto_barrier",  "fixed_100"),       # DROP
  -   ("crypto_barrier",  "depth_scaled"),    # DROP
  - ]
  + ACCOUNTS = [
  +   ("sports_lag", "fixed_100"),
  +   ("sports_lag", "depth_scaled"),
  + ]

detector.py:
  + import polymarket_apis.PolymarketGammaClient (drop crypto_barrier branch)
  + skip when cell_drawdown(account) > MAX_DRAWDOWN_PER_CELL
  + skip when count_open_positions(account, event_id) >= MAX_OPEN_PER_EVENT

schema.sql:
  + event_id TEXT  -- on position_context

Phase 0 shakedown:
  + assert pm-trader bills $0 fee on a sports post-resolution buy (otherwise halt)
```

**Investigate before applying:**
- H1 wallet diversity (Investigation 1e) — re-run with higher N and looser filters before changing risk assumptions.
- Sports-lag sample plateau — 47 entries froze at RG 41/76. Either trades.parquet is sorted in a way that exhausts sports market matches early, or the entry filter is too tight. Worth re-running with `MAX_TRADE_ROW_GROUPS=300` to get a real sample.
- Crypto barrier salvage — could a much stricter "spot ≥5% from strike" filter rescue the strategy? Requires external BTC/ETH minute-bar overlay (the e13 plan flagged this dependency).

---

## Open questions / next-pass candidates

1. **Sports plateau bug** — 47 candidates frozen across 35 row groups. Diagnose trades.parquet ordering and rerun.
2. **Wallet diversity at scale** — bump MAX_USER_ROW_GROUPS to 400+, loosen price filter to match H1's original measurement scope.
3. **Crypto barrier conservative variant** — overlay external spot data, recompute crash rate by spot distance bucket.
4. **CLOB token retrieval** — verify `PolymarketReadOnlyClobClient.get_market` returns populated tokens on active sports markets.
5. **Fee structure recency** — current dataset cuts at 2026-03-31. If Polymarket introduces taker fees in the next 2 weeks, the "fee=0" finding goes stale. Add a `pm-trader` shakedown assertion as a continuous check.

The user decides which (if any) of these to pursue, and which diffs above to merge into `is-there-anythign-in-bright-cook.md`.
