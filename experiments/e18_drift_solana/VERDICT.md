# e18 — Drift (Solana) VERDICT

**Tier:** 3 — scouting dead-end.
**Headline:** Drift's B.E.T is dormant. 15 total prediction markets lifetime, 94% of volume in 2 election contracts, **zero new listings in 5 quarters** (2025Q2 → 2026Q2). Non-election markets have median hourly depth of $10. Not tradeable outside major political events.

**Calibration at T-7d (n=14 resolved, pooled):** price-outcome correlation +0.48. Directionally calibrated. Only statistically notable bucket is 0.10-0.15 with n=1 (FED-CUT-50-SEPT, z=+2.65) — anecdotal, not a pattern. Sports subset (n=6) too small for any FLB claim: 1 sample in the 0.55-0.60 bucket. **Cannot confirm or deny Polymarket's +30pp sports favorite-underpricing** — the venue lacks the events to measure it.

**Cross-venue sanity check:** Drift TRUMP-WIN-2024-BET T-7d = 0.66 matches Polymarket's ~0.63-0.66. During high-liquidity political events, Drift prices were **not dislocated** from Polymarket. This is one useful datapoint for Agent 6's cross-venue analysis.

**Research-question implication:** Drift is the wrong venue for FLB research. Future agents should deprioritize Solana DEX prediction markets (cf. Baozi is also thin per e19) and focus sample power on Polymarket, Kalshi, Betfair, PMXT.

**Environment notes:**
- Agent could not commit to git (permission denied for `git commit` in background mode); all artifacts staged but uncommitted.
- Added `pmxt>=2.31.1` to `pyproject.toml` (root). Worth reviewing whether this was necessary for Drift work — possibly carry-over from pipeline setup.
