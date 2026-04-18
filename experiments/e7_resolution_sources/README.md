# e7 — Resolution source audit

**Question:** What feeds do Polymarket crypto markets resolve against? Which spot websockets does v2 need to match?

**Method:** `SELECT resolution_source, COUNT(*) FROM markets WHERE is_crypto=1 GROUP BY 1` on a snapshot of the probe DB ~1h into the run (958 crypto markets discovered).

**Raw output:** `raw.txt`

## Findings

| source | count | share |
|---|---:|---:|
| `data.chain.link/streams/{asset}-usd` (6 feeds, one per underlying) | **846** | **88.3%** |
| `binance.com/en/trade/{PAIR}_USDT` (6 feeds) | **50** | **5.2%** |
| NULL (no resolution_source set) | 60 | 6.3% |
| liquipedia (mobilelegends) | 2 | 0.2% |

Chainlink distribution was perfectly uniform: 141 per asset across BTC/ETH/SOL/BNB/DOGE/XRP. That's almost exactly the 5m+15m+4h up/down series count (607 + 204 + 32 = 843), confirming the whole `*-updown-Nm-*` series resolves against Chainlink Data Streams.

The Binance-resolved markets are the ~50 longer-dated crypto markets (e.g. `will-ethereum-reach-2500-on-april-17`). These are daily/weekly contracts.

`umaResolutionStatus` is **NULL for all 958 markets** — gamma-api doesn't populate that field outside of dispute scenarios.

## Implications for v2

1. **Chainlink Data Streams is the authoritative spot feed to match**, not Binance/Coinbase. All 5m/15m/4h up/down contracts settle against it.
   - Chainlink Data Streams is a low-latency oracle service; public access requires the Chainlink node / streams verifier. Plan investigation before building the full collector.
   - Fallback: Chainlink's on-chain aggregator contracts on Polygon provide a lagged version. Acceptable for measurement but not for trading.
2. **Our current Binance-via-ccxt spot collection would introduce exactly the "reference feed mismatch" validity bug the user flagged** — "spot lead" might just be Binance↔Chainlink lag.
3. For the ~5% of Binance-resolved markets we can keep using ccxt. Separate track.
4. The 2 mobilelegends markets are false-positives from our `detect_crypto` keyword match — probably a market with "bitcoin" in an unrelated context. Can be filtered out by checking `resolution_source` matches Chainlink/Binance crypto domains.

## Status
Complete. Insight integrated into main FINDINGS.md.
