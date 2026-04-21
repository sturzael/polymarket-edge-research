# Agent B — Decisions / Methodology

## Data source
- Primary: `experiments/e16_calibration_study/data/05_tm7d_prices_sports_deep.parquet` (2,025 sports markets with T-7d snapshots).
- Joined to `01_markets_audit.parquet` on `condition_id` to bring in `end_date` (resolution date) and `created_at`.

## Time axis
- Chose **`end_date`** (resolution date) rather than `created_at`, because the research question is 'has this FLB been arbed away?' — the relevant clock is when the market actually resolved, not when it was listed.

## Split strategy
- Used **equal-count** (quantile) splits rather than equal-time-length. Equal-count keeps each slice's n similar, which stabilises standard errors; equal-time-length would pile most markets into the recent tail (Polymarket volume grew through 2024–2026).
- Halves = 2 slices, thirds = 3 slices, quarters = 4 slices; each sorted by `end_date` ascending.

## Core FLB zone
- The e16 study cited '0.55-0.60 bucket +25.8pp, n≈628'. In this parquet the 0.50-0.60 band (two 5pp buckets) contains 220 markets; that aggregated band is the closest match to the cited 628-figure and is what I use as the 'core FLB zone' for the headline trend test. I also report the strict 0.55-0.60 bucket separately for exact reproducibility.

## Direction rule
- |delta first→last| < 0.05 → **stable**; delta > 0 → **strengthening**; delta < 0 → **decaying**. The 5pp threshold is arbitrary but consistent with the e16 headline effect size (~25.8pp), so a <5pp drift is materially within noise for the spot estimate.

## Z-scores
- Binomial one-sample z vs null yes_rate = bucket_mid; SE = sqrt(p(1-p)/n). Reported per-bucket in the JSON and findings tables.

## Rolling / sliding window
- The task asked about rolling-quarter splits 'if sample supports it'. I report 4 non-overlapping quarters (by end_date quantile). Did not run overlapping rolling windows — non-overlapping quarters are cleaner and the sample per slice (~500) is too small to subdivide further without n collapsing in individual 5pp buckets.

## Core-FLB-zone correction
- On re-reading the e16 FINDINGS.md I noted the "628 markets" figure was the mixed-category n=1,463 T-7d pull (sports subset), **not** the authoritative sports-deep 2,025 parquet. The authoritative bucket is n=120 strict 0.55-0.60 with +25.8pp at z=7.6. I updated FINDINGS.md to make this explicit and treat the **strict 0.55-0.60 bucket (n=120)** as the primary headline-test artifact. I retain the 0.50-0.60 two-bucket aggregate (n=220) as a robustness check.

## Commits
- Attempted `git add experiments/e23_stratification/b_temporal/` early on; it succeeded in staging my files but also surfaced many unrelated / sibling-agent files as untracked in `git status`. Attempts to `git reset HEAD` and `git restore --staged .` to narrow the staged set were blocked by the sandbox (permission denied). Rather than create a commit that would sweep in unrelated work-in-progress from parallel agents, I left the b_temporal artifacts unstaged in the working tree for a human or an orchestrator commit step. All four deliverables are present at `experiments/e23_stratification/b_temporal/` — FINDINGS.md, VERDICT.md, DECISIONS.md, analyze.py, and data/temporal_calibration.json.
