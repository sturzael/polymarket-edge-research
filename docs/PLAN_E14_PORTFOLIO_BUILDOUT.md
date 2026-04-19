# Path forward: $1k → growable bankroll on Polymarket

**Successor to** `PLAN_E12_PAPER_TRADE.md`. The e12 paper-trade harness still runs — this plan reframes what we're optimising for and brings in the strategies the synthesis surfaced.

## Reality after the e13 audit + 24h of e12 live observation

The e13 backtest confirmed a +3.99% net edge on sports settlement-lag at 0.95–0.97 entries (n=47, sample-thin). The first 24h of running e12 against the live exchange added two empirical observations the backtest could not see:

1. **The 0.95–0.97 entry zone is empty in real time.** Of 723 currently-active sports markets, zero have end_date in the next 72h. Single-game markets do exist (`mlb-det-bos-2026-04-18`) but Polymarket marks them `closed=False → True` within ~2h of game end (UMA liveness). The e13 historical median 14.4-min hold reflects markets that are now already closed — by the time the daemon polls every 2s, the asks are gone.
2. **The active 0.95–0.99 zone is dominated by futures** (NBA Finals, Stanley Cup, Vezina Trophy). LlamaEnjoyer's 500-trade history confirms 41% of his buys happen at price ≥ 0.99 with $34k–$151k position sizes. Per-trade edge ~0.1%, profit comes from scale.

Three implications for $1k capital:

- **Sports_lag at 0.95–0.97** *might* still work but has a much shorter live capture window than the historical median suggested. The 2x2 grid as built will mostly miss it.
- **LlamaEnjoyer's 0.99 zone has depth and is fillable**, but per-trade edge is 0.1% — at our average $30 trade size that's $0.03/trade. Need ~3,300 trades/month to make $100. Technically possible but slow.
- **The cleanest validated strategy at our scale is Austere-Heavy's barrier tail-insurance** (per synthesis): 100% win rate at ≥15% spot-distance filter (n=57), 6.7% gross over 28 days at $300k notional. At our scale that's ~$70/month per $1k.

## Strategy portfolio for $1k

Three strategies, paper-traded in parallel, sized to fit a $1k real bankroll. All run inside the existing `e12_paper_trade` harness — adding new cells, not new infrastructure.

### Strategy A — `sports_lag_wide` (LlamaEnjoyer's zone)

The zone where actual depth lives. New cap variant in the existing 2x2 grid → expanded to 2x3:

```python
ENTRY_TARGET_CAPS = (0.95, 0.97, 0.99)
```

- 6 cells total: 2 size_models × 3 caps
- Same detector, same risk gates
- Honest expectation: **0.99 cap fills frequently, low edge per trade. 0.95 and 0.97 caps fill rarely or never.** That's the data we want.
- After 7 days of paper data, we know empirically which cap is the right operating point

### Strategy B — `barrier_tail_insurance` (Austere-Heavy clone)

The most data-validated strategy in the synthesis. Buy NO on crypto barrier markets at price ≥ 0.95 when spot is ≥ 15% from strike. Hold to resolution.

- New strategy file `barrier_detector.py` reusing infrastructure from `experiments/e9_live_arb_scan/` (already filters crypto barriers)
- Add `binance` spot client (`python-binance` already installed)
- Single cell to start: `barrier_tail__fixed_50__filter15` ($50 per position, ≥15% spot distance)
- Acknowledged limitation from synthesis: **regime-independence is unproven** because backtest sample (184 markets) is concentrated in Mar–Apr 2026; missing 2025 bull-market data. We accept this risk in paper trade and watch closely if regime shifts.

### Strategy C — `wallet_shadow_austere` (copy-trade)

Mirror Austere-Heavy's fills with a few-second delay. Pull their trades from polymarket data-api (we already proved this works for LlamaEnjoyer). For each new BUY they place at price ≥ 0.95 on a barrier market, place the same trade at proportionally smaller size in a paper cell.

