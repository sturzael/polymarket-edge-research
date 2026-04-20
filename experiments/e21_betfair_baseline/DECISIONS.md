# e21 Decisions log

## 2026-04-20: use same bucketing as e16

5pp buckets, standard-error z-scoring from binomial SE:
- z = (yes_rate - bucket_mid) / sqrt(bucket_mid * (1 - bucket_mid) / n)

Same bucket labels (0.00-0.05, ..., 0.95-1.00). Same midpoints (bucket_lo + 0.025).

## 2026-04-20: T-anchor choice

Polymarket baseline used T-7d fixed time. For Betfair we need the closest equivalent.
Betfair horse racing markets typically don't have meaningful volume 7 days out
(markets often only open 24-48h before the event). For football/soccer we can get
T-7d easily.

Decision: if we find Betfair horse racing data, anchor at T-24h or last-traded
pre-race price (since that's where academic FLB literature also measures).
Document whichever anchor we use. If we find football data with deeper history,
anchor at T-7d for direct Polymarket comparison.

