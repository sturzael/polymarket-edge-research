# e9 deep dive — is there a successful bot we can actually investigate?

**Short answer: yes. `Respectful-Clan` (`0x6e1d5040…`) is the headline case — actively running right now, mechanically observable, and their strategy maps onto the MM opportunity already flagged in `docs/OPPORTUNITY_HOURLY_LADDER_MM.md`.**

## How I picked wallets to look at

From the top-20 in `REPORT.md`, I looked at the extremes:
- biggest winners (realized P&L): Respectful-Clan +$99k, Austere-Heavy +$58k
- biggest loser: Impressive-Steak −$82k
- highest market-breadth on updown-5m: Infatuated-Pigsty (1,804 markets), Digital-Archaeologist (1,410)

Then pulled: trade velocity, price-bucket distribution, buy-vs-sell mix, inter-trade gap, max trade size, current book value, open-position count.

## The wallets, one line each

| Wallet | What they do | Worth studying? |
|---|---|---|
| `Respectful-Clan` (`0x6e1d5040…`) | **52 trades/hr, 2-sec median gap, 1997/2000 BUY, $1.65M book, 304 open positions, spread across barriers + ladders.** +$99k realized. Auto-name. | **Yes — the cleanest case** |
| `Austere-Heavy` (`0xeee92f1c…`) | 5.6 trades/hr across 15 days. 2000/2000 BUY. 346 positions, -$91k unrealized, +$58k realized. 78% barrier focus. | Yes, but slower and messier |
| `Impressive-Steak` (`0x06dc5182…`) | 33 trades/hr, median buy price 0.80 (expensive). 500 open positions. -$82k realized but +$85k unrealized. | No — cautionary example of buying too high |
| `Infatuated-Pigsty` (`0x6e0d6450…`) | 1,930 updown-5m trades Feb 23 → Mar 4, median price 0.96, then stopped. Now on barriers. | **Evolved past it** — strategy had a shelf life |
| `Digital-Archaeologist` (`0x14e296e2…`) | Same as above: updown-5m scalp Feb 25 → Mar 27, stopped. Median trade size $5. | Same — shelf-life bot |
| `Testy-Connection` (`0x726fd4fd…`) | Active trader, median price 0.40, human-shaped. | No — not a bot |

## What Respectful-Clan is actually doing

**Their open-position book:**
| Vertical | # positions | Current value | Unrealized |
|---|---|---|---|
| Barriers (reach/dip-to) | 43 | **$1,111,248** | +$237,157 |
| Ladder above/below | 106 | $464,802 | +$15,807 |
| Ladder ranges | 130 | $40,126 | −$17,726 |
| Other | 25 | $35,794 | −$725 |

**Recent trades (all within ~20 min window on 2026-04-18):**
- BUY **No** @ 0.913 "Will BTC reach $80,000 April 13-19?"
- BUY **No** @ 0.963 "Will BTC reach $90,000 in April?"
- BUY **No** @ 0.990 "Will BTC reach $80,000 on April 18?"
- BUY **No** @ 0.962 "Will BTC reach $90,000 in April?"
- BUY **No** @ 0.710 "Will BTC reach $78,000 on April 18?"

**The strategy in plain English:** sell "it will happen" to people who want to pay ~$0.05 for a lottery ticket, by buying the NO side at 0.90-0.99. BTC is currently nowhere near $90k so "reach $90k in April" is mechanically unlikely; `Respectful-Clan` buys the NO at 0.96 and redeems at $1.00 on expiry. Tiny per-trade edge, massive scale (1997 BUYs in 38 hours), 304 concurrent positions diversifying idiosyncratic risk.

There's also a directional bet layer (the $321k position in "BTC reach $80k in April" YES at avg 0.35 is a different shape — that's conviction on the spot rising, not tail-insurance).

## Why this maps onto opportunities we've already identified

`docs/OPPORTUNITY_HOURLY_LADDER_MM.md` (our own analysis) proposes MM-ing the middle of balanced-probability markets. What `Respectful-Clan` is doing is the *tail* version of that: not "quote the middle", but "lift the 0.95-0.99 asks" when the underlying says the position is nearly certain.

This is:
- **Simpler than MM** — no quoting, just lifting mispriced offers.
- **Already-proven profitable** — we just found a wallet doing exactly this with +$99k realized in two days.
- **Scale-tunable** — run the same rule at $10k instead of $1.65M and you get ~0.6% of the P&L, i.e. ~$600 realized / 2 days. Still interesting at low operating cost.

## Concrete next investigation

1. **Reverse-engineer the entry rule.** Join `Respectful-Clan`'s trade timestamps against `probe/market_snapshots` for the same `market_id` where we have overlapping data. Measure for each of their buys: (implied_prob, spot_distance_from_strike, time_to_expiry, best_ask). Fit a simple decision boundary — when do they pull the trigger vs. pass?

2. **Backtest on the 40 April-17 barriers we already have snapshot data for.** Simulate: "every 60s, if any probe-tracked barrier has best_ask ≥ 0.95 AND spot is ≥ 15% away from strike AND ≥30min to expiry, take $100 at best_ask." Report: number of fills, gross P&L, redemption P&L, per-day rate. This is a day or two of work using `probe/probe.db` alone.

3. **Price-vs-fair check at the trade-record level.** For every `Respectful-Clan` BUY in `top_wallet_history.jsonl`, compute implied prob from our best-bid/best-ask snapshot at that timestamp. How much edge did they actually capture? (Gives us a target to beat.)

4. **Watch-list the wallet.** Add `0x6e1d5040d0ac73709b0621f620d2a60b80d2d0fa` to the probe — pull their trades every 5 min via `/trades?user=` and log any new barrier they touch. Costs one HTTP call every 5 min; gives us real-time strategy shadowing.

## Caveats, briefly

- Per-position realized P&L from `/positions` only reflects positions that haven't aged out of the endpoint's window. Lifetime P&L may be bigger or smaller.
- The 2-second inter-trade gap includes batched submissions; their actual decision cadence may be slower with pre-built order bundles.
- `Respectful-Clan`'s $321k YES position on "BTC reach $80k" is a directional bet, not tail-insurance. If you mechanically copy the 0.90-0.98 rule, you don't get this — but you also don't get the $116k unrealized on it. The tail strategy is smaller and duller; the directional bet is the juice.
- Barrier and ladder markets have UMA resolution lag (see `docs/FINDINGS.md` on resolution source). Redemption P&L realizes only after UMA settles, usually 6-24h post-expiry.
