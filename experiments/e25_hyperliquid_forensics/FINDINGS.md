# Hyperliquid Top-Wallet Momentum Decomposition

_Generated 2026-04-21 UTC. Methodology ported from Polymarket wallet-forensics study (4h lookback, ±0.5% threshold)._

## Section 1 — Sample summary

- 24 wallets pulled from HL all-time-PnL top-50. 14 have ≥20 analyzable BTC/ETH/SOL opens; 10 marked UNDERPOWERED.
- Total entries analyzed: **21,648** (Open Long + Open Short on BTC/ETH/SOL, both price endpoints resolvable).
- Per-asset: BTC=10,852; ETH=7,727; SOL=3,069.
- Bucket totals: momentum=5,088 (23.5%), contrarian=7,034 (32.5%), flat-regime=9,526 (44.0%).
- Entry-time range: 2026-03-23 → 2026-04-21 (30 days). Price source: Binance 1m klines (43,691 candles each).

## Section 2 — Ranked table

| rank | wallet | allTime PnL | month PnL | n_entries | momentum % | dir. % | label | notes |
|---:|---|---:|---:|---:|---:|---:|---|---|
| 2 | `0xecb63caa…2b00` | $203.3M | $1.7M | 869 | 0.1 | 0.7 | STRUCTURAL | BTC 84% |
| 4 | `0x5b5d5120…c060` | $180.3M | $4.0M | 2940 | 57.8 | 100.0 | MIXED | BTC 98% |
| 5 | `0x7fdafde5…17d1` | $159.5M | $-785k | 4413 | 3.1 | 4.2 | STRUCTURAL | ETH 73% |
| 9 | `0xb83de012…6e36` | $123.6M | $46k | 2197 | 19.7 | 24.9 | STRUCTURAL | SOL 71% |
| 11 | `0x880ac484…311c` | $114.0M | $663k | 3136 | 16.6 | 39.6 | STRUCTURAL | ETH 39% |
| 14 | `0xa312114b…ad1e` | $96.4M | $2.6M | 0 | — | — | UNDERPOWERED | no BTC/ETH/SOL opens |
| 16 | `0x2e3d94f0…dd14` | $84.6M | $-614k | 0 | — | — | UNDERPOWERED | no Open-dir fills |
| 17 | `0xd4758770…1a91` | $81.7M | $674k | 634 | 17.4 | 57.0 | STRUCTURAL | BTC 100% |
| 18 | `0x45d26f28…4029` | $80.0M | $-389k | 15 | 0.0 | — | UNDERPOWERED | 15 tradable opens |
| 19 | `0xbdfa4f44…5c50` | $76.0M | $772k | 0 | — | — | UNDERPOWERED | no BTC/ETH/SOL opens |
| 21 | `0x023a3d05…2355` | $67.2M | $1.8M | 3987 | 30.8 | 58.0 | MIXED | ETH 54% |
| 23 | `0x5d2f4460…9bb7` | $63.1M | $1.8M | 0 | — | — | UNDERPOWERED | no BTC/ETH/SOL opens |
| 24 | `0x8af700ba…fa05` | $62.9M | $3.6M | 0 | — | — | UNDERPOWERED | no BTC/ETH/SOL opens |
| 27 | `0x35d1151e…acb1` | $59.1M | $1.2M | 1820 | 30.4 | 67.2 | MIXED | BTC 100% |
| 28 | `0x8e096995…70c9` | $58.9M | $-879k | 0 | — | — | UNDERPOWERED | no BTC/ETH/SOL opens |
| 32 | `0x939f9503…04d2` | $52.2M | $3.1M | 0 | — | — | UNDERPOWERED | no Open-dir fills |
| 35 | `0x7dacca32…f410` | $47.3M | $-346k | 0 | — | — | UNDERPOWERED | no BTC/ETH/SOL opens |
| 36 | `0x010461c1…703a` | $47.1M | $-15k | 134 | 0.0 | 0.0 | STRUCTURAL | ETH 49% |
| 38 | `0xcac19662…26b3` | $44.0M | $-790k | 186 | 100.0 | 100.0 | MOM-LUCKY | BTC 100% |
| 40 | `0x162cc7c8…8185` | $41.9M | $463k | 600 | 26.7 | 68.4 | STRUCTURAL | SOL 66% |
| 42 | `0x856c3503…910d` | $39.3M | $1.6M | 81 | 0.0 | 0.0 | STRUCTURAL | ETH 94% |
| 45 | `0x31ca8395…974b` | $37.2M | $-361k | 160 | 10.6 | 100.0 | STRUCTURAL | ETH 43% |
| 49 | `0x418aa6bf…8888` | $34.1M | $-1.4M | 476 | 8.6 | 15.5 | STRUCTURAL | BTC 80% |
| 50 | `0x82d8dc80…32ff` | $33.1M | $0 | 0 | — | — | UNDERPOWERED | no Open-dir fills |

_`momentum %` counts flat-regime (|4h ret|<0.5%) as non-momentum. `dir. %` = momentum / (momentum+contrarian), excludes flat regime — closer to the original Polymarket "215/223 within 60s of BTC >0.5% move" framing._

