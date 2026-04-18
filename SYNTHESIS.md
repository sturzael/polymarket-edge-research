# Two Days Hunting for Edge on Polymarket

*A research synthesis — what worked, what didn't, and what I learned along the way.*

## Summary

Over approximately two days in April 2026, I ran a structured research project investigating whether a solo operator could find tradeable edge on Polymarket using an LLM-assisted research workflow (Claude Code + conversational review). The project started with the implicit thesis that prediction markets might contain mispricings catchable by a competent individual with modest capital.

Nine distinct trading theses were investigated. Eight were falsified. One survives with modest, unvalidated upside of approximately **$200–$800/month at $10k deployed capital**, gated behind two untested live-cost unknowns.

The more durable output of the project is methodological: a working discipline for evaluating speculative opportunities against data, including two rules (**÷5 on revenue estimates**, **counter-memo before action**) that repeatedly caught estimation drift before it became expensive. The meta-finding — that the honest trajectory of a speculative trading thesis is usually a series of downward revisions, not upward ones — is probably the most valuable single thing produced.

This document records the arc. The specific trading conclusions are fixable in time. The methodology transfers.

---

## What was investigated

The project began with an open question: where in the Polymarket ecosystem might an individual operator find tradeable edge? Over two days, the following angles were each investigated, to varying depth, and either falsified or provisionally survived.

### Investigated and killed

**1. 5-minute BTC/ETH/SOL up/down markets.** Polymarket runs rolling 5-minute binary markets on spot-price direction. Initial hypothesis: if the market's implied probability lags the underlying spot feed even briefly, there's exploitable pre-expiry edge. Falsified by observation that 85% of arbitrage flow in these markets is captured within the first 60 seconds post-signal, consistent with HFT-grade execution. A laptop-operated bot, even on a US-East VPS, cannot compete with operators running at millisecond reaction times on tick-level WebSocket data. This space is actively worked by at least one public bot vendor (PolySnipe) plus several others inferred from wallet analysis.

**2. Hourly "above-K" strike ladders (market making).** Initial hypothesis: Polymarket's hourly BTC/ETH strike ladders present 30+ markets per asset per hour that professional MMs would skip due to admin overhead. A laptop operator could post tight quotes inside the 1¢/99¢ penny stubs and collect spread. Falsified within 4 minutes of live observation: the apparent 73¢ gap in the order book was a misreading of CLOB's bid-sort order (ascending, not descending). The true inside spread was 2–3¢, actively managed by a professional MM reacting to spot moves within ~30 seconds. No gap to capture; the market was already served.

**3. Static arbitrage via monotonicity violations.** Initial hypothesis: if `P(BTC > $77,000)` trades higher than `P(BTC > $76,600)` simultaneously, there's a risk-free spread. Sweeping both BTC and ETH strike cohorts at live bid/ask found zero executable violations. Apparent violations observed on `lastTradePrice` were stale-print artifacts, not executable prices. Falsified.

**4. Long-tail non-crypto LP.** Initial hypothesis: Polymarket's thousands of obscure long-tail markets (niche politics, minor sports) have wider spreads and less professional market-making presence, creating LP opportunities. Survey of 50 random balanced long-tail markets found median spread of 3¢ (already competitive), and the wide-spread markets (50–70¢ spreads) had zero 24h volume. No flow to capture. Falsified.

**5. Crypto barrier markets as resting opportunities.** Initial hypothesis: markets like "will BTC reach $90k by April 30" with spot already well past the barrier should have winning-side tokens trading below 1.00, capturable as near-risk-free trades held to resolution. Real-time scan of 36 live barrier markets with economically-certain outcomes found all 36 with winning-side asks pinned at 0.99+ and no cheap resting asks. The arbitrage exists only during the transition moment when spot crosses the barrier — a speed race, not a patient opportunity. Falsified for laptop-grade execution.

**6. Expiry microstructure / Chainlink oracle replication.** Initial hypothesis: Polymarket's 5-minute markets resolve against Chainlink Data Streams (confirmed 88% of crypto markets). Building a real-time Chainlink-output predictor from constituent CEX websockets might identify cases where the market's implied probability diverges from oracle-predicted probability in the final 30 seconds. Investigated but not pursued: the build cost (1–2 weeks) is high relative to the uncertain edge, and the strategy requires competing with the same HFT operators already dominating the 5m space.

