# e2 — Deribit IV snapshot

**Question:** Get an independent volatility benchmark against which Polymarket crypto prices can be validated. If Poly's implied probability for "BTC up in next 5m" is systematically offset from what Deribit's IV-implied probability says it should be, *that* is the headline mispricing finding.

**Method:** Hit the public Deribit v2 endpoint `get_book_summary_by_currency?currency=BTC&kind=option` (and ETH). Snapshot to disk. Do again in ~24h for realized-vs-implied over the probe window.

## Snapshot 1

- **Time:** 2026-04-18 14:40 UTC (unix 1776480011)
- **BTC:** 930 option contracts, files `btc_book_summary_1776480011.json`
- **ETH:** 786 option contracts, files `eth_book_summary_1776480011.json`

Top expiries by contract count:
- BTC: 26JUN26 (114), 25SEP26 (114), 25DEC26 (108), 24APR26 (96, nearest), 29MAY26 (92), 26MAR27 (88)
- ETH: 25SEP26 (116), 26JUN26 (114), 25DEC26 (86), 24APR26 (76, nearest), 26MAR27 (70), 29MAY26 (70)

Each JSON entry has: `mark_iv`, `bid_iv`, `ask_iv`, `underlying_price`, `mark_price`, `instrument_name`, `mid_price`, `open_interest`, `volume`.

## How to use

For any Polymarket crypto up/down contract resolving at time T:
1. Pull the nearest-expiry Deribit option chain at T - X.
2. Fit the ATM volatility smile; compute σ at the underlying's spot.
3. Model-implied P(up over Δt) = `1 − Φ((ln(K/S) − σ²Δt/2) / σ√Δt)`.
   - For an up/down 5m market, K = S (strike is current spot, resolves "up" if S_T > S_0), so it reduces to `1 − Φ(−σ√Δt/2)` ≈ 0.5 + small drift, typical ~0.51–0.53 depending on vol.
4. Compare to Poly's lastTradePrice or bid/ask midpoint.

**Key insight:** For 5-minute at-the-money up/down, Deribit IV predicts a probability close to 0.5 with a slight positive drift from the vol-of-vol. Any Poly 5m market trading materially away from 0.5 at T-60s without corresponding spot movement is either reflecting flow information (order imbalance), operator information (insider), or is mispriced. This is the benchmark the v2 calibration study should use.

## Snapshot 2 (pending)

Planned ~24h after snapshot 1. Compares implied vs realized vol across the probe window.

Write snapshot 2 via:
```
cd ~/dev/event-impact-mvp
uv run python experiments/e2_deribit_iv/snapshot.py    # see below
```

## Status

Snapshot 1 captured. Snapshot 2 pending. Analysis not yet run.
