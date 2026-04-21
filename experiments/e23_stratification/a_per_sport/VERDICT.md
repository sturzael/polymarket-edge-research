# Per-Sport Deployability Verdict

**Criterion for deployability (0.55–0.60 bucket):** n ≥ 20 AND z ≥ 2 (the e16 study-wide two-sigma threshold). Z < 2 means we cannot reject the null of no FLB in that sport at the peak bucket, and n < 20 means sample is too small to test.

**Deployable (signal survives per-sport stratification):** MLB.

**Not deployable — sample too small to test in critical bucket:** F1, NBA, NFL, NHL, SOCCER, TENNIS, UFC_BOXING.

**Not deployable — signal does not reach z≥2 at sport level:** (none).

**One-paragraph summary.** Of the 8 sport categories in the n=2,025 sports-deep sample, only **MLB** passes both sample-size (n_bucket ≥ 20) and significance (z ≥ 2) hurdles at the critical 0.55–0.60 bucket — with n=54, yes_rate 94.4%, dev +36.9pp, z=+11.85. MLB alone contributes 45% of the markets in the critical bucket and carries the bulk of the e16 aggregate signal. Seven sports (NBA, NHL, NFL, tennis, F1, soccer, UFC/boxing) fall under the n<20 insufficient-sample flag at the 0.55–0.60 bucket; of those, NHL (n=11, +33.4pp, z=3.85) and NFL (n=8, +30.0pp, z=2.57) point strongly in the same direction as MLB despite small n, while NBA points positive but weakly (n=19, z=1.60), and the remaining four show no or negative effect. **For deployment from this dataset alone: MLB is the only sport where the 0.55–0.60 signal is firmly validated. NHL/NFL are directionally supportive but need a larger sample before trading.** Adjacent favorite buckets (0.60–0.80) also show per-sport significance for MLB, NBA, NHL, and tennis, so a broader-bucket deployment (not just 0.55–0.60) widens the deployable universe to roughly those four sports — at the cost of mixing in cells that e16 did not single out as the peak. F1, soccer, and UFC/boxing show no clear per-sport FLB at T-7d in this sample and should be excluded pending more data. **Bottom line:** the e16 aggregate FLB is not a uniform 'all sports' phenomenon — it is primarily an MLB phenomenon with supportive hints in NHL/NFL/NBA and weak-to-absent signal in F1, soccer, UFC/boxing. A per-sport filter on entry is recommended over a blanket 'any sport' strategy.

## Detail per sport

- **MLB** (n_total=465): DEPLOYABLE — n_bucket=54, dev=+36.9pp, z=+11.85
- **NHL** (n_total=237): INSUFFICIENT SAMPLE — n_bucket=11 < 20
- **NFL** (n_total=166): INSUFFICIENT SAMPLE — n_bucket=8 < 20
- **NBA** (n_total=336): INSUFFICIENT SAMPLE — n_bucket=19 < 20
- **UFC_BOXING** (n_total=138): INSUFFICIENT SAMPLE — n_bucket=9 < 20
- **SOCCER** (n_total=126): INSUFFICIENT SAMPLE — n_bucket=6 < 20
- **TENNIS** (n_total=301): INSUFFICIENT SAMPLE — n_bucket=11 < 20
- **F1** (n_total=256): INSUFFICIENT SAMPLE — n_bucket=2 < 20
