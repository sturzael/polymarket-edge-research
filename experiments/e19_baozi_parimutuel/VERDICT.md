# e19 — Baozi VERDICT

**Tier:** 3 (venue profile + methodology). Measurement not performed; probe pipeline ready.
**Headline:** Baozi is a live Solana mainnet pari-mutuel PM platform (V4.7.6, program `FWyTPzm5cfJwRKzfkscxozatSxF6Qu78JQovQUwKPruJ`). No REST API — all data via Solana RPC `getProgramAccounts` with memcmp on the MARKET discriminator. Circumstantial signals (no Dune/DefiLlama coverage, Beta status, no cited user/TVL counts) point to small resolved-market universe. Expected TIER 3 (<100) to low-end TIER 2 (100-500) once probe runs.

**Calibration magnitude vs Polymarket baseline (sports 0.55-0.60 → +30pp, z=5.1):** NOT MEASURED. A-priori, pari-mutuel theory (Thaler & Ziemba 1988) predicts larger FLB than order-book. But Baozi data accessible via RPC is **at-close (T-0) only**, not T-7d — a more-informed price point than Polymarket's anchor. Net comparison direction is ambiguous.

**Key protocol findings:**
- Mechanism: pure pari-mutuel, `implied = yes_pool / (yes_pool + no_pool)`. Not LMSR.
- Fee on winnings only: `(grossProfit × platformFeeBps) / 10000`.
- No on-chain category field — infer from question text.
- V4 ↔ V5 arb is real: V4 (pari-mutuel) and V5 (Orca Whirlpool CL-AMM conditional tokens) run on the same events with different pricing. Spread is tradeable in theory; not quantified here.

**Blockers for full TIER 1 analysis:**
1. T-7d snapshot requires bet-replay via `getSignaturesForAddress` + instruction decode + pool reconstruction. Solana public RPC retains ~2 weeks of tx history for unknown accounts → older markets need Helius/QuickNode archive.
2. Sandbox blocked Bash/npm/direct RPC in this run; pipeline scripts saved to `scripts/` are runnable locally.

**Next steps (if prioritized):**
1. Run `scripts/probe_baozi.py` with a Helius/Triton archive RPC endpoint to get market universe count and at-close pool snapshots.
2. If >50 resolved markets surface, run `scripts/flb_calibration.py` for at-close FLB + sports stratification.
3. If >200 resolved markets, build bet-replay indexer for real T-7d calibration (~half-day of work).
4. Independently: prototype V4/V5 arb monitor using top-20 V4 markets × matched V5 Orca Whirlpools.
