"""Compute favorite-longshot calibration for Drift -BET prediction markets.

Methodology (matches e16/05_fixed_time_calibration.py):
1. For each market, identify resolution time = timestamp of LAST traded candle
   (last candle with quoteVolume > 0). After that point, Drift zero-fills
   oracleClose/fillClose indefinitely.
2. Identify outcome from the final-traded-block fillClose:
     mean of fillClose over the last 5 traded candles (or all if fewer)
     >= 0.85 → YES, <= 0.15 → NO, else UNRESOLVED (cannot classify).
3. Compute T-7d price via VWAP of fillClose weighted by quoteVolume within
   +/-12h of (resolution_ts - 7 days). Fall back to oracleClose mean if no
   fills in window.
4. Bucket in 5pp bands, compute yes_rate, deviation, z-score.

Outputs: data/calibration_table.json, data/market_level.json (per-market rows)
"""
from __future__ import annotations

import json
import math
from pathlib import Path

HERE = Path(__file__).parent.parent
DATA = HERE / "data"
CDIR = DATA / "candles"

BUCKETS = [(i / 100.0, (i + 5) / 100.0) for i in range(0, 100, 5)]


def bucket_label(p: float) -> str:
    for lo, hi in BUCKETS:
        if lo <= p < hi:
            return f"{lo:.2f}-{hi:.2f}"
    return "0.95-1.00"


def bucket_mid(p: float) -> float:
    for lo, hi in BUCKETS:
        if lo <= p < hi:
            return lo + 0.025
    return 0.975


def classify_category(symbol: str) -> str:
    s = symbol.upper()
    if any(x in s for x in ("F1", "SUPERBOWL", "NBAFINALS", "FIGHT")):
        return "sports"
    if any(x in s for x in ("TRUMP", "KAMALA", "REPUBLICAN", "DEMOCRATS", "MICHIGAN")):
        return "politics"
    if "FED" in s:
        return "economics"
    if "WLF" in s or "BREAKPOINT" in s:
        return "crypto_events"
    return "other"


def last_traded_index(recs: list[dict]) -> int | None:
    for i in range(len(recs) - 1, -1, -1):
        qv = recs[i].get("quoteVolume") or 0
        if float(qv) > 0:
            return i
    return None


def resolution_info(recs: list[dict]) -> dict:
    idx = last_traded_index(recs)
    if idx is None:
        return {"idx": None, "ts": None, "outcome": None, "final_fill": None}
    ts = recs[idx]["ts"]
    # Use fillClose of the last 5 traded candles (iterating backwards from idx)
    tail_fills = []
    i = idx
    while i >= 0 and len(tail_fills) < 5:
        r = recs[i]
        qv = float(r.get("quoteVolume") or 0)
        fc = r.get("fillClose")
        if qv > 0 and fc is not None:
            tail_fills.append(float(fc))
        i -= 1
    if not tail_fills:
        return {"idx": idx, "ts": ts, "outcome": None, "final_fill": None}
    final = sum(tail_fills) / len(tail_fills)
    if final >= 0.85:
        outcome = "YES"
    elif final <= 0.15:
        outcome = "NO"
    else:
        outcome = None  # ambiguous final price
    return {"idx": idx, "ts": ts, "outcome": outcome,
            "final_fill": round(final, 5),
            "tail_fills": [round(x, 5) for x in tail_fills]}


def snapshot_vwap(recs: list[dict], target_ts: int, window_hours: int = 12) -> dict | None:
    lo = target_ts - window_hours * 3600
    hi = target_ts + window_hours * 3600
    in_window = [r for r in recs if lo <= r["ts"] <= hi]
    if not in_window:
        return None
    weighted_price = 0.0
    weighted_vol = 0.0
    oracle_prices = []
    fill_ct = 0
    for r in in_window:
        oc = r.get("oracleClose")
        if oc is not None and float(oc) > 0:
            oracle_prices.append(float(oc))
        qv = float(r.get("quoteVolume", 0) or 0)
        fc = r.get("fillClose")
        if qv > 0 and fc is not None and 0 < float(fc) < 1:
            weighted_price += float(fc) * qv
            weighted_vol += qv
            fill_ct += 1
    if weighted_vol > 0:
        price = weighted_price / weighted_vol
        source = "fill_vwap"
    elif oracle_prices:
        price = sum(oracle_prices) / len(oracle_prices)
        source = "oracle_mean"
    else:
        return None
    return {
        "price": round(price, 5),
        "source": source,
        "n_candles_window": len(in_window),
        "n_with_fills": fill_ct,
        "total_quote_volume_window": round(weighted_vol, 2),
    }


