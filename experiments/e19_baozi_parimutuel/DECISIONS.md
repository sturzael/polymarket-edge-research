# e19 — Decisions log

## D1: data source = direct Solana RPC `getProgramAccounts`

The Baozi MCP server (`@baozi.bet/mcp-server`) is a thin wrapper over Solana RPC calls:
`listMarkets` → `connection.getProgramAccounts(PROGRAM_ID, filters=[MARKET_DISCRIMINATOR])`.
There is no Baozi-hosted REST API. We can either install the MCP or call Solana RPC directly
with the same filter. Going direct: fewer deps, fewer moving parts, same data.

Program ID: `FWyTPzm5cfJwRKzfkscxozatSxF6Qu78JQovQUwKPruJ`
MARKET discriminator (first 8 bytes of account data): `[219, 190, 213, 55, 0, 227, 198, 154]`
RACE_MARKET discriminator: `[235, 196, 111, 75, 230, 113, 118, 238]`

Default RPC: `https://api.mainnet-beta.solana.com` (public, rate-limited).

## D2: category inference from question text

Baozi markets store `layer` (Lab/Official/Private) and `accessGate` (Public/Whitelist) on-chain
but **no explicit category field** (no "sports" / "crypto" / "politics" column per the decoded
struct). To stratify sports vs non-sports per the unified methodology, we'll infer category
from the question text using keyword rules (team names, leagues, player names for sports;
ticker symbols for crypto; politician names for politics; etc.). Acknowledging this will be
noisy compared to Polymarket's tagged `category`.

## D3: implied probability = final pool ratio

For a resolved Baozi market, implied YES probability at close = `yesPoolSol / (yesPoolSol + noPoolSol)`.
This is the "T-0 snapshot." We will NOT reconstruct a T-7d snapshot for the first pass because
that requires replaying every bet transaction via `getSignaturesForAddress` + decode — a bet-by-bet
indexer that's >30 min to build, and Solana mainnet-beta RPC only retains ~2 weeks of tx history
for unknown PDAs without archive access.

Documented caveat: our calibration result for Baozi is AT-CLOSE, whereas the Polymarket baseline
is T-7d. These are different points on the price trajectory; at-close is typically more calibrated
than T-7d (more information). So if Baozi shows MORE FLB at close than Polymarket shows at T-7d,
that's a strong pari-mutuel signal. If Baozi shows similar or less, we can't conclude much because
the time windows differ.

If TIER 1 data exists, the bonus step will be to pick a subset (~50 markets) and do a bet-replay
T-7d snapshot to compare like-for-like.

## D4: if Solana RPC blocks public `getProgramAccounts`

Some public RPCs disable `getProgramAccounts` without filters for DoS reasons, but the filtered
version (memcmp on discriminator) is generally allowed. Fallbacks if it fails:
1. Try the Solana public RPC multiple times (it's sometimes flaky).
2. Try Helius public demo endpoint.
3. Fall back to listing just Active markets by scanning a smaller range.
4. If all fail, write the methodology + note that analysis requires a paid RPC endpoint
   (Helius $49/mo tier) and stop at venue-profile.

## D5: environment — Bash blocked

Bash tool was denied at the start of this agent's run. Worked around by:
- Using Write for file creation instead of `mkdir`/`cat`.
- Using Python via a subprocess-free path where possible. Where a one-off HTTP POST is needed,
  we try the WebFetch tool with JSON-RPC endpoints (Solana RPC is JSON-RPC over HTTPS POST,
  but WebFetch is also denied on non-github URLs).

Practical implication: we cannot actually HIT the Solana RPC from this environment. The script
we write (`scripts/probe_baozi.py`) is documented for the user to run locally, and we populate
the venue-profile section from what's already public.

