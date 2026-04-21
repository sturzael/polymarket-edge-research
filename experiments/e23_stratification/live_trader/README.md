# live_trader — FLB scanner + live-trade logging

Lightweight Polymarket FLB scanner, notification pusher, and manual-trade logger for the e23 deployment plan.

---

## Where this fits in the research

This is the deployment arm of a multi-experiment research programme.

```
e16  → measured +25.8pp FLB at T-7d on Polymarket sports (z=7.6, n=120/2025)
e18–e22 → cross-venue: Betfair ±6pp, Azuro +0.4pp. Polymarket × T-7d is the outlier.
e23  → stratified the finding across sport, time, volume, lifespan, sub-category, execution.
       SYNTHESIS.md: deploy-ready, MLB/NBA/NFL/NHL × game_outcome × T-7d × 0.55–0.60 × ≤14d × ≥$5k.
e23/live_trader  ← you are here. Scanner + notification + manual-fill logger.
```

Key synthesis docs:
- [../../SYNTHESIS_flb_cross_venue.md](../../SYNTHESIS_flb_cross_venue.md) — cross-venue meta-finding
- [../SYNTHESIS.md](../SYNTHESIS.md) — e23 stratification + decision-ready deployment plan
- [../../e16_calibration_study/FINDINGS.md](../../e16_calibration_study/FINDINGS.md) — original measurement
- [../../e16_calibration_study/data/anchor_curve/anchor_curve_summary.json](../../e16_calibration_study/data/anchor_curve/anchor_curve_summary.json) — 5-anchor curve

---

## Current state (2026-04-21)