def main() -> None:
    all_markets = json.load(open(DATA / "all_markets.json"))["markets"]
    bets = [m for m in all_markets if m["symbol"].endswith("-BET")]

    # Manual overrides for public-knowledge outcomes where the fillClose is ambiguous.
    # These are only used if automatic classification returns None.
    # Source: public event outcomes. See VERDICT.md.
    manual_outcomes: dict[str, str] = {
        "DEMOCRATS-WIN-MICHIGAN-BET": "NO",    # Trump won Michigan 2024
        "BREAKPOINT-IGGYERIC-BET": "NO",       # per thin settlement near 0.167
        "WARWICK-FIGHT-WIN-BET": "YES",        # Warwick won vs Paul (2024-10-12)
    }

    records = []
    for m in bets:
        sym = m["symbol"]
        recs = json.load(open(CDIR / f"{sym}.json"))
        if not recs:
            continue

        res = resolution_info(recs)
        outcome = res["outcome"]
        if outcome is None and sym in manual_outcomes:
            outcome = manual_outcomes[sym]
            outcome_source = "manual_override"
        else:
            outcome_source = "auto_fillclose_tail"

        resolution_ts = res["ts"]
        first_ts = recs[0]["ts"]
        last_ts = recs[-1]["ts"]
        total_qv = sum(float(r.get("quoteVolume", 0) or 0) for r in recs)

        anchors = {}
        if resolution_ts is None:
            resolution_ts = last_ts
        duration_days = (resolution_ts - first_ts) / 86400.0
        for label, offset_h in [("T_minus_7d", 7 * 24),
                                 ("T_minus_1d", 24),
                                 ("T_minus_3d", 72),
                                 ("T_minus_14d", 14 * 24)]:
            target_ts = resolution_ts - offset_h * 3600
            if target_ts < first_ts:
                anchors[label] = None
                continue
            snap = snapshot_vwap(recs, target_ts, window_hours=12)
            anchors[label] = snap

        mid_ts = (first_ts + resolution_ts) // 2
        anchors["midpoint"] = snapshot_vwap(recs, mid_ts, window_hours=12)

        records.append({
            "symbol": sym,
            "market_index": m["marketIndex"],
            "category": classify_category(sym),
            "outcome": outcome,
            "outcome_source": outcome_source,
            "final_fill": res.get("final_fill"),
            "first_ts": first_ts,
            "resolution_ts": resolution_ts,
            "last_candle_ts": last_ts,
            "duration_days": round(duration_days, 2),
            "total_quote_volume": round(total_qv, 2),
            "anchors": anchors,
        })

    # Report per-market
    print(f"{'symbol':<35} {'cat':<14} {'dur':>5}d {'qv':>11}  {'out':<3}  "
          f"{'T-7d':>7}  {'T-3d':>7}  {'T-1d':>7}  {'mid':>7}")
    for r in records:
        def fmt(anchor):
            if anchor is None:
                return "  --  "
            return f"{anchor['price']:.4f}"
        print(f"{r['symbol']:<35} {r['category']:<14} "
              f"{r['duration_days']:>5.1f} ${r['total_quote_volume']:>10,.0f}  "
              f"{str(r['outcome']):<3}  "
              f"{fmt(r['anchors']['T_minus_7d']):>7}  "
              f"{fmt(r['anchors']['T_minus_3d']):>7}  "
              f"{fmt(r['anchors']['T_minus_1d']):>7}  "
              f"{fmt(r['anchors']['midpoint']):>7}")

    json.dump(records, open(DATA / "market_level.json", "w"), indent=2)

    # Build calibration rows — primary T-7d anchor
    def build_rows(anchor_key: str) -> list[dict]:
        rows = []
        for r in records:
            if r["outcome"] not in ("YES", "NO"):
                continue
            snap = r["anchors"].get(anchor_key)
            if snap is None:
                continue
            rows.append({
                "symbol": r["symbol"],
                "category": r["category"],
                "outcome": r["outcome"],
                "yes": 1 if r["outcome"] == "YES" else 0,
                "price": snap["price"],
                "bucket": bucket_label(snap["price"]),
                "bucket_mid": bucket_mid(snap["price"]),
                "source": snap["source"],
                "duration_days": r["duration_days"],
            })
        return rows

    def aggregate(rows: list[dict]) -> list[dict]:
        b: dict[str, dict] = {}
        for r in rows:
            b.setdefault(r["bucket"], {"n": 0, "yes": 0, "mid": r["bucket_mid"],
                                       "symbols": []})
            b[r["bucket"]]["n"] += 1
            b[r["bucket"]]["yes"] += r["yes"]
            b[r["bucket"]]["symbols"].append(r["symbol"])
        out = []
        for bk, v in sorted(b.items()):
            yr = v["yes"] / v["n"]
            mid = v["mid"]
            dev = yr - mid
            se = math.sqrt(mid * (1 - mid) / v["n"])
            z = dev / se if se > 0 else float("nan")
            out.append({
                "bucket": bk, "n": v["n"], "mid": round(mid, 3),
                "yes_rate": round(yr, 4), "deviation": round(dev, 4),
                "z_score": round(z, 2),
                "symbols": v["symbols"],
            })
        return out

    output = {"n_markets_total": len(records)}
    for anchor in ["T_minus_7d", "T_minus_3d", "T_minus_1d", "midpoint"]:
        rows = build_rows(anchor)
        output[anchor] = {
            "n_rows": len(rows),
            "rows": rows,
            "buckets": aggregate(rows),
        }
        print(f"\n=== {anchor} anchor ({len(rows)} rows) ===")
        print(f"  {'bucket':<12} {'n':>3}  {'mid':>6}  {'yes_rate':>9}  {'dev':>7}  {'z':>5}  symbols")
        for a in output[anchor]["buckets"]:
            print(f"  {a['bucket']:<12} {a['n']:>3}  {a['mid']:>6.3f}  "
                  f"{a['yes_rate']:>9.3f}  {a['deviation']:>+7.3f}  "
                  f"{a['z_score']:>+5.2f}  {a['symbols']}")

    # Sports-only view for T-7d
    rows_sports = [r for r in build_rows("T_minus_7d") if r["category"] == "sports"]
    print(f"\n=== T-7d SPORTS ONLY ({len(rows_sports)} rows) ===")
    for a in aggregate(rows_sports):
        print(f"  {a['bucket']:<12} {a['n']:>3}  {a['mid']:>6.3f}  "
              f"{a['yes_rate']:>9.3f}  {a['deviation']:>+7.3f}  "
              f"{a['z_score']:>+5.2f}  {a['symbols']}")

    # Directional: correlation price vs yes across all resolved markets (all anchors pooled)
    all_pts = []
    for r in records:
        if r["outcome"] not in ("YES", "NO"):
            continue
        snap = r["anchors"].get("T_minus_7d") or r["anchors"].get("midpoint")
        if snap:
            all_pts.append((snap["price"], 1 if r["outcome"] == "YES" else 0))
    if len(all_pts) >= 2:
        n = len(all_pts)
        xs = [p[0] for p in all_pts]
        ys = [p[1] for p in all_pts]
        mx = sum(xs) / n
        my = sum(ys) / n
        num = sum((x - mx) * (y - my) for x, y in all_pts)
        dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
        dy = math.sqrt(sum((y - my) ** 2 for y in ys))
        corr = num / (dx * dy) if dx > 0 and dy > 0 else float("nan")
        print(f"\n  T-7d-ish price vs outcome correlation: {corr:+.4f} (n={n})")
        output["price_outcome_correlation"] = round(corr, 4)
        output["correlation_n"] = n

    json.dump(output, open(DATA / "calibration_table.json", "w"), indent=2)
    print(f"\nWrote {DATA / 'calibration_table.json'}")


if __name__ == "__main__":
    main()