**7. "Copy Respectful-Clan" (initial master plan).** Analysis of Polymarket's top wallets identified "Respectful-Clan" with $1.65M book value and +$99k realized P&L over 38 hours. Initial thesis: replicate their apparent tail-insurance strategy at small scale. Falsified by a decomposition of their position book: 215 of 223 of their directional YES buys occurred within 60 seconds of BTC rallying >0.5% in a 4-hour window — a momentum-trading strategy, not tail-insurance. Their pure tail-insurance subset produced 1.5% ROI with negative realized P&L, identical to Impressive-Steak (another top wallet, net −$78k). The headline $99k was two good macro calls during a favorable regime, not a replicable rule.

**8. Crypto funding-rate arbitrage.** Investigated as a tangent when Claude Code mentioned "10–30% APY" from memory. Live data pull via ccxt confirmed current BTC/ETH/SOL perp funding rates are negative (−8% to −16% annualized), with 90-day median near zero. Net of round-trip fees (~0.25%), expected value is slightly negative. The "10–30% APY" number reflects 2020–2023 bull-market conditions, not current regime. Falsified — and notably, falsified by a live-data sense-check that Claude Code then acknowledged as a methodology failure on its part. (This exchange is itself worth preserving as evidence of how LLM-assisted research can go wrong and how user verification catches it.)

**9. Dump-and-hedge pair-sum arbitrage.** Surfaced during a public-repo scan: two independent teams (RaymondDakus, dashkit-protocol) built and shipped detection bots for intra-market pair-sum violations on 15-minute BTC markets (where `YES_ask + NO_ask` briefly drops below $1.00). Deferred rather than falsified, but the practical verdict is negative: two teams shipping publicly means the edge is known and competitive, and the observable bot sizing ($1 max positions in at least one case) suggests real-world fills don't support meaningful size. Historical data can't tell you whether both legs are fillable at the observed gap prices; that requires live deployment.

### Investigated and provisionally alive

**10. Barrier-market tail-insurance à la Austere-Heavy.** A different Polymarket wallet ("Austere-Heavy") was profiled as a cleaner version of the tail-insurance pattern originally (wrongly) attributed to Respectful-Clan. Their 3,500 trades over 27.8 days show $324k of tail-insurance notional on dip-NO / reach-NO barrier markets at median 0.956 price. Their behavior is regime-independent (only 16% of YES trades correlate with recent BTC moves, vs 98% for Respectful-Clan), and their latency profile (p50 36s, p90 7,298s) is not momentum-driven. This is the closest thing to a replicable mechanical strategy the project identified.

Honest expected value at $10k deployed capital: **$200–$800/month**. This estimate has been revised downward six times over the project from initial estimates of $5,000–$30,000/month. The trajectory is itself informative — see "Meta-findings" below.

Two unknowns still gate live deployment:

- **H3 (fees):** Polymarket's actual maker fee is empirically unknown. Settleable with one $5 live trade.
- **H2 (fill feasibility):** whether the observed 0.95–0.99 asks actually rest on the book long enough to be filled, or whether they're quote-touched-gone in seconds. Settleable with one hour of manual live observation on a single qualifying market.

Both tests cost under $20 combined. Neither has been run at time of writing.

**11. Sports settlement-lag arbitrage.** Polymarket's UMA oracle resolves sports markets with lag measured in hours. During the lag window, winning-side tokens often trade at 0.95–0.99 despite the game outcome being public. A scan of 200 recently-closed sports markets with 24h volume > $10k found 50 arbitrage windows (median 11.7 minutes long, 3.4% notional-weighted edge). Flow was diffuse across 411 distinct wallets with no dominant operator, suggesting laptop-accessible competition. Investigated but not built — gated behind the same H3 and H5 (latency from VPS) tests.

---

## Infrastructure built

The following artifacts were produced and remain in the repository:

### Data collection

- **24-hour reconnaissance probe** capturing 1,316 resolved crypto markets and 791k snapshots across 607 concurrent 5-minute markets
- **Wallet forensics** covering 18 top barrier-market operators, including Respectful-Clan, Austere-Heavy, and Impressive-Steak
- **Cross-exchange lead-lag measurement** validating 100ms Binance→Coinbase lead-lag (published-literature consistent)
- **Deribit IV snapshots** for options-market probability baselines
- **48-hour geopolitical informed-trading probe** (in progress at time of writing)

### Analysis

