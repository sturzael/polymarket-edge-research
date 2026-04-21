# Agent F — Friction Model Decisions

This file documents the assumptions behind each friction layer so reviewers
can stress-test them independently.

## 1. Spread model

**Central assumption:** half-spread = 1.0pp (entry-side only, paid when
crossing from mid to ask).

**Sensitivity range:** 0.5pp (tight book, e.g. MLB regular season) to 1.5pp
(wide book, e.g. tennis or UFC). Primary analysis uses 1.0pp central.

**Justification:**
- e22 cross-venue finding: Polymarket vs Smarkets on the same live sports
  events showed |spread mean| = 0.75pp across n=106 matched pairs. Smarkets
  is a mature UK exchange; if Polymarket spreads were systematically wider
  than Smarkets by more than a couple of pp, cross-venue arb would eat it.
  So 1-2pp total spread (half-spread 0.5-1.0pp) is the supported range.
- e4 book-depth snapshots of 5m crypto markets showed extreme mid-life
  spreads (98pp from 0.01/0.99 stubs), but that's crypto-updown 5-minute
  markets — not sports T-7d. Irrelevant for our use-case.
- e11 findings referenced 1-3pp sports spreads; we take the midpoint.

**Why entry-side only:** In buy-and-hold to resolution, the contract pays
out 0 or 1 directly via protocol resolution — no second order crosses the
book. Spread is paid once.

**Risk:** if we're wrong and true half-spread is 2-3pp (4-6pp total
bid-ask), net edge drops to 18-20pp. Still deployable. Only becomes
threatening if spreads exceed 6pp total, which would be inconsistent with
e22's cross-venue measurement.

---

## 2. Fee model

**Formula:** `fee_per_contract = price × (1 - price) × fee_bps / 10000`.

This is the Polymarket published formula (confirmed in auto-memory
`polymarket_protocol_facts.md`). At p=0.575, the notional-scaled fee is
tiny — `0.575 × 0.425 = 0.2444` times the bps rate, so 3 bps → 0.0073%
of notional = **0.07pp**.

**Fee scenarios reported:**
- 0 bps (historical V1, confirmed by e12 pre-V2 sidecar)
- 3 bps (current sports post-V2 baseline)
- 7.2 bps (current crypto; used as a sensitivity bound in case V2 unifies
  rates upward)
- 15 bps (conservative V2 worst-case)

**Fee-timing decision: ONE-SIDED (buy-and-hold to resolution).**

**Justification:** The e16-established strategy is to enter at T-7d when the
market is priced 0.55-0.60 and hold to resolution. Polymarket contracts
resolve via UMA oracle — the winning token pays $1, losing token pays $0.
There is no exit trade; the position auto-settles. Only the entry fee is
paid.

**What we lose if we're wrong:**
- If we actually exit before resolution (e.g., to free capital or stop
  losses), we pay a second fee at exit price. Per `data/fee_model_comparison.json`,
  the two-sided model at $500/3bps costs only 0.07pp more. Immaterial.
- If exit price is closer to 0.5 (where `p(1-p)` is highest), the exit fee
  could reach 0.09pp at 3bps. Still immaterial.

**Both models reported** in `data/net_edge_matrix.json` → `one_sided` and
`two_sided` branches.

---

## 3. Slippage model

**Formula:** `slippage_pp = max(0, order_size - $20) / $500 × 1.0pp`

**Justification:**
- `median_trade_usd` p50 in the 0.55-0.60 bucket = **$20**. This is the
  typical single taker-print observed in the ±12h window around T-7d.
- **Proxy assumption:** median single-fill USD ≈ top-of-book fillable depth
  available to a market order. This is conservative: the actual top-of-book
  passive resting depth may be higher than the largest observed print if
  MMs don't get hit every minute. But it's the only scale-invariant anchor
  we have.
- **Slope:** 1pp per $500 of order above the single-fill proxy. This is a
  conservative haircut — in practice many sports markets at T-7d have
  several price levels within 1pp of top-of-book, and walking $500 above
  the top print may only cost 0.5-1pp.

