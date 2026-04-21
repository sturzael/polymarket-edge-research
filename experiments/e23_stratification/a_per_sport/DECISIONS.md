# Per-Sport Stratification — Methodology Decisions

Agent A (per-sport) of e23 parallel stratification. All decisions below were made autonomously without stopping for approval, per the task spec.

## Input data
- **Source:** `experiments/e16_calibration_study/data/05_tm7d_prices_sports_deep.parquet` (n=2,025 sports markets, authoritative per e16 FINDINGS §2e).
- The task brief cited "n≈628 sports markets." That figure referred to an earlier, shallower pull (`05_tm7d_prices.parquet`) that mixed sports with non-sports. The deep sports-only pull with n=2,025 is the authoritative dataset and the 120-market 0.55-0.60 bucket (the +25.8pp / z=7.6 headline) lives there. We use the deeper dataset.

## Bucketing and statistics
- Buckets: 5pp wide, `[lo, lo+0.05)` per `i/100` from 0 to 1 — identical to e16 `05_fixed_time_calibration.py::bucket_label` / `bucket_mid`.
- `bucket_mid(p) = lo + 0.025`.
- `deviation = yes_rate − bucket_mid` (pp).
- **z-score:** matches e16's "binomial standard error per bucket, |dev|/SE" wording. After cross-checking e16's reported z=7.6 at n=120 / yr=0.833 / dev=+0.2583, we confirmed e16 used the **observed-yes_rate** Wald SE: `SE = sqrt(yes_rate·(1−yes_rate)/n)`.
  - With that formula, our overall 0.55-0.60 bucket reproduces z=7.59 vs e16's 7.6 — exact match (rounding).
  - Alternative (mid-based SE) would give z=5.72 — more conservative but not what e16 published. To keep cross-table comparability we stick with e16's formulation.
  - Edge case: when `yes_rate ∈ {0, 1}` we fall back to mid-based SE (prevents division by zero). Rare; affects only terminal buckets that already pass/fail clearly on sign alone.

## Sport name parsing
- `sports_nba` → `NBA`, `sports_ufc_boxing` → `UFC_BOXING`, etc. Strip `sports_` prefix and uppercase.
- Sports present in the parquet: MLB, NBA, TENNIS, F1, NHL, NFL, UFC_BOXING, SOCCER. The task brief also listed "boxing" separately, but in this dataset boxing is merged with UFC under `sports_ufc_boxing`. We preserve the dataset's granularity rather than guessing a split.

## Critical-bucket choice
- The 0.55-0.60 bucket is the e16 peak (yes_rate 83.3%, +25.8pp, z=7.6) and is the natural reference cell. We report n / yes_rate / deviation / z there per sport and flag `n<20` as insufficient.
- We also report the full bucket table per sport (not just the critical cell) so readers can see whether adjacent buckets agree.

## Insufficient-sample threshold
- `n_bucket < 20` flagged as INSUFFICIENT. Twenty is the point at which a binomial proportion estimate has SE ≤ 0.112 at p=0.5 — below that, a +25pp effect cannot be distinguished from noise at the 2-sigma level. This is the same "z≥2 means significant" convention e16 used.

## Deployability threshold
- A sport is DEPLOYABLE if `n_bucket ≥ 20` AND `z ≥ 2` in the 0.55-0.60 bucket. This is not an economic-viability test (fees, spread, capacity) — those belong to agents C and F. It is a "does the per-sport signal replicate" test.

## Things explicitly NOT done (scope-bounded)
- No re-extraction of trades from the API — brief says no new API calls needed.
- No bid/ask spread adjustment — e16 already flagged this as a 2-4pp haircut and it's not per-sport-specific in the parquet.
- No temporal stratification — that's Agent B.
- No liquidity-tier split — that's Agent C.
- No sub-category (game-outcome vs futures vs props) — that's Agent E.

## Git commits
- Ran `git add experiments/e23_stratification/a_per_sport/` to stage my outputs. That pulled in many sibling files (other e23 agents' outputs, e20/e22 outputs, .gitignore change) that `git add -A`-style behavior had already staged in the working tree. Attempted to unstage with `git reset HEAD` and `git restore --staged .` — both blocked by the sandbox permission layer.
- Left staging in current state; parent agent will handle the final commit. My outputs (FINDINGS.md, VERDICT.md, DECISIONS.md, analyze.py, data/per_sport_calibration.json) are all in place on disk. If parent commit fails, outputs are readable via filesystem.
- `experiments/e23_stratification/` was untracked at start (no prior e23 directory existed).
