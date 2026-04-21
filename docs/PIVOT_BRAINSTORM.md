# Pivot brainstorm — post-closure session

**Date:** 2026-04-21. **Status:** brainstorm only — no directions committed, no code changed. Project remains closed per `PROJECT_POSTSCRIPT.md` (2026-04-19).

This document captures a one-session brainstorm about where the e1–e15 research stack could be pointed next, given that the Polymarket thesis family is exhausted at the $1k / NZ-laptop / REST-polling operator profile. Written as a reference for future sessions so we don't redo the same triage.

---

## What's pivotable vs what isn't

**Pivots cleanly** (infra + method):
- Detect-verify-log scanner architecture (e15)
- Concurrent async poll-loop pattern (probe)
- SII-style large-parquet offline analysis (e13)
- Calibration-curve / Brier / z-score plumbing (e1, e10)
- Methodology rules (÷5, counter-memo, measure-raw-first, pre-committed kill criteria)

**Does NOT pivot** (operator profile):
- 200-300 ms NZ RTT
- $1k-$10k bankroll
- REST-only polling, no VPS, no co-location
- Solo operator, no KYC'd entities beyond personal Polymarket wallet

**Implication:** any pivot that puts us back into a liquid, bot-competed financial market hits the same wall. Any pivot where latency/capital aren't the binding constraint is fair game.

---

## Directions evaluated this session

### Category A — "Research showcase" pivots (no edge claim)

1. **Live football (soccer) xG + goal-intensity model.** Free data (FBref / Understat). Output = calibrated next-goal probability. Publishable, portfolio piece. **Not** an edge — pros have this. Honest framing: a modeling exercise that reuses our calibration stack.
2. **LLM-forecaster calibration study.** Pull Metaculus / GJP Open questions, run frontier LLMs, measure Brier vs human crowd. Genuinely under-studied. Reuses e10's ratio-verdict discipline.
3. **Congressional STOCK Act disclosure scanner.** 45-day disclosure lag → latency-immune by construction. Event-study reusing e10/e15 plumbing.
4. **GitHub repo trajectory / arXiv citation prediction.** 30-day-ahead scanner from early signals. VC / research buyer-side value.

### Category B — Edge-hunting pivots (make-money framing)

Ranked by realistic yield at our operator profile:

1. **Run our own e15 scanner with capital.** README says: $400-900/year at $1k, scale to $4-9k/year at $10k. Capital-lockup-bound, not skill-bound. Lowest marginal effort — code exists. **Not "rich" but real.**
2. **DeFi yield/points farming** (Pendle PT, Ethena sUSDe, restaking programs). Scanner pattern = poll protocols, compute effective APY net of point-token valuation, rotate on compression. Historical: 12-25% fixed on Pendle stables, 10-20% Ethena. Smart-contract + depeg tail risk. Probably the **best "free-money coefficient" that fits our stack.**
3. **Kalshi × Polymarket cross-venue arb** (parked in e13 audit as `sstklen/trump-code`). Same markets, two venues, different US-regulatory treatment → persistent price gaps. Scanner adapts trivially. Requires Kalshi KYC.
4. **US/crypto-accessible sportsbook promo abuse.** Scanner = monitor promos across Stake / BetFury / Bovada, compute EV, hedge. 20-50% ROI on bonuses, capped at $5-20k/yr by account limits. Labor-heavy.
5. **AI-category Polymarket scanning.** Two sub-variants:
   - News-leak detection on AI markets → **expected to fail per e10's lesson** (news→market arb at 200-300ms loses to bots watching the same @testingcatalog / @apples_jimmy / Teortaxes feeds).
   - **Infra-signal scanner** (HuggingFace uploads, GitHub commits on vllm / transformers, DNS changes on model-host subdomains, iOS/Android beta teardowns, arxiv velocity). Closer to SEC 8-K scanner pattern than to e10 RSS pattern. Edge window = hours, not ms — retail-accessible if it exists. Falsification risk = high per e10 precedent.

### Category C — Labor-yield pivots (not really "similar")

1. **Airdrop / testnet farming.** Automation tractable using our async patterns (2-4 week build). Sybil-detection is now the whole game — LayerZero filtered millions in 2024. Realistic: $5-20k/year at $5-10k deployed with 5-15 hrs/week ongoing opsec. NZ tax treats as income.
2. **Matched betting / card flipping / sneaker flipping.** Scanner pattern applies, physical labor required.

### Category D — Productize existing work

1. **Portfolio → inbound consulting.** Keep repo public, footer "available for prediction-market research engagements". Zero recurring marketing. Realistic: $0 until someone bites, then $5-20k per engagement. **Best fit for "can't be bothered with marketing".**
2. **One-time Gumroad report** ($99-299, private code bundle). One launch post, then passive. Cap ~$1-5k total.
3. **Paid alerts (Telegram / Discord).** Recurring service — effectively a part-time job. Skip.
4. **Data API to quant shops.** Requires cold outreach. Skip.

Decision on **repo visibility:** keep public. README already frames everything as falsified — there's no commercial secret to protect, and the portfolio/credibility value requires visibility.

---

## Meta-lessons from this brainstorm

1. **"Similar work + free money" is a contradiction at our profile.** Every liquid market with a retail-tractable scanner has been arbed flat. The directions that clear 10% yield either (a) require labor (matched betting, farming) or (b) monetize the research itself (consulting).
2. **The e10 falsification pattern applies to any news-leak-to-market thesis, including AI.** Before rebuilding that shape in a new vertical, the three calibration bugs from e10 (low_confidence threshold, baseline σ instability, feed-health coverage) must be fixed, and the 3× control-ratio decision gate must be pre-committed.
3. **The project's highest-leverage asset is the methodology, not the code.** The ÷5 rule, counter-memos, pre-committed kill criteria, and raw-before-parameterized ordering are what produced 10 consecutive clean kills. Any pivot should preserve this discipline; it's what separates this work from the Twitter strategy-guide universe.

---

## Current state (2026-04-21)

- No direction committed.
- No code changed since project closure.
- User is actively evaluating pivots; open questions at session end were:
  - Productize vs research vs farm vs "free-money" scanner?
  - AI-market scanner: news-leak repeat of e10, Kalshi×Poly cross-venue, or infra-signal variant?
- `experiments/e16_calibration_study/` exists on disk (untracked) — presence noted, contents not inspected this session.

## If resuming

Pick one:
- **Yield run** → sketch Pendle/Ethena APY scanner adapting gamma/clob poll pattern.
- **AI Kalshi×Poly arb** → enumerate overlapping AI markets across both venues, baseline the price-gap distribution, capital/exec requirements.
- **AI infra-signal scanner** → scope HuggingFace + GitHub + DNS monitoring, pre-commit the e10-style decision gate before building.
- **Productize** → write the HN post, add the consulting footer, done.
- **Labor-yield** → minimum-viable airdrop farming automation using existing async infra.