- Wallet: needs to be identified (synthesis cites Austere-Heavy as a pattern but no full wallet given). First task: identify the actual address via the crypto-barrier 0.95+ trade scan; pick the wallet matching the +$25k / 28d / 3,500 trades / 80% barrier profile.
- Single paper cell: `wallet_shadow__sized_proportional`
- Sizing: position fraction = (their size USD) × ($1k / their bankroll) capped at $50 per trade
- Expected outcome: tight tracking of the operator's edge minus our delay friction

### Strategies explicitly NOT in this plan (and why)

- **Crypto-barrier residual arb** (the original e9 thesis): dead, −63% historical (e13 finding). Even tighter spot-distance filter unproven.
- **Hourly ladder MM**: dead, confirmed by defiance_cr's bot shutdown.
- **5m updown HFT**: dead at our latency (NZ 200–300ms vs HFT sub-100ms).
- **Long-tail political/entertainment LP**: dead, 3¢ spreads from existing pros.
- **Static monotonicity arb**: dead, 0 executable violations at bid/ask.
- **Funding-rate arb**: dead in current regime (negative APY).
- **Copy Respectful-Clan**: dead, that wasn't an arb (momentum overlay; regime-dependent).
- **UMA dispute trading**: dead, <0.5% rate on sports.
- **Kalshi cross-venue**: deferred to v2, requires KYC + cross-venue capital management.

## Capital allocation tiers

The bankroll grows or shrinks based on cell-level decisions. Paper-trade results gate live deployment.

### Tier 0 — paper trade (now → +7 days)

| Strategy | Cells | Paper capital per cell |
|---|---|---|
| A — sports_lag_wide (3 caps × 2 sizes) | 6 | $1,000 each (paper) |
| B — barrier_tail_insurance | 1 | $1,000 paper |
| C — wallet_shadow_austere | 1 | $1,000 paper |

8 paper cells. Each runs the full 75-trade sample target (or 7-day cap, whichever first), with 20-trade early kill on negative cells.

### Tier 1 — first live deployment ($250 of $1k)

After paper-trade results land, deploy real capital to whichever cells cleared the **PROCEED** band (net edge ≥ 1.5% at fee_bps=0). Allocation:

- $250 total live capital initially (25% of $1k bankroll). Reserves cover variance.
- Distribute across surviving cells proportional to (net_edge × hit_rate). Floor $50 / cell.
- Continue paper-trading the killed/ambiguous cells in case they recover post-V2.

### Tier 2 — scale up after 14 days live ($500 of $1k or $1k of $1.2k bankroll)

Trigger: 14 calendar days live, net live PnL > +5% on deployed capital, no cell-level drawdown breaker fired.
- Increase per-cell live size up to $100 / position.
- Add one new strategy class from the deferred list (likely Kalshi cross-venue or a barrier salvage variant) **only if it can be paper-validated in parallel without competing for capital**.

### Tier 3 — graduate to $5k+

Trigger: cumulative live net PnL > +50% over 30 days OR external capital injection.
- Move to VPS (US-east) to close the latency gap (currently 200–300ms NZ → ~30ms VPS).
- Re-evaluate strategies that need sub-100ms (none of our current set, but the salvageable barrier variants might).

## Realistic monthly-revenue projection at $1k

Honest application of the ÷5 rule + e13 sample-size discipline:

| Strategy | Optimistic monthly | ÷5 realistic | Comment |
|---|---:|---:|---|
| sports_lag_wide @ 0.99 | $40 | $8 | LlamaEnjoyer scale, our size — high frequency, low edge |
| sports_lag_wide @ 0.95–0.97 | $50 | $10 | If live capture works — uncertain |
| barrier_tail_insurance | $80 | $16 | Austere-Heavy at $1k scale, no regime safety |
| wallet_shadow_austere | $60 | $12 | Tight tracking minus delay friction |
| **Combined ($1k bank)** | **$230** | **$46** | **~5% monthly** |

With the strategies that survive validation, target compounded growth:
- Month 1: $1k → $1.05k
- Month 6: $1k → $1.34k (5% / month compounded)
- Month 12: $1k → $1.80k

If realised returns are above the ÷5 floor (closer to half-optimistic), the Month-12 number is $2k–$3k. The plan succeeds if growth exceeds 3% / month sustained — that's the band where compounding outpaces opportunity cost vs. T-bills.

## What this plan deliberately gives up

