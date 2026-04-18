# Proposed diffs to `~/.claude/plans/is-there-anythign-in-bright-cook.md`

Drafted from the user's critical-path additions. **Not yet applied** — review and merge by hand.

These three diffs implement items 3, 4, 5 from the user's additions list. Items 1 (wallet diversity at scale → `08_wallet_diversity_at_scale.py`) and 2 (LlamaEnjoyer P&L → `09_llamaenjoyer_pnl.py`) are probes whose results will feed back into the "Known limitations" section once they run.

---

## Diff 1 (item 3): Phase 0b — close the "accept published rate" loophole

The current Phase 0b option (c) lets us proceed with a non-zero fee as a "more conservative assumption." This was the loose end. Replace with mandatory backtest re-validation.

**Replace lines 143–149:**

```diff
 ### 0b. Zero-fee assertion (new, critical)
 Buy a $5 position in a recently-resolved sports market (winning side at ~0.97). Read back pm-trader's recorded fee:
 - If `fee == 0` → empirically matches SII data. Proceed.
 - If `fee > 0` → pm-trader's model disagrees with on-chain reality. **Halt.** Three paths:
   a. Reconcile: check whether pm-trader's `bps` parameter is configurable; set to 0
   b. Investigate: pull the live market's `getClobMarketInfo(conditionID).info.fd.r` to see the actual feeRate override
-  c. Accept: if pm-trader insists on charging published rate, run with that as a more conservative assumption and note the discrepancy in every report
+  c. **MANDATORY backtest re-validation** (replaces the old "accept" option). If reconciliation (a) and investigation (b) both confirm the live exchange charges the non-zero rate, do NOT proceed to Phase 1 with the new fee as an "accepted conservative assumption." Instead:
+     1. Re-run `experiments/e13_external_repo_audit/03_sii_sports_lag_backtest.py` with `DEFAULT_FEE_BPS = <verified live rate>`.
+     2. If historical net edge at the live rate falls below the **ambiguous-zone floor (1.5%, see decision criterion below)** → halt the project and re-evaluate the strategy. Do not paper-trade a thesis whose historical edge dies at the realistic fee.
+     3. If historical net edge at the live rate stays ≥ 1.5% → proceed, but lock the live rate as the new `FEE_BPS` default and re-run `slug_audit.py` and `pre_run.py` with it before unpausing.
+
+ Rationale: a "more conservative assumption" is still an assumption. The historical backtest is the only check against picking a strategy that survives at fee=0 but dies at fee=published-rate.
```

---

## Diff 2 (item 4): delay daemon start until 2-3 days after V2 cutover

Currently the plan starts the daemon before the cutover and pauses through it. The user's addition: don't start at all until 2026-04-25 (V2 + 2-3 days), with re-verification before the daemon goes live.

**Replace the verification step list (lines 339–351):**

```diff
 ## Verification (execution order)

 1. `uv add polymarket-paper-trader polymarket-apis httpx pyratelimiter espn-api nba_api MLB-StatsAPI python-binance`
 2. Run `shakedown.py` (0a + 0b + 0c). **Halt on zero-fee assertion failure.**
 3. Run `slug_audit.py`. Commit corrected pattern list + CLOB-tokens verification.
 4. Run `pre_run.py` for 1 hour. Confirm 75-trade target reachable in ≤ 7 days.
-5. Start daemon in tmux: `uv run python -m experiments.e12_paper_trade.daemon`.
-6. After 30 min: smoke-test `report.py`. Confirm positions opening on both paths, risk gates logging, no exceptions.
-7. Spot-check 3–5 resolved positions against real gamma-api trade tape. >20% fill-model mismatch → pause and debug.
-8. **On 2026-04-22:** follow V2 cutover plan.
-9. Run until `SAMPLE_TARGET_TRADES = 75` hit (or 7-day cap).
-10. Final `report.py` at `fee_bps = 0, 100, 300`.
-11. Apply decision criterion per size_model cell.
+5. **HARD WAIT until 2026-04-25 00:00 UTC** (V2 cutover 2026-04-22 + 48–72h stabilization). Daemon does NOT start before this. Use the wait window to:
+   - Monitor `pm-trader` and `polymarket-apis` GitHub repos for V2-compatibility patches; pin known-good versions
+   - On 2026-04-22 ~10:00 UTC: take a pre-cutover snapshot of `markets.parquet` schema + a sampled `getClobMarketInfo` response for diff against post-cutover
+   - On 2026-04-22 +24h: confirm gamma-api response shapes still match `polymarket-apis` Pydantic models; patch or downgrade if not
+   - On 2026-04-23 / 24: re-run `shakedown.py` (0a + 0b) against the V2-live exchange
+   - **If V2 zero-fee finding does NOT replicate post-cutover:** apply Diff 1's mandatory backtest re-validation rule before any further progress. Possible halt.
+6. Start daemon in tmux: `uv run python -m experiments.e12_paper_trade.daemon`.
+7. After 30 min: smoke-test `report.py`. Confirm positions opening on both paths, risk gates logging, no exceptions.
+8. Spot-check 3–5 resolved positions against real gamma-api trade tape. >20% fill-model mismatch → pause and debug.
+9. Run until `SAMPLE_TARGET_TRADES = 75` hit (or 7-day cap).
+10. Final `report.py` at `fee_bps = 0, 100, 300`.
+11. Apply decision criterion per size_model cell (see "Decision criterion" section for ambiguous-zone handling).
```

