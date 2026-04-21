"""
Step 4+5: Capacity + planning-number estimates.
Combines asset universe (24h vol), spread snapshots (mean bps, top-of-book size),
and wallet concentration to produce a top-5 candidate table with:
- naive gross bps/fill after 1.3bp maker fee
- capacity: 0.5% of 24h ntl / 5 safety = effective quote size per side
- turnover: assume top-of-book refresh every 10s on active assets (360 round-trips/hr)
- raw daily + annual projection
- /5 discipline applied for planning number
Compares to e26 BTC-only baseline ($15-50/mo at $5-10k).
"""
import json
from datetime import datetime, timezone

UNIVERSE = "/Users/elliotsturzaker/dev/event-impact-mvp/experiments/e27_hl_synthetics_recon/data/asset_universe.json"
SPREADS = "/Users/elliotsturzaker/dev/event-impact-mvp/experiments/e27_hl_synthetics_recon/data/spread_snapshots.json"
PROFILES = "/Users/elliotsturzaker/dev/event-impact-mvp/experiments/e27_hl_synthetics_recon/data/wallet_profiles.json"
OUT = "/Users/elliotsturzaker/dev/event-impact-mvp/experiments/e27_hl_synthetics_recon/data/capacity_estimates.json"

MAKER_FEE_BPS = 1.3  # HL maker fee basepoint (post VIP/staking on active retail tier)
QUOTE_PER_SIDE_USD = 2500  # e26 baseline: $2.5k per side = $5k gross book
SAFETY_DIVISOR = 5.0


def main():
    uni = json.load(open(UNIVERSE))
    spreads = json.load(open(SPREADS))
    profiles = json.load(open(PROFILES))

    # Map coin -> 24h vol
    vol_lookup = {}
    for p in uni["perps_by_volume"]:
        vol_lookup[p["name"]] = p["day_ntl_vlm"]

    # Map coin -> wallet concentration
    wallet_counts = {}
    for row in profiles["asset_aggregation"]:
        wallet_counts[row["coin"]] = {
            "n_wallets": row["n_wallets"],
            "fills": row["fill_count_across_wallets"],
            "ntl": row["ntl_usd_across_wallets"],
        }

    table = []
    for s in spreads["summary"]:
        coin = s["coin"]
        vol24 = vol_lookup.get(coin, None)
        wc = wallet_counts.get(coin, {"n_wallets": 0, "fills": 0, "ntl": 0})

        mean_spread = s["mean_spread_bps"] or 0
        # Gross edge per round-trip = spread (capture both sides) - 2 * maker_fee
        # But realistic: as a solo MM we capture the spread ~ 30-50% of the time
        # due to adverse selection. Model: effective captured = 0.5 * spread.
        # Per-fill net = 0.5*spread - maker_fee (maker side only, one-legged accounting)
        raw_net_bps_per_fill = mean_spread * 0.5 - MAKER_FEE_BPS

        # Capacity: 0.5% of 24h vol per side / SAFETY
        cap_per_side = (vol24 or 0) * 0.005 / SAFETY_DIVISOR if vol24 else 0
        # But we're constrained to $2500 per side (our actual bankroll quote)
        effective_quote = min(QUOTE_PER_SIDE_USD, cap_per_side)

        # Turnover: assume 6 round-trip fills/hour = 144/day for mid-tier
        # (10min quote/turn time, conservative vs top-of-book refresh rate seen in snapshots)
        # For majors with very fast TOB change, pro MMs dominate; we assume retail fill rate
        # is more like 2-8 fills/hr (conservative).
        tob_chg_per_snap = s["tob_changes_across_snapshots"] / max(s["n_snapshots"]-1, 1)
        # tob_chg_per_snap=1.0 means every 45s TOB changes. Our fill rate << TOB refresh rate.
        assumed_fills_per_day = 50  # conservative: 2/hour averaged across 24h

        raw_daily_usd = effective_quote * (raw_net_bps_per_fill / 10000) * assumed_fills_per_day
        adj_daily_usd = raw_daily_usd / SAFETY_DIVISOR
        raw_monthly_usd = raw_daily_usd * 30
        adj_monthly_usd = adj_daily_usd * 30

        table.append({
            "coin": coin,
            "dex": s["dex"],
            "day_ntl_vol_usd": vol24,
            "mean_spread_bps": mean_spread,
            "median_depth_50bps_usd": round((s["mean_depth_50bps_bid_usd"] + s["mean_depth_50bps_ask_usd"]) / 2, 2) if s["mean_depth_50bps_bid_usd"] else None,
            "top_wallet_n": wc["n_wallets"],
            "top_wallet_fills_30d": wc["fills"],
            "capacity_0p5pct_per_side_usd": round(cap_per_side, 2),
            "effective_quote_per_side_usd": round(effective_quote, 2),
            "raw_net_bps_per_fill_assuming_50pct_capture": round(raw_net_bps_per_fill, 2),
            "assumed_fills_per_day": assumed_fills_per_day,
            "raw_daily_usd": round(raw_daily_usd, 2),
            "raw_monthly_usd": round(raw_monthly_usd, 2),
            "div5_monthly_usd_planning": round(adj_monthly_usd, 2),
            "comment": (
                "structural_negative" if raw_net_bps_per_fill <= 0 else
                "marginal" if raw_net_bps_per_fill < 1 else
                "borderline" if raw_net_bps_per_fill < 3 else
                "potentially_viable"
            ),
        })

    # Rank by raw_monthly desc
    table.sort(key=lambda r: -r["raw_monthly_usd"])

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "assumptions": {
            "maker_fee_bps": MAKER_FEE_BPS,
            "quote_per_side_usd": QUOTE_PER_SIDE_USD,
            "safety_divisor": SAFETY_DIVISOR,
            "capture_rate_of_spread": 0.5,
            "assumed_fills_per_day": 50,
            "comment": "Capture-rate 50% of spread is generous for solo retail; true rate vs HLP/pro MMs likely 20-40%. Fills/day=50 is a rough midpoint; TOB snapshot data show majors and xyz:* are near 100% TOB-refresh every 45s, implying a solo retail maker is rarely at the top — so 50 fills/day is probably optimistic.",
        },
        "baseline_e26_btc_only_monthly": "$15-50/mo at $5-10k (for comparison)",
        "top_candidates_ranked_by_raw_monthly": table,
    }
    with open(OUT, "w") as f:
        json.dump(out, f, indent=2)

    print(f"\nCapacity + planning-number table (assuming 50% spread capture, 50 fills/day @ $2.5k/side):")
    print(f"{'coin':<18} {'vol24':>14} {'spread':>8} {'net/fill':>10} {'raw_$/mo':>10} {'/5 $/mo':>10} {'topwallets':>10}  comment")
    for r in table[:20]:
        vol = f"${r['day_ntl_vol_usd']:,.0f}" if r['day_ntl_vol_usd'] else "n/a"
        print(f"  {r['coin']:<18} {vol:>14}  {r['mean_spread_bps']:>6.2f}  {r['raw_net_bps_per_fill_assuming_50pct_capture']:>8.2f}bp  ${r['raw_monthly_usd']:>8,.0f}  ${r['div5_monthly_usd_planning']:>8,.0f}  w={r['top_wallet_n']:>2}  {r['comment']}")
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