- **Speed.** No VPS, no co-location, no sub-100ms latency. We are explicitly accepting Saguillo's compression trend may eventually kill the strategies we picked.
- **Scale.** $1k cannot run Austere-Heavy's 304 concurrent positions. We will hold 5–20 concurrent at most. That limits diversification.
- **The MM strategy class entirely.** Even though Akey 2026 says MM is the only class with predicted positive returns, we don't have the inventory-management infrastructure or the latency to compete with `defiance_cr`'s replacement bots.
- **Front-running operators.** Tempting to front-run Respectful-Clan's 24s-median momentum signal (per synthesis) but that's untested; capital not allocated.

## Decision criteria (pre-committed; do not modify after results)

Per cell, applied at the relevant sample size:

| n trades | Verdict trigger | Action |
|---|---|---|
| < 20 | — | continue |
| ≥ 20 | net edge < 0% AND PnL < 0 | **kill cell** (early kill) |
| ≥ 75 | net edge < 0.5% OR PnL < 0 | **kill cell** |
| ≥ 75 | 0.5% ≤ net edge < 1.5% | **ambiguous** — extend by 75 more or kill |
| ≥ 75 | net edge ≥ 1.5% | **promote to live** at Tier 1 sizing |

Cells that hit `cap_too_tight` > 80% of detections without filling: log it and after 7 days widen the cap to `max(cap, observed-median-ask + 0.005)`. The missed-opportunity diagnostic in `report.py` already surfaces this.

## V2 cutover handling (unchanged from PLAN_E12_PAPER_TRADE.md)

- Daemon auto-pauses 2026-04-22 09:30 UTC via `cutover_pause_active()`
- `v2_watcher.py` runs snapshot pre-cutover, verify post-cutover; resumes daemon if clean
- Pre-commit: discard V2-tagged data if {fee shifts ≥ 50bps, slug coverage drops ≥ 20%, best_ask shifts ≥ 10%}

## Concrete file changes (next session)

```
experiments/e12_paper_trade/
├── config.py             # ENTRY_TARGET_CAPS = (0.95, 0.97, 0.99) — adds 6th column to grid
├── detector.py           # relax END_DATE_WITHIN_HOURS to allow futures + game markets
├── barrier_detector.py   # NEW — Austere-Heavy clone: barrier markets, ≥15% spot distance
├── binance_spot.py       # NEW — wraps python-binance for BTC/ETH minute bars
├── shadow_detector.py    # NEW — polls polymarket data-api for Austere-Heavy's trades
├── shadow_wallets.py     # NEW — config: list of wallets to shadow + sizing rules
└── (everything else unchanged)
```

## Verification (continuation of e12 verification)

12. Identify Austere-Heavy's actual wallet address by re-running e13's wallet-diversity scan filtered to barrier markets only (Austere-Heavy is the operator with ~3,500 trades, 80% barriers, ~$300k notional, +$25k over 28 days)
13. Build `barrier_detector.py` and `shadow_detector.py`
14. Add 0.99 cap variant to `ENTRY_TARGET_CAPS`
15. Restart daemon; let all 8 cells run in parallel for 7 days
16. Generate `report.py` daily; mark any cell that early-kills
17. Tier 1 deployment after 7 days: live capital to surviving cells

## Honest open questions

1. **Was the e13 sports_lag edge real, or a backtest artifact?** The empirical 24h shows zero opportunity in the 0.95-0.97 zone. Either the historical window has compressed (Saguillo trend) or the backtest's sample (47 entries, late-RG plateau) was already a bad approximation. Paper-trading the 0.99 cap variant for 7 days will tell us.
2. **Is Austere-Heavy still active?** Synthesis is from earlier-month data. Their recent 28-day stretch could be over. First task in identifying the wallet is checking last_trade_time on their address.
3. **Does pm-trader's fill model match real CLOB matching priority?** pm-trader walks the gamma-published book; real CLOB is price-time priority. For our $50-size trades the difference is probably noise, but if Phase 1 paper says +5% edge and Phase 2 live says -1%, this is the suspected gap.
4. **Will V2 (2026-04-22) reset everything?** Possible. The pause-resume protocol handles it but we may end up with two disjoint datasets that we can't combine.