- Regime-stratified backtest of the Austere-Heavy-style tail-insurance rule across 184 resolved markets — 100% win rate at 15% distance filter, but acknowledging the sample is almost entirely from Mar–Apr 2026 and doesn't include sustained bull-market conditions
- Counter-memo framework applied to each surviving thesis to identify silent-failure modes
- Latency profile for Respectful-Clan's rally-triggered trades (p50 24s — front-runnable, but the strategy being front-run is the weaker of their two edges)
- Full-scale scanner across ~5,800 active Polymarket markets categorized by type

### Documented API gotchas (saved to README for future use)

- gamma-api silently drops past-expiry markets from listings — use CLOB for resolution detection
- gamma-api's `condition_ids` filter requires repeated query params, not comma-separated
- CLOB's `/markets?condition_id=X` silently ignores the filter — use `/markets/<cid>` instead
- CLOB's `/book` endpoint returns bids sorted ascending (lowest first) — `bids[0]` is the WORST bid
- Polymarket resolution lag averages ~400 seconds past nominal expiry, not seconds
- For updown-style markets, `endDate − startDate` gives the parent series duration, not per-contract duration; parse the slug

Any future researcher in this space starts several days ahead by knowing these.

---

## Methodology — what worked and what didn't

Two explicit methodology rules accumulated during the project and proved load-bearing:

### Rule 1: Divide monthly revenue estimates by 5 before acting on them

This was observed empirically: initial estimates in this project were systematically 3–10× too high. The sources of optimism are consistent — capture-rate assumptions ignore queue position, adverse selection goes unmodeled, fees get rounded down, fat-tail risks are priced as medium-probability rather than certain. Applying ÷5 to an initial estimate produced numbers that subsequent analysis then validated as roughly correct. The rule is crude but directionally robust.

### Rule 2: Write the counter-memo from the same data

Before acting on a "this works" finding, write the companion "here's why this doesn't work" memo using the same dataset. The counter-memo is required to identify silent-failure modes — ways the strategy generates ≤$0/month without a loud signal that anything's wrong. This rule killed the hourly-ladder MM strategy within 4 minutes of going live (the counter-memo correctly predicted the MM was already there) and the Respectful-Clan replication plan (the counter-memo predicted regime dependence; the Impressive-Steak comparison confirmed it).

### What didn't work methodologically

The project repeatedly exhibited **"estimate reconstruction"**: after a thesis was killed, the next thesis's initial estimate would arrive at the same order of magnitude as the killed one, just with different underlying assumptions. The ÷5 rule caught the arithmetic but not the semantic drift. A better discipline would have been to institute a hard cap: no individual thesis gets an estimate above some honest-market baseline (perhaps 10× the cost of running the test), regardless of the spreadsheet.

The project also exhibited **"rabbit-hole productivity"**: each killed thesis spawned 2–3 new angles, each of which consumed hours of analysis. Total project time across ~2 days was probably 15–20 hours of focused work. Output per hour declined over time as remaining theses became weaker. A better discipline would have been to bound the project to 8–10 hours and accept the conclusion at that point regardless of whether a specific thesis had been exhausted.

### The meta-finding

The correct trajectory of an honest speculative-research project is **downward**. Initial excitement produces big numbers. Each successive analysis reveals reasons the big numbers are wrong. The endpoint is a modest, heavily-caveated estimate for one surviving strategy — or a clean null result across the board. The ÷5 and counter-memo rules are designed to accelerate that trajectory; they don't change its shape.

Projects that don't exhibit this downward trajectory are either (a) investigating something with genuine structural edge that the researcher has identified early, which is rare, or (b) failing to apply the discipline that would reveal the drift.

---

## What this means for whether retail-scale trading edge exists on Polymarket

The honest synthesis, based on nine falsified theses and one provisionally-alive one: **at solo-laptop-or-VPS scale, there is no obvious free alpha in the venues and datasets examined.**

This isn't a claim that no edge exists anywhere on Polymarket. It's a claim that:

- The visible, obvious patterns (tail arbitrage on crypto barriers, 5m up/down microstructure, MM on hourly ladders, static arb, cross-venue arb, resolution-lag arb on sports) are either already worked by operators with structural advantages or don't survive the full cost stack of fees, adverse selection, fill feasibility, and capital inefficiency.
- The one surviving candidate (Austere-Heavy-style tail-insurance on barrier markets) produces honest expected returns in the $200–$800/month range at $10k capital — real, but modest, and with meaningful fat-tail risk.
- The market structure consistent with our findings is that Polymarket has roughly 2 meaningfully profitable operators out of 750 in the barrier-trading space. That's a ~0.3% base rate, consistent with an efficient market where skill (not copyable rules) separates winners from losers.