The `v2_migration.py` script section earlier in the plan should be reframed: it's no longer a mid-run pause script — it's a pre-start verification script that runs once on 2026-04-23 / 24.

---

## Diff 3 (item 5): pre-committed ambiguous zone

Replace the single-line decision criterion (around line 337) with a three-band rule, **committed before the run starts**.

**Replace line 337:**

```diff
-**Decision criterion:** kill a size_model cell if net edge < 0.5% OR total net PnL negative, at `fee_bps = 0`. Keep otherwise.
+**Decision criterion** (pre-committed before the run; do NOT modify after seeing results):
+
+| Net edge at `fee_bps = 0` (or actual live rate per Diff 1) | Action |
+|---|---|
+| < 0.5% OR total PnL negative | **KILL** the cell |
+| 0.5% ≤ net edge < 1.5% | **AMBIGUOUS** — do NOT proceed to capital. Extend sample by another 75 trades (or 7-day cap, whichever first), then re-evaluate. If still ambiguous → kill. |
+| ≥ 1.5% | **PROCEED** to capital-deployment decision |
+
+Rationale: pre-commit prevents observed-edge magnitude from biasing the bar. Sample-thin "barely positive" results historically translate to negative real-money runs after fees, slippage, and the operator-skill gap (Akey 2026: <30% of Polymarket traders profitable; Della Vedova 2026: bots take 2.52¢ per contract from casual traders).
```

---

## Diff 4 (item 1 — pending probe results): bump "Known limitations" wallet-diversity section

Once `08_wallet_diversity_at_scale.py` finishes, replace the H1 entry in the "Known limitations" section (line 356) with the actual measured number. Template:

```diff
-- **H1 "flow-diffuse" unconfirmed:** e13's wallet-diversity probe (n=121 wallets) showed top-10 = 68% of volume, contradicting the original H1 claim (411 wallets, diffuse). Sample is too small to act on. If larger-sample confirmation reverses H1, we're fighting pros and the realistic capture rescales 3–5× down. Watch for this during paper trading: if realized fills are consistently losing to the same handful of wallets, H1 failed and the strategy needs re-pricing.
+- **H1 "flow-diffuse" — settled by e13/08:** at n=<actual> wallets across <actual> markets (RG coverage <pct>%), top-10 share = <X>%, top-50 share = <Y>%, gini = <G>. Verdict: <H1 holds | H1 fails>. <If holds:> retail-paced; original docs estimate of 5–15% capture stands. <If fails:> realistic capture rescales 3–5× down; treat the strategy as a pro-vs-pro contest and watch for the same top-10 wallets as adversaries during paper trading.
```

---

## Diff 5 (item 2 — pending probe results): add LlamaEnjoyer benchmark to "Known operators"

Once `09_llamaenjoyer_pnl.py` finishes, the "Known operators" section gets a real number to anchor against:

```diff
 - `LlamaEnjoyer` (0x9b97…e12) demonstrably trades UFC post-event
+ - `LlamaEnjoyer` (0x9b97…e12, full 0x<hex>): last 30 days realized P&L = $<X> across <N> markets, win rate <H>%. <If profitable:> validates that taker-side post-event sports arb still pays. <If unprofitable or marginal:> realistic ceiling for our paper trade is similar; calibrate expectations accordingly.
```

If LlamaEnjoyer's realized P&L is ≥ +$1k over 30 days at modest capital (say <$50k deployed), it's an existence proof for the strategy class. If it's negative or near-zero, the thesis loses an important piece of supporting evidence.

---

## Order of merging into the plan

1. Diff 3 (ambiguous zone) — pure planning edit, can apply now
2. Diff 1 (Phase 0b mandatory re-validation) — same; can apply now
3. Diff 2 (V2 wait) — applies now; daemon doesn't start until 2026-04-25 anyway
4. Diff 4 — wait for `08` results
5. Diff 5 — wait for `09` results

User decides which (if any) to merge.
