# Agent D — HL MM technical stack & risk framework

**Returned:** 2026-04-21

## Recommended Stack

- **Language/SDK:** Python 3.11 + `hyperliquid-python-sdk` (official, MIT, active — v0.23.0 released 2026-04-14). Reuses existing infra patterns (SQLite, ntfy). Ships `examples/basic_adding.py` — working MM skeleton to fork.
- **VPS:** Vultr High Frequency Tokyo ($12/mo, 2 vCPU / 2GB). Tokyo is mandatory — HL officially recommends it for lowest latency to validators.
- **Data:** WebSocket `l2Book` subscription (sequence-validated, exponential-backoff reconnect). Public REST only for reconciliation.
- **Monitoring:** Grafana Cloud free tier (10k metrics) + Sentry free + existing ntfy for kill alerts.
- **Avoid:** Rust SDK (faster but 4× build time for marginal gain at your scale); Hummingbot's HL perp connector (works but has recurring post-only-after-upgrade bugs #6730/#6800, adds abstraction tax).

## Latency Realism (RTT to HL, conservative)

| Path | RTT | Viable for passive MM? |
|---|---|---|
| NZ (Auckland) direct to HL API | ~180–230ms | **No** — adverse selection will destroy you |
| US-East (Ashburn) VPS | ~160–190ms | Marginal; worse than Asia |
| **Tokyo VPS → HL** | **~5–20ms** | **Yes** — this is the only realistic option |
| Co-lo peered RPC (Dwellir / HyperRPC Tokyo) | sub-ms to validator | HFT-class, not needed for wide-quote MM |

Sub-100ms from NZ is **implausible**. Auckland is your cockpit, not your server.

## Minimum Viable Risk Controls

1. **Hard position cap:** notional + % of equity (e.g. $5k / 20%)
2. **Daily drawdown kill:** halt + cancel-all at −2% equity
3. **Adverse-selection detector:** if one-sided fill ratio >75% over 5min, widen spreads 2× or pause
4. **Quote sanity:** reject any quote >0.3% from mark; halt if mid deviates from reference CEX >0.5%
5. **Remote kill:** ntfy webhook → VPS systemd stop; phone-accessible dashboard
6. **Heartbeat watchdog:** if no L2 update >2s, cancel all and reconnect
7. **Nonce discipline:** atomic counter (HL stores top-100 per address; collision = silent drop)
8. **Post-upgrade handler:** catch "only post-only allowed" errors, retry with ALO for ~3min

## Testnet Path

1. Deposit ≥$5 USDC on Arbitrum mainnet to HL bridge (activates address)
2. Claim 1000 mock USDC at `app.hyperliquid-testnet.xyz/drip` (one-shot per address)
3. Point SDK at `api.hyperliquid-testnet.xyz`, generate API wallet via `/API` page
4. Run `basic_adding.py` unchanged → verify fills → layer strategy

## Monthly Opex

| Item | Low | High |
|---|---|---|
| Tokyo VPS | $12 | $40 |
| Grafana Cloud / Sentry | $0 | $0 |
| Dedicated RPC (optional) | $0 | $50 |
| **Total** | **$12** | **$90** |

Public HL API is free and sufficient; paid RPC only matters if you hit 100 req/min/IP.

## Top 3 Reference Repos

1. **`hyperliquid-dex/hyperliquid-python-sdk`** `examples/basic_adding.py` — canonical HL MM loop; start here, don't reinvent signing.
2. **`fedecaccia/avellaneda-stoikov`** — reference A-S implementation; port the reservation-price + spread math, ignore its exchange adapter.
3. **`chainstacklabs/hyperliquid-trading-bot`** — educational Python bot showing auth/WS/order flow patterns on HL specifically.

## Verdict

**Build in Python on a Tokyo VPS, or don't build. Two weeks is realistic if you fork `basic_adding.py` and layer risk controls + A-S spread logic on top.**

## Sources

- [hyperliquid-dex/hyperliquid-python-sdk](https://github.com/hyperliquid-dex/hyperliquid-python-sdk)
- [basic_adding.py example](https://github.com/hyperliquid-dex/hyperliquid-python-sdk/blob/master/examples/basic_adding.py)
- [HL Rate Limits docs](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits)
- [HL Optimizing Latency docs](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/optimizing-latency)
- [HL Testnet Faucet](https://hyperliquid.gitbook.io/hyperliquid-docs/onboarding/testnet-faucet)
- [HL Order Types](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/order-types)
- [HL Nonces and API Wallets](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/nonces-and-api-wallets)
- [HL Fees](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees)
- [HL WebSocket Subscriptions](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket/subscriptions)
- [Hummingbot post-only bug #6730](https://github.com/hummingbot/hummingbot/issues/6730)
- [Hummingbot HL connector](https://hummingbot.org/exchanges/hyperliquid/)
- [fedecaccia/avellaneda-stoikov](https://github.com/fedecaccia/avellaneda-stoikov)
- [chainstacklabs/hyperliquid-trading-bot](https://github.com/chainstacklabs/hyperliquid-trading-bot)
- [Dwellir HL orderbook service](https://www.dwellir.com/hyperliquid-orderbook)
- [WonderNetwork Auckland/Tokyo pings](https://wondernetwork.com/pings/Auckland/Tokyo)