The practical implication: a new entrant to this space, without either domain expertise in a specific vertical (Bulgarian politics, NBA prop bets, niche weather markets) or an infrastructure advantage (sub-10ms execution, access to sports data feeds faster than the market), is statistically far more likely to be one of the 748 wallets making nothing or losing modestly than one of the 2 making real money.

### Where edge might still exist, which this project didn't test

- Verticals where the researcher has genuine non-public information advantage (industry contacts, regional knowledge, specialist expertise)
- Cross-venue plays requiring entity structure or KYC access the researcher happens to have
- Strategies with multi-month time horizons where the friction of capital lock-up is the moat
- Products adjacent to trading rather than trading itself (data feeds, research reports, execution tooling sold to other operators)

Anyone considering this space should honestly ask themselves which of these they have access to. For someone approaching it cold, the realistic answer is usually "none of them."

---

## What remains to be done (if anything)

Two cheap tests remain that would fully close out the surviving Austere-Heavy thesis:

**Test 1: Fee experiment ($10, 20 minutes).** Fund a Polymarket wallet with $50 USDC. Place one $5 limit buy on any active market. Let it fill. Compare the actual USDC decrement against the expected price × size. The delta is the fee. This settles whether the assumed 0% maker fee holds in practice or whether a 1–2% fee silently kills the strategy.

**Test 2: Fill feasibility observation ($0, 1 hour).** Identify a qualifying barrier market (BTC reach-upside where spot is >15% below strike with 2–4h to resolution). Watch the order book in real time for 60 minutes. Does the 0.95–0.99 ask actually rest for minutes at a time, or is it "quote-touched-gone" within seconds? This distinguishes a mechanically executable strategy from a trade-tape artifact.

If both tests pass, a $500 pilot deployment over 2–3 weeks would generate real data on realized P&L vs. the $200–$800/month estimate. If either test fails, the strategy is dead in practice and the project closes with a clean null across all ten theses.

Neither test has been run. The project ends cleanly either way.

---

## Acknowledgments and disclosures

