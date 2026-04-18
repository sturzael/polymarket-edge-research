# e9 — Polymarket crypto-barrier wallet intel

Source: trades for 40 April-17 barrier markets tracked in `probe.db` pulled via `data-api.polymarket.com`. 4,946 trades across 750 distinct wallets. For the top-20 wallets by barrier-market notional we then pulled up to 2,000 trades of full Polymarket history and all open positions.

## Top-level findings

- **Concentration on barriers is moderate.** Top-20 wallets drive 40% of barrier-market notional ($157,548 of $397,703).

- **9/20 top wallets are multi-market operators** (active on ≥5 of the 40 barriers). The rest are single-market whales who took one big position and stopped.

- **5/20 top wallets use the 0x-prefixed default display name** — i.e. they never set a profile name. Typical signature of execution-only bots or fresh wallets, not retail users.

- **9/20 top barrier wallets also trade updown-5m** (crypto 5-min up/down — the *other* thing this repo's probe tracks) — 3478 distinct updown markets touched in aggregate. Only 0 of them overlap with the probe's specific April-17/18 cohort because the probe has only been running ~2 days; the wallets' recent history predates that window.

- **Aggregate P&L across top-20:** realized $72,904, unrealized-only $111,797. These are meaningful book sizes — not hobbyist traders.


## Top-20 wallet table

| # | Wallet | Name | Barriers hit | Barrier notional | Vertical mix (% notional, last ≤2k trades) | Realized P&L | Auto-name? |
|---|---|---|---|---|---|---|---|
| 1 | `0x6e1d5040…` | Respectful-Clan | 8 | $21,123 | barrier:57% ladder:28% other:16% | $99,385 | y |
| 2 | `0x54030db9…` | Large-Bracelet | 2 | $16,919 | barrier:53% ladder:39% | $0 |  |
| 3 | `0x239a14ee…` | Stable-Factory | 2 | $15,913 | barrier:34% ladder:45% other:21% | $0 |  |
| 4 | `0x23222038…` | Evil-Pint | 7 | $14,573 | barrier:14% ladder:76% other:10% | $0 |  |
| 5 | `0x8611527a…` | Open-Medium | 16 | $13,740 | barrier:22% ladder:47% other:31% | $2 |  |
| 6 | `0x551b3b17…` | Long-Alluvium | 1 | $11,812 | barrier:20% ladder:73% other:5% | $0 |  |
| 7 | `0x06dc5182…` | Impressive-Steak | 17 | $11,491 | barrier:29% ladder:38% other:33% | $-81,735 | y |
| 8 | `0x34e8ef69…` | Definitive-Yin | 10 | $8,103 | barrier:29% ladder:48% other:23% | $0 |  |
| 9 | `0xbe601e36…` | Dense-Muscat | 1 | $6,520 | barrier:54% other:46% | $0 | y |
| 10 | `0x46992d0e…` | Happy-Default | 1 | $5,523 | barrier:6% updown-5m:20% ladder:8% sports:8% other:57% | $0 |  |
| 11 | `0xeee92f1c…` | Austere-Heavy | 6 | $4,851 | barrier:78% other:22% | $58,341 |  |
| 12 | `0x8eeb7381…` | Bony-Flag | 12 | $4,228 | barrier:25% ladder:40% other:35% | $1 |  |
| 13 | `0xbc1f5a7f…` | Deafening-Refund | 2 | $3,602 | barrier:66% ladder:30% | $0 | y |
| 14 | `0x6e0d6450…` | Infatuated-Pigsty | 2 | $3,019 | barrier:14% updown-5m:83% | $0 |  |
| 15 | `0xe6266639…` | Hollow-Yang | 1 | $2,929 | barrier:25% ladder:41% other:32% | $0 |  |
| 16 | `0x726fd4fd…` | Testy-Connection | 3 | $2,768 | barrier:39% ladder:21% other:40% | $-3,090 |  |
| 17 | `0xeea6b30a…` | Polished-Episode | 5 | $2,719 | barrier:11% ladder:45% sports:34% other:11% | $0 |  |
| 18 | `0x14e296e2…` | Digital-Archaeolog | 2 | $2,689 | barrier:84% updown-5m:12% | $0 |  |
| 19 | `0xdd8c8c4d…` | Upbeat-Establishme | 1 | $2,536 | barrier:20% updown-5m:77% | $0 | y |
| 20 | `0xafc5ecc8…` | Gifted-Nursery | 13 | $2,492 | barrier:13% ladder:46% other:41% | $0 |  |

## Cross-vertical activity — are barrier wallets also in our repo's universe?

The repo's probe tracks two kinds of Polymarket markets: updown-5m (crypto up/down, 5-min duration) and crypto-barrier (the same 40 we sampled here). If a top barrier wallet also trades updown-5m, that's a 'yes' — they operate across the verticals we care about.

### Top-20 barrier wallets — updown-5m activity

Slug-based match across entire wallet history (not just probe cohort). `# probe overlap` = subset that also hit the specific markets this repo's probe was watching on April 17-18.

| Wallet | Name | # updown trades | # distinct updown markets | Updown notional | # probe overlap |
|---|---|---|---|---|---|
| `0x6e0d6450…` | Infatuated-Pigst | 1930 | 1804 | $31,231 | 0 |
| `0x46992d0e…` | Happy-Default | 16 | 11 | $17,942 | 0 |
| `0x14e296e2…` | Digital-Archaeol | 1503 | 1410 | $10,937 | 0 |
| `0xe6266639…` | Hollow-Yang | 6 | 3 | $9,773 | 0 |
| `0xdd8c8c4d…` | Upbeat-Establish | 53 | 21 | $9,651 | 0 |
| `0x239a14ee…` | Stable-Factory | 392 | 203 | $5,157 | 0 |
| `0x54030db9…` | Large-Bracelet | 23 | 23 | $1,946 | 0 |
| `0x8611527a…` | Open-Medium | 2 | 1 | $475 | 0 |
| `0xafc5ecc8…` | Gifted-Nursery | 4 | 2 | $117 | 0 |

### Broader vertical breakdown (all Polymarket markets, not just probe)

| Vertical | Notional (top-20 recent ≤2k each) | Share |
|---|---|---|
| crypto_ladder | $15,698,748 | 60.9% |
| crypto_barrier | $5,502,327 | 21.3% |
| other | $4,183,582 | 16.2% |
| sports | $266,617 | 1.0% |
| updown_5m | $87,229 | 0.3% |
| politics | $39,527 | 0.2% |

## Strategy-shape signals (top-20, by price bucket of all trades)

Penny-stub behaviour (lots of trades at ≤0.05 or ≥0.95) = dump-at-resolution or pre-placed limit exits. Middle-band (0.35–0.65) = active opinion-taking.

- **<=0.05:** 0.1% of top-20 aggregate notional
- **0.05-0.15:** 0.2% of top-20 aggregate notional
- **0.15-0.35:** 0.6% of top-20 aggregate notional
- **0.35-0.65:** 1.7% of top-20 aggregate notional
- **0.65-0.85:** 1.5% of top-20 aggregate notional
- **0.85-0.95:** 1.5% of top-20 aggregate notional
- **>0.95:** 94.4% of top-20 aggregate notional

## Entity-clustering observations

- 5 of 20 top wallets have unset profile names. A batch of freshly-funded bot wallets tends to look like this.

- Named multi-market operators (candidates for real individuals/desks):
  - `0x23222038…` — **Evil-Pint** (7 barriers, $14,573)
  - `0x8611527a…` — **Open-Medium** (16 barriers, $13,740)
  - `0x34e8ef69…` — **Definitive-Yin** (10 barriers, $8,103)
  - `0xeee92f1c…` — **Austere-Heavy** (6 barriers, $4,851)
  - `0x8eeb7381…` — **Bony-Flag** (12 barriers, $4,228)
  - `0xeea6b30a…` — **Polished-Episode** (5 barriers, $2,719)
  - `0xafc5ecc8…` — **Gifted-Nursery** (13 barriers, $2,492)

## Caveats

- Each top wallet's history is capped at 2,000 trades (data-api pagination practicality). Very active wallets' older trades are outside the window, so vertical-mix % reflects *recent* behaviour, not lifetime.

- Probe DB currently tracks only the April-17 crypto barriers. If there are large older barriers, top wallets there are not sampled.

- `realizedPnl` from `/positions` is per-position; positions resolved long ago may age out of the endpoint's window.


## Follow-ups

- **On-chain enrichment:** for each top wallet, hit Polygonscan via `transactionHash` (already in the JSONL) to find common funding sources — would answer the entity-clustering question properly.

- **Full-lifetime vertical mix:** paginate `/trades?user=` beyond 2,000 trades for the ~5 biggest operators to get a lifetime breakdown.

- **Price-vs-fair edge analysis:** join each barrier trade against `market_snapshots` for the same market to measure whether top wallets systematically buy below fair value (true arb) or move size at/above fair (MM-hedging / panic close-outs).

