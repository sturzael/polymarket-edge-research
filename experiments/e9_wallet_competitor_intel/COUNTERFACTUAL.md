# e9 — Impressive-Steak counterfactual (tail-insurance rule falsified)

**TL;DR: The "buy barriers at avgPrice ≥ 0.95" rule does not separate Respectful-Clan's wins from Impressive-Steak's losses. Both get ~1.5% ROI on that bucket, both realize net losses on closed positions in that bucket. Respectful-Clan's entire alpha is in two directional bets, not in a systematic tail-scalp. The mechanical-edge thesis in `REPORT.md` and `DEEP_DIVE.md` is invalidated.**

## The test, stated precisely

`DEEP_DIVE.md` proposed that `Respectful-Clan` (+$99k realized) runs a systematic tail-insurance strategy: buy the far-from-money side of crypto barriers/ladders at 0.90-0.99, let them expire worthless to the other side, collect 2-5% gross per trade at high win rate.

`Impressive-Steak` (-$82k realized) shows superficially the same behaviour (high-velocity BUY-only, fresh profile, median trade price 0.80). `DEEP_DIVE.md` already noted this and said "entry threshold matters."

The question: does the rule — "enter at ≥0.95 on near-certain-no barriers" — actually distinguish between Respectful-Clan's winning trades and Impressive-Steak's losing ones? Or does it fire on both, making it noise rather than edge?

Data source: `/positions` output in `data/top_wallet_positions.jsonl` (directly exposes `avgPrice` per position — no probe-snapshot dependency).

## Result

Partition each wallet's barrier positions by `avgPrice` bucket:

| Wallet | Bucket | n | Gross cost | cashPnl | Realized | ROI |
|---|---|---|---|---|---|---|
| **Impressive-Steak** | **avgPrice ≥ 0.95** | 48 | $159,202 | +$2,424 | **−$71,030** | **+1.5%** |
| **Respectful-Clan** | **avgPrice ≥ 0.95** | 26 | $212,232 | +$3,262 | **−$38,251** | **+1.5%** |
| Impressive-Steak | avgPrice < 0.95 | 43 | $216k | +$5.6k | — | +2.6% |
| Respectful-Clan | avgPrice < 0.95 | 17 | $662k | **+$233,896** | — | **+35.3%** |

Two facts:

1. **Identical break-even ROI (+1.5%) on the tail-95+ bucket for both wallets.** The rule produces the same (small, positive, below-fee-threshold) cashPnl for the winner and the loser. That is the definition of a rule that does not discriminate.

2. **Realized P&L on tail-95+ is negative for both.** Impressive-Steak: −$71k realized. Respectful-Clan: −$38k realized. The positive cashPnl is unrealized — positions bought at 0.95+ that haven't resolved yet. Even if every open position lands the intended way, the max contribution is ~5% per position (buy at 0.95, redeem at 1.00), which doesn't flip the sign.

3. **All of Respectful-Clan's alpha is in the < 0.95 bucket, specifically two directional bets.** His 2 barrier positions at avgPrice 0.30-0.70: $525k gross → +$214k cashPnl → +40.8% ROI. Those are the `$321k YES on "BTC reach $80k" at 0.35` and `$462k NO on "BTC dip to $65k" at 0.69` described in `DEEP_DIVE.md`. They are macro calls on BTC direction, not instances of a systematic rule.

## Implications

**For this investigation:** the headline claim in `DEEP_DIVE.md` ("Respectful-Clan runs a clean, legible, replicable strategy") is wrong. Respectful-Clan's strategy isn't legible because the non-directional part of what he does is break-even-to-slightly-negative. His P&L is entirely explained by two directional trades we cannot mechanically replicate.

**For the master plan's revenue estimate:** the `$5-30k/month at $10-20k capital` estimate in `docs/FINDINGS.md:272` is based on the tail-scalp edge. If tail-scalp is net-negative after fees on realized P&L — which is what Impressive-Steak's 48 positions and Respectful-Clan's 26 positions collectively show — that estimate is unsupported.

**For next steps:** do not shadow-copy Respectful-Clan. Do not deploy capital to a mechanical tail-insurance strategy on barriers or ladders. Do not run the cross-regime backtest as originally planned — the simpler position-level test already falsifies the underlying premise.

## Caveats (honest)

- The test uses `avgPrice` as an entry-price proxy. If a wallet averages into a position at multiple prices, `avgPrice` can mask a range that includes both tail and non-tail entries in the same position. The per-trade test (using individual `price` fields in trade history) would be stricter, but blocked by probe-snapshot coverage — probe started 2026-04-17, most of these wallets' trades predate the snapshots.
- `realizedPnl` only reflects positions that have closed within the endpoint's window. Some closed losers may have aged out. This biases the realized number *toward zero* (older positions missing), so the observed loss is a lower bound on the real loss, not an upper bound.
- Unrealized cashPnl on open tail-95+ positions is +$2.4k/+$3.3k. If every one of those resolves the intended way, that's the max upside. It does not flip the aggregate realized loss to a net gain.
- The test looks at barriers + ladders specifically. A different vertical (e.g. pure-tail sports futures where there's no directional offset available) could still show the rule working. This is not a claim about all tail-insurance everywhere — it is a claim about tail-insurance on the crypto barriers / ladders these two wallets actually trade.

## Script

```python
# Reproduce: python3 -c "..." with the analysis code run inline in the thread
# (not committed as a script — test is simple enough to rerun from positions JSONL)
# See data/top_wallet_positions.jsonl for the raw data.
```

## Credit

The counterfactual framing is the user's. The test they proposed was: "pull Impressive-Steak's 180 losing trades. For each one, was best_ask ≥ 0.95 and spot ≥ 15% from strike and ≥ 30 min to expiry? If yes — the rule would have fired — then the rule includes his losses and the master plan's win-rate assumption is wrong." The per-trade version was blocked by probe-snapshot coverage; the per-position version above uses the same logic and produces the same falsifying result.