This research was conducted with substantial assistance from Claude Code (Anthropic's coding agent) and parallel review via Claude in a separate conversational context. The LLM-assisted workflow meaningfully accelerated data collection, API integration, and exploratory analysis. It also introduced specific failure modes — notably the "estimate drift" pattern where polished output documents contained numbers more optimistic than the underlying evidence supported, and at least one instance (the funding-rate tangent) where an LLM cited historical performance figures from memory without verification until a data-based sense-check was requested.

The appropriate posture for anyone conducting similar research is: the LLM is an exceptional research assistant and an unreliable analyst. Every number it produces should be traced to the specific query, dataset, and timestamp that generated it. Every estimate should be divided by 5 and have its counter-memo written. **The LLM's polish level is not correlated with its accuracy.**

No capital was deployed during this project. No trading was conducted. The findings are based entirely on observation of public Polymarket data, public wallet activity, and public market infrastructure. No accusations of informed trading or other misconduct are made against any named wallet or operator; wallet analysis is conducted at the behavioral pattern level only.

---

## Appendix: artifact index

All artifacts live in this repository. Raw data files (SQLite DBs, trade history JSONL) are excluded from the public repo for size and privacy reasons but are regenerable from the included code.

- `docs/README.md` — project entry point
- `docs/FINDINGS.md` — chronological log of all findings
- `docs/PLAN_HISTORY.md` — narrative of project pivots (v0 → v1 → v2 → v3)
- `docs/MASTER_PLAN.md` — master build plan (superseded by this synthesis; kept for reference)
- `docs/WHAT_WORKS_ON_POLYMARKET_BARRIERS.md` — earlier synthesis focused on barrier markets only
- `docs/OPPORTUNITY_HOURLY_LADDER_MM.md` — killed thesis: MM on hourly ladders
- `docs/OPPORTUNITY_SPORTS_EVENT_LAG_ARB.md` — alive thesis: sports resolution-lag
- `docs/COUNTER_MEMO_MM_OPPORTUNITY.md` — methodology artifact; the counter-memo that killed the MM thesis
- `probe/` — 24h reconnaissance probe code (data regenerable)
- `experiments/e1/` through `experiments/e11/` — individual investigations (see each subfolder's README for scope and findings)

Total code: ~4,500 lines of Python. Total data (regenerable): ~800MB SQLite. Total time: approximately 2 days of focused work, ~15–20 hours.

---

*End of synthesis. The research is complete. The two remaining tests, if run, close out the last live thesis. Otherwise the project lands here.*

---

## Post-synthesis update (2026-04-19): paper-trade phase started

This synthesis was written as a capstone. It has since been partially superseded by a new phase — the project re-opened to design and (pending approval) run a continuous paper-trade harness on the surviving theses. What changed:

### Sports settlement-lag arb: alive and better-characterized

The "provisionally alive" sports-lag thesis is now partially empirically validated:
- **H3 (fees) is resolved.** e13 historical backtest against the SII-WANGZJ on-chain Polymarket dataset (954M rows) measured taker fees across 143 sports post-resolution trades: zero across all price bands. The $10 live-test H3 gate is no longer blocking.
- **Historical edge confirmed (sample-thin).** Same e13 audit measured +3.99% notional-weighted net edge across 47 entries, 14.4 min avg hold. Directionally matches the earlier in-repo observations.
- **H1 (wallet-diffuse) partially contradicted.** A re-derivation at 121 wallets / 41 markets found top-10 = 68% of volume, contradicting the original "411 wallets" claim. Sample is too thin to reverse H1 confidently; deferred pending deeper rerun.

### Crypto-barrier tail-scalp: killed

Previously categorized as "residual arb opportunity" in `e9_live_arb_scan`, which proposed ~1% net EV held to resolution. Same e13 audit: **n=5,220, −63.44% notional-weighted net edge, 37.34% crash rate**. Crypto realized volatility of 1–2%/hour flips 37% of these markets before resolution. Added to NULL_RESULTS.md as falsification #6.

### Austere-Heavy tail-insurance: unchanged status

The Austere-Heavy style barrier-market tail-insurance strategy is distinct from the killed crypto-barrier residual arb above (different entry triggers, different holding logic). The two cheap tests described earlier in this synthesis remain outstanding. Not part of the e12 paper-trade scope.

### Paper-trade harness (e12)

Plan documented at `docs/PLAN_E12_PAPER_TRADE.md`. Single strategy (sports_lag), two size models, continuous daemon, restart-safe SQLite. Uses `polymarket-paper-trader` (book-walking fills against live Polymarket order books), `polymarket-apis` (typed Gamma client), sports-result feeds (ESPN + nba_api + MLB-StatsAPI) for earlier detection than book-polling alone. Risk gates from Octagon pattern review (20% drawdown cell breaker, max 3 concurrent per event). V2 cutover on 2026-04-22 forces an explicit pause/verify/resume protocol mid-run.

Decision criterion: keep the strategy if net edge ≥ 0.5% at `fee_bps=0` across 50–100 paper trades; kill otherwise. Sensitivity analysis at fee_bps = 0, 100, 300 for robustness to the fee-is-zero finding.

### Updated posture on LLM-assisted research

Two additional failure modes surfaced this session worth noting:
1. **Protocol-docs gap.** Several assumptions the earlier sessions had treated as empirical unknowns (fee formula, rate limits, UMA resolution latency, V2 cutover date) were published at docs.polymarket.com the whole time. Not checking docs first cost real plan iteration.
2. **Sample-size inflation.** The e13 historical backtest returned concrete numbers (+3.99% edge, −63% crash) with wildly different sample sizes (47 vs 5,220). The smaller sample was preserved as actionable without the sample-size caveat initially; the user flagged this explicitly. Rule: always pair a result with its sample size and a note on whether the sample warrants action.

Both align with the broader posture already in this synthesis: the LLM is a research assistant, not an analyst. Polish is not accuracy. Verify before acting.

### Current project state

- Plan approved, harness not yet built
- e13 audit complete with concrete numbers
- No capital deployed, no live trades
- Next step: Phase 0 shakedown + slug_audit + pre_run before the main daemon

The research is not complete. The synthesis above captures the Stage 1 arc (exploration → falsification → one survivor). Stage 2 (paper-trade validation) is now in progress and will either promote sports_lag to live-deployment candidate or add it to NULL_RESULTS.md.