**Effect on net edge:**
- $200 order → 0.36pp slippage
- $500 order → 0.96pp slippage
- $1,000 order → 1.96pp slippage
- $2,000 order → 3.96pp slippage

**Risk:** if slippage is actually 2pp/$500 (twice our model), $500 orders
lose 2pp vs 1pp, and $2,000 loses 8pp vs 4pp. The $2,000 level would then
net only 16.8pp — still positive but meaningfully degraded. $500 would still
net 22.8pp. So the recommendation to cap at $500-$1000 is robust to 2×
slippage error.

---

## 4. Fill probability model

**Formula:** `fill_prob = empirical_ceiling × 0.85`, where
`empirical_ceiling` = fraction of 0.55-0.60 bucket markets whose
`max_single_trade_usd` ≥ order size in the T-7d window.

**Anchors from the parquet (n=120 in-bucket):**
- $200 → ceiling 86.7% → adjusted 73.7%
- $500 → ceiling 83.3% → adjusted 70.8%
- $1,000 → ceiling 80.0% → adjusted 68.0%
- $2,000 → ceiling 74.2% → adjusted 63.0%

**Justification for the 0.85 haircut:** `max_single_trade_usd` is an
upper-bound proxy — it tells you the largest order the market ever
*actually* filled in a single print during that 24h window, but that single
print may have walked multiple price levels. In practice, filling at our
*quoted* price (not our eventual fill price) requires top-of-book fillable
depth, which is smaller. A 15% haircut reflects this uncertainty; it's a
standard "empirical upper bound × typical book-walk discount" adjustment.

**What this model doesn't capture:**
- Queuing risk (someone else's order fills first). For a T-7d bet this is
  minor — we're not racing to a print.
- Adverse selection (the quote moves as we reach for it). Could add
  1-2pp if bots detect our order. Mitigated by using ≥T-7d entries where
  bot flow is lower.
- Order-size detection (very large orders may be filled at progressively
  worse prices). Already partially baked into the slippage model.

**Validation plan:** the e12 paper-trader pipeline can record
`slippage_bps` and fill success per cell. Agent F's fill-probability model
can be validated empirically within 20-30 live sports trades at mixed sizes.

---

## 5. Bets-per-month + concurrent-positions model

**Assumption:** 15-20 qualifying bets/month, midpoint 17.5.

**Justification:** Given by the task prompt, not measured here. A 30-day
forward observation (per e16 recommendation) would substitute a measured
number. If the real number is half (8/month), all annualized P&L projections
halve; if it's double (35/month), they double. This is a linear scaling
factor on all dollar numbers in Matrix 2.

**Concurrent positions:** 17.5 × 7/30 = 4.08 — with a 7-day hold from entry
to resolution, roughly 4 positions are open simultaneously at any moment.
Capital deployment sizing is built against this.

---

## 6. Fee-model decision made clear

The task prompt noted: *"Actually the fee is a one-sided cost when holding
to resolution (no exit trade needed — the contract resolves to 0 or 1).
If the strategy is buy-and-hold to resolution, only entry fee applies.
Document which model you use clearly in DECISIONS.md. Both models are worth
reporting."*

**My decision:** **one-sided (buy-and-hold) is the primary model**,
reported in Matrix 1 as the main table and used in Matrix 2 capital
deployment. Two-sided is reported as a sensitivity in
`data/fee_model_comparison.json` and in Matrix 1's `two_sided` branch of
`net_edge_matrix.json`.

Why one-sided is correct for this strategy:
- The e16 strategy IS buy-and-hold. There is no exit model in the finding.
- Polymarket contracts settle via UMA — the winning token is redeemed for
  $1 directly via smart contract, no second trade needed.
- The paper-trader (e12) and forward validation also assume hold-to-resolution.

Why two-sided is reported anyway:
- If we added a momentum exit rule later (e.g. "close if market moves to
  0.80 before T-1d"), the two-sided fee model would apply.
- Completeness: task prompt requested both.

The difference is <0.1pp in all scenarios tested, so fee-model choice is
not a decision-driver. Slippage and fill probability are.
