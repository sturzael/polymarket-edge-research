# e20 — Azuro VERDICT

**Tier:** 1 — full analysis. 1.86M outcome-rows (Polygon) + 1.48M (Gnosis) across 837k+694k resolved conditions, 2023-02 → 2025-05.

**Headline:** Azuro AMM sports book shows textbook-direction FLB with **~10-75× smaller magnitude** than Polymarket. At 0.55-0.60: Azuro +0.4pp vs Polymarket +30pp (z=2.8 vs z=5.1; n=151,962 vs 32). Max Azuro deviation anywhere = +3pp; max Polymarket in same range = +30pp.

**AMM hypothesis REJECTED.** AMMs do NOT inherit uncorrected FLB just because they lack a professional market maker. Azuro is *better* calibrated than Polymarket despite (or because of) being on-chain.

**Likely mechanism:** Azuro's "data providers" seed initial odds from sharp off-chain bookmakers, so LP quotes start at a fair line. Informed LPs take the other side of retail flow and fade mispricing. Professional overround (median 1.065) is distributed flat across buckets — retail pays uniform tax, no favorite-specific underpricing.

**Structural observation:** Azuro markets are short-horizon. Only 0.1% of conditions had bets 7 days before game start; only 9.7% at 24h. **Apples-to-apples T-7d comparison is structurally impossible on Azuro.** Close-time anchor used here is ≈ Polymarket T-0 — if anything, this should favor Azuro *having* more FLB than Polymarket-T-7d (since Polymarket converges toward truth as close approaches). We still find less on Azuro, which strengthens the conclusion.

**No "0.50 cliff"** — Polymarket's 31pp discontinuity across the 0.50 boundary does not replicate on Azuro (smooth +4.7pp progression from 0.45-0.50 to 0.50-0.55 bucket).

**Combined with Agent 5 (Betfair ±6pp max):** Polymarket is the clear outlier. Two independent comparison venues (traditional betting exchange with 73k+ selections; on-chain AMM with 1.86M+ outcomes) both show the Polymarket +30pp sports anomaly does not exist elsewhere. The excess is Polymarket-specific (and likely specific to Polymarket's retail-heavy exotic/novelty sports sub-composition).

**Environment notes:**
- Azuro indexing stopped ~2025-05-08 across all chains; data complete through that date, nothing after.
- Arbitrum and Linea V3 endpoints listed in public docs are dead.
- Agent could not `git commit` (sandbox); artifacts staged in working tree.
- Agent could not Write FINDINGS.md/VERDICT.md itself; parent session persisted this.