## Section 3 — Structural candidates (momentum % < 30)

- rank 2 `0xecb63caa` — $203.3M / mo $1.7M, n=869 (BTC). 84% flat-regime — opens almost entirely in quiet markets; MM/mean-reversion signature.
- rank 5 `0x7fdafde5` — $159.5M / mo $-785k, n=4413 (ETH). 72% contrarian — fades 4h trends.
- rank 9 `0xb83de012` — $123.6M / mo $46k, n=2197 (SOL). 59% contrarian, SOL-dominant fader.
- rank 11 `0x880ac484` — $114.0M / mo $663k, n=3136 (ETH). Mixed-contrarian (mom 17 / con 25 / neu 58).
- rank 17 `0xd4758770` — $81.7M / mo $674k, n=634 (BTC only). 70% flat-regime BTC trader.
- rank 36 `0x010461c1` — $47.1M / mo $-15k, n=134. 86% flat-regime.
- rank 40 `0x162cc7c8` — $41.9M / mo $463k, n=600. 61% flat-regime, SOL-heavy.
- rank 42 `0x856c3503` — $39.3M / mo $1.6M, n=81 (ETH). 95% contrarian — strongest clean fader in sample.
- rank 45 `0x31ca8395` — $37.2M / mo $-361k, n=160. 89% flat-regime.
- rank 49 `0x418aa6bf` — $34.1M / mo $-1.4M, n=476. Mixed-contrarian, losing month.

## Section 4 — Momentum-lucky (momentum % > 80)

- rank 38 `0xcac19662` — $44.0M / mo $-790k, n=186, 100% momentum-coincident (BTC-only). Pure trend-rider — bleeding this month in a rangey regime. Classic fade candidate on trend exhaustion.

## Section 5 — Distribution shape

```
momentum % across 14 analyzable wallets:
  [  0- 10%]  5  #####
  [ 10- 20%]  4  ####
  [ 20- 30%]  1  #
  [ 30- 40%]  2  ##
  [ 40- 50%]  0
  [ 50- 60%]  1  #
  [ 60- 70%]  0
  [ 70- 80%]  0
  [ 80- 90%]  0
  [ 90-100%]  0
  [   100%]  1  #
```

Heavily **left-skewed, not bimodal**: 9 of 14 sit below 20%; only 2 above 50%. This is the *inverse* of the Polymarket BTC-spike finding (where wallets piled at 90%+). Strong caveat: the `dir. %` column — which excludes flat-regime entries — lifts most low-mom wallets back to 50–70%, meaning much of the "structural" label here reflects wallets trading in quiet 4h windows rather than genuinely fading big moves. The true heavy faders are ranks 5, 9, 42, 49.

## Section 6 — Notable observations

- **Rank-2 `0xecb63caa`** ($203M) is the highest-PnL analyzable wallet and is flagged STRUCTURAL with 84% flat-regime. High-frequency market-making fingerprint — not a momentum play. The one most worth investigating further.
- **Six top-20 wallets** (ranks 14, 16, 19, 23, 24, 28) drop out entirely — they don't trade BTC/ETH/SOL. HL top-wallet PnL is concentrated in HYPE + synthetics (xyz:CL, xyz:BRENTOIL, xyz:SILVER, @107, @210, LIT, MON, XMR, TAO). **The core-asset slice analyzed here is not representative of how HL's top wallets actually make money.**
- **Concentration risk**: 4 analyzable wallets have >95% of entries in one asset (ranks 4, 17, 27, 38 — all BTC). Their `momentum %` is a statement about a single asset's regime, not a cross-asset style.
- **Rank-5 `0x7fdafde5`** ($159M allTime, $-785k month) is the cleanest large-sample contrarian: 72% contrarian over 4,413 entries. The recent losing month doesn't invalidate the signature.
- **Month PnL is mixed across all buckets** — structural ≠ profitable-now. Two structural wallets are losing the month; the sole momentum-lucky wallet is also losing. Small sample, no clean regime call.

## Section 7 — Caveats and sample limitations

- Entry = `dir ∈ {Open Long, Open Short}` only. Flips (`Long > Short`, `Short > Long`) and spot `Buy/Sell` dropped — under-samples pure-flip styles.
- `|4h ret| < 0.5%` bucketed as flat (counts against `momentum %`). Mechanical bias toward STRUCTURAL for quiet-market traders; see `dir. %`.
- 30-day window; subsample regime effects dominate — do **not** read labels as long-horizon style claims.
- 24 wallets → 14 analyzable is a case study, not a population. **Do not conclude "Hyperliquid has/lacks alpha" from this.**
- BTC/ETH/SOL perps only; HL's actual top-wallet book lives in synthetics/HYPE/spot pairs, not analyzed.
- Descriptive only — no return projections. Any copy-trade construct would warrant ÷5 haircut minimum, and probably shouldn't be attempted from n=14.
- Binance 1m closes used as off-exchange reference; 0.5% threshold is robust to HL-vs-Binance basis. 4h lookback ends at `t_entry − 1 min` with a 10-min max-gap guard.