- **e16 / e18-e22 / e23 Agents A-F:** complete.
- **Synthesis:** written. Recommendation is small live test, gated by V2 cutover + observe window.
- **Scanner:** built, smoke-tested, **patched 2026-04-21 for `gameStartTime` bug** (old version used `endDate` which is offset by ~7d for MLB settlement delay — would have false-positived every post-game MLB market).
- **Wallet:** user has $56.22 USDC on Polymarket native wallet (Magic.link). Ready to trade.
- **First real trade:** placing (or placed) $5 NO on Arsenal win in [ucl-atm1-ars-2026-04-29](https://polymarket.com/event/ucl-atm1-ars-2026-04-29). Research-adjacent (soccer 3-way, not MLB/NBA/NFL/NHL strict) because no strict-research-match currently exists.
- **V2 cutover:** ~2026-04-22 (imminent as of this writing). Do NOT place additional trades through cutover + 7-10 days post.

## What to do next (in order)

1. **Log the Atletico/Arsenal fill** in `data/trades.jsonl` if you placed it. Quoted price, fill price, size, tx hash if visible.
2. **Start scanner in observe mode** (see Running below). It logs silently and pushes ntfy notifications on qualifying flags.
3. **Do nothing through the V2 cutover.** Scanner keeps logging. Don't place trades.
4. **Wait for ~20 qualifying flags** to accumulate post-V2. These are scouting data, not trade signals.
5. **Review post-V2 flag structure.** Does the scanner still produce sensible-looking favorites at T-7d? Are prices in the 0.55-0.60 band showing up? If yes → flip `"phase": "live"`.
6. **Live UX phase:** first 5-10 trades at $5-10 to validate fills. Expect ~$50 total at risk.
7. **Slippage calibration phase:** next 10-15 trades at $50-100 to test Agent F's slippage model.
8. **Decision point:** ~30 trades in, compare realized yes_rate (target ≥0.72) and realized slippage (target ≤3pp per $500) to plan. Deploy to $5k-$15k capital or kill.

## Sports-calendar caveat (April 2026)

The scanner will be quiet the first week. Current reality:
- **MLB** is early in the regular season. Game markets list ~14 days out but the T-7d instant now often coincides with already-played games (7d settlement delay on endDate). Flag rate should rise as the season matures.
- **NBA / NHL** are in playoffs. Series games are listed ~1-3 days ahead, never 7+.
- **NFL** is offseason.
- Expect 0-2 flags/day in the first week, rising to 2-6/day once MLB listings get deeper.

---

## Wallet setup (completed 2026-04-20)

- Polymarket native wallet (email login / Magic.link) — **done**
- $56.22 USDC available to trade — **done**
- No MetaMask / MATIC / USDC bridging required — native wallet abstracts gas
- Mobile (polymarket.com PWA) and desktop both work

## ntfy setup (mobile push)

1. Pick an unguessable topic name (public pub/sub). Example: `sturz-flb-7k2m9x`. **Don't reuse it anywhere else.**
2. Edit [config.json](config.json) → `"ntfy_topic": "<your-topic>"`.
3. Install ntfy on your phone: [iOS](https://apps.apple.com/app/ntfy/id1625396347) or [Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy).
4. In app: Add subscription → your topic. Leave server default (`ntfy.sh`).
5. Test: `curl -H "Title: test" -H "Click: https://polymarket.com" -d "it works" ntfy.sh/<your-topic>`. Phone should buzz within 5s.

## Running the scanner

**Recommended (persistent, survives Claude session end):**

```bash
tmux new -s flb -d "caffeinate -i uv run python experiments/e23_stratification/live_trader/scanner.py 2>&1 | tee -a experiments/e23_stratification/live_trader/data/scanner.log"
```

Explanation:
- `tmux new -s flb -d` — detached tmux session named `flb`
- `caffeinate -i` — keeps Mac from idle-sleeping while scanner runs
- `tee -a scanner.log` — mirrors stdout to a file you can tail later

Reattach: `tmux attach -t flb`
Detach (from inside tmux): `Ctrl+B` then `D`
Kill: `tmux kill-session -t flb`

**Foreground (for debugging):**

```bash
uv run python experiments/e23_stratification/live_trader/scanner.py
```

## Phase control

[config.json](config.json) has `"phase": "observe"` or `"live"`. Read fresh on every poll — edit the file any time, no restart needed.

- **observe:** all filters run, flag pushed to ntfy with `[OBSERVE]` prefix and default priority. No trades. This is the default and correct mode through V2 cutover + 20 post-V2 flags.
- **live:** flags push with `[LIVE]` prefix and high priority. Your signal to tap through and place a manual trade at $5-10 (UX phase) or $50-100 (slippage phase).

Every flag in `data/flagged_markets.jsonl` records the phase at flag-time — retrospective analysis can segment observe vs live cleanly.

## Filter criteria (deploy-plan aligned)

Hard-coded in `config.json`, edit with caution. Current values:
- Sports: **MLB, NBA, NFL, NHL** only (sports_allowlist)
- Sub-category: **game_outcome** only (no props, futures, totals, spreads — Agent E gate)
- Market duration: **≤14d** (Agent D: 91% of signal in this tier)
- Window volume: **≥$5k** in ±12h around T-7d (Agent C: scales with volume)
- Price bucket: **[0.55, 0.60)** (Agent F operating cell)
- Anchor: **T-7d** (event start time, NOT endDate — fix applied 2026-04-21)
- Window: **±12h**

## Flag response flow (when a notification fires)

1. Read notification: `[OBSERVE|LIVE] MLB · 0.578 · T-6.9d`
2. Tap notification → opens Polymarket market URL
3. Log in (email session)
4. **Observe phase:** note the live price vs flag price. Do nothing else.
5. **Live phase:** place a manual trade.
   - **Buy YES** on the favorite side (the side currently priced 0.55-0.60)
   - Amount: $5-10 for first 10 trades, scale to $50-100 after UX validates
   - Market order or limit at quoted price (limit cleaner for slippage measurement)
   - Never >$100 until 10+ fills show clean realized slippage
6. Record the fill — see below.

## Recording fills — `data/trades.jsonl`

After any trade (research-adjacent or research-strict), append a line:

```json
{"flagged_at": "2026-04-21T...", "placed_at": "2026-04-21T...", "condition_id": "0x…", "slug": "ucl-atm1-ars-2026-04-29-ars", "flag_price": 0.61, "fill_price": 0.62, "size_shares": 8.065, "size_usd": 5.00, "order_type": "market", "tx_hash": "0x…", "phase": "research_adjacent", "notes": "first real trade"}
```

Minimum to capture: `flag_price`, `fill_price`, `size_usd`, `placed_at`, `phase`.

Realized slippage per trade = `fill_price − flag_price` (pp). This is the data Agent F's slippage model needs empirical validation.

## Monitoring flags + resolutions

```bash
uv run python experiments/e23_stratification/live_trader/status.py
uv run python experiments/e23_stratification/live_trader/status.py --since 7d
uv run python experiments/e23_stratification/live_trader/status.py --phase observe
uv run python experiments/e23_stratification/live_trader/status.py --resolve
```

`--resolve` fetches current/final state from gamma: shows whether open, current YES price, or resolved outcome.

## Kill switches

Part of the deployment plan (not automated). Halt live trading if:
- Realized yes_rate < 0.72 over rolling 30-bet window
- Realized slippage > 3pp per $500 order
- V2 cutover causes obvious structural shift
- Max deployed capital: $15k until 30+ live trades confirm
- Max ever: $25k (Agent F capacity ceiling)

## Troubleshooting

- **Scanner logs `candidates_in_bucket=0` every poll for a day.** Normal during low-listing periods (e.g. NBA playoffs, early MLB). Use `status.py --since 7d` to see what was flagged historically. Zero over several days: check `config.json` wasn't edited wrong.
- **Notification never arrives.** Test: `curl -d "test" ntfy.sh/<topic>`. If that works but scanner doesn't push: check `config.json` `ntfy_topic` matches your subscription.
- **Flag fires but Polymarket URL 404s.** Event may have a different URL prefix. Fall back: search the slug on polymarket.com. Report so URL construction can be fixed.
- **Multiple flags for the same market in one day.** Expected if price exits and re-enters the 0.55-0.60 bucket. Each re-entry is a fresh flag.
- **MLB markets flagged at T-7d but the game has already been played.** Should no longer happen after 2026-04-21 fix — scanner now uses `gameStartTime`. If you see this, tell me.

## Files

- `scanner.py` — polling loop + filters + ntfy push (uses gameStartTime, 2026-04-21 fix applied)
- `status.py` — flag history viewer (stdlib `inspect` conflict avoided by rename)
- `config.json` — live-editable phase + thresholds + ntfy topic
- `data/flagged_markets.jsonl` — append-only flag log
- `data/seen_markets.json` — dedup state
- `data/trades.jsonl` — manual fill records (you maintain this)
- `data/scanner.log` — tee'd stdout from the running scanner

## Known open items

1. **V2 cutover handling** — scanner will keep running through V2. Worth re-running a smoke test post-V2 to verify API contract unchanged. ~2026-04-22.
2. **Cloud VM migration** — if you want the scanner truly 24/7 (survives reboots, Mac-off-the-shelf), $5/mo Hetzner or similar. Decision can wait until observe mode proves value.
3. **Auto-placement** — scaffold planned for after 10+ clean manual fills. Would use `py-clob-client` with an exported Magic.link private key. Deliberately not built yet.
