# Agent D — Market lifetime stratification

**Status:** Complete. Sandbox blocked direct MD writes; parent session persisted.
**Date:** 2026-04-20
**Data source:** `experiments/e16_calibration_study/data/05_tm7d_prices_sports_deep.parquet` (n=2,025 sports markets, T-7d ±12h, ≥3 trades in window). `duration_days` already present — no join needed.

## Tier definitions (total market lifespan = `end_date − created_at`)

| tier | rule | interpretation at T-7d snapshot |
|---|---|---|
| short | duration ≤ 14d | existed 1-7 days before snapshot (still fresh) |
| medium | 14 < duration ≤ 30 | existed 7-23 days before snapshot |
| long | duration > 30d | existed 23+ days before snapshot (mature book) |

## Tier overview (focus bucket 0.55-0.60)

| tier | n_total | n@0.55-0.60 | yes_rate | deviation | z | DSC_median |
|---|---:|---:|---:|---:|---:|---:|
| all sports | 2,025 | 120 | 0.833 | +25.8pp | +5.72 | 3.93d |
| **short** | 1,651 | **109** | **0.844** | **+26.9pp** | **+5.68** | **2.70d** |
| medium | 264 | 6 | 1.000 | +42.5pp | +2.11 | 8.75d |
| long | 110 | 5 | 0.400 | **−17.5pp** | −0.79 | 94.92d |

`DSC = days_since_creation_at_snapshot = duration_days − 7`.

**Insufficient-sample flags (n<20 in 0.55-0.60):** medium (n=6) and long (n=5). **Only short has a well-estimated focus cell** — and carries 91% of the aggregate bucket (109/120).

## Short tier full calibration (n=1,651)

| bucket | n | mid | yes_rate | dev | z |
|---|---:|---:|---:|---:|---:|
| 0.25-0.30 | 114 | 0.275 | 0.061 | −0.214 | −5.11 |
| 0.30-0.35 | 115 | 0.325 | 0.104 | −0.221 | −5.05 |
| 0.35-0.40 | 121 | 0.375 | 0.182 | −0.193 | −4.39 |
| 0.40-0.45 | 122 | 0.425 | 0.270 | −0.155 | −3.45 |
| 0.45-0.50 | 121 | 0.475 | 0.488 | +0.013 | +0.28 |
| 0.50-0.55 | 89 | 0.525 | 0.685 | +0.160 | +3.03 |
| **0.55-0.60** | **109** | **0.575** | **0.844** | **+0.269** | **+5.68** |
| 0.60-0.65 | 122 | 0.625 | 0.828 | +0.203 | +4.63 |
| 0.65-0.70 | 94 | 0.675 | 0.926 | +0.251 | +5.19 |
| 0.70-0.75 | 81 | 0.725 | 0.926 | +0.201 | +4.05 |
| 0.75-0.80 | 59 | 0.775 | 0.966 | +0.191 | +3.52 |
| 0.80-0.85 | 56 | 0.825 | 0.982 | +0.157 | +3.09 |

Sharp sign-flip at 0.50; classic S-shape; essentially replicates aggregate.

## Long tier full calibration (n=110)

| bucket | n | mid | yes_rate | dev | z |
|---|---:|---:|---:|---:|---:|
| 0.40-0.45 | 6 | 0.425 | 0.333 | −0.092 | −0.45 |
| **0.55-0.60** | **5** | **0.575** | **0.400** | **−0.175** | **−0.79** |
| 0.60-0.65 | 4 | 0.625 | 0.500 | −0.125 | −0.52 |
| 0.75-0.80 | 5 | 0.775 | 1.000 | +0.225 | +1.20 |
| 0.90-0.95 | 5 | 0.925 | 1.000 | +0.075 | +0.64 |

Focus cell sign-flipped (yes_rate 0.400 vs short tier's 0.844) but n=5 insufficient.

## Dose-response across 8 finer duration bins (favorites aggregate 0.50-0.80)

| duration | n_total | n_fav | yes_rate_fav | dev_fav_pp |
|---|---:|---:|---:|---:|
| 0-8.5d | 280 | 103 | 0.874 | +24.9pp |
| 8.5-10d | 624 | 244 | 0.877 | +25.2pp |
| 10-12d | 242 | 73 | 0.863 | +23.8pp |
| 12-14d | 505 | 134 | 0.791 | +16.6pp |
| 14-21d | 220 | 33 | 0.758 | +13.3pp |
| 21-30d | 44 | 13 | 0.692 | +6.7pp |
| 30-60d | 33 | 3 | 0.333 | **−29.2pp** (n=3) |
| 60-1000d | 77 | 13 | 0.615 | −1.0pp |

Monotone decline from ~+25pp (<12d) to ~+7pp (21-30d). Sign-flips at 30+d (n small).

## Interpretation

The FLB at T-7d is **strongly age-gated**. Short-lived markets (81.5% of the dataset) carry essentially all the 0.55-0.60 lift at z=+5.68. Profile is consistent with **pre-informed-flow mispricing** — retail-shaped prices that haven't been arbitraged — rather than a durable structural favorites premium.

Two secondary notes:
1. **DSC_median 2.7d for short tier** — half of short-tier markets had been trading <3 days at T-7d snapshot. The signal is largely in markets listed within a week of their event.
2. **Targetable population is large, not a rare corner.** Short-lived markets are the bulk of Polymarket sports, so a 0.55-0.60 strategy targets the majority of listings.

## Methodology notes

- Used deep parquet (n=2,025), not the shallower 628-market pull.
- Per-bucket z-score: `SE = sqrt(mid*(1-mid)/n)`, H0: yes_rate = bucket_mid.
- Insufficient-sample rule: n<20 per task brief.
- **Only 5.4% (110/2,025) have lifespan >30d.** Long-tier evidence is directional, not conclusive. Firmer read on "bias disappears in mature books" would need a targeted pull of multi-week championship / season-long markets, not a random pull from the same pool.
