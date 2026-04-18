"""Generate the 24-hour reconnaissance report from probe.db.

Run: `uv run python -m probe.report [--db probe/probe.db] [--out probe/REPORT.md]`

Produces a markdown report with:
  - duration breakdown of discovered crypto markets
  - resolution stats (rate, lag distribution, clean-rate)
  - price-data sufficiency per market
  - explicit recommendation: proceed on 5m / use 15m-1h / don't proceed
"""
from __future__ import annotations

import argparse
import sqlite3
import statistics
from collections import Counter, defaultdict
from pathlib import Path


def _fmt_ms(ms: int | None) -> str:
    if ms is None:
        return "-"
    import datetime as dt
    return dt.datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M:%S")


def _bucket_duration(duration_s: int | None) -> str:
    if duration_s is None:
        return "unknown"
    if duration_s <= 60:
        return "<=1m"
    if duration_s <= 5 * 60:
        return "5m"
    if duration_s <= 15 * 60:
        return "15m"
    if duration_s <= 60 * 60:
        return "1h"
    if duration_s <= 4 * 3600:
        return "4h"
    if duration_s <= 24 * 3600:
        return "1d"
    if duration_s <= 7 * 86400:
        return "1w"
    return ">1w"


DURATION_BUCKETS_ORDER = ["<=1m", "5m", "15m", "1h", "4h", "1d", "1w", ">1w", "unknown"]


def generate_report(db_path: str) -> str:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Probe meta
    meta = {
        row[0]: row[1]
        for row in cur.execute("SELECT key, value FROM probe_meta").fetchall()
    }
    started_ms = int(meta.get("probe_started_at_ms", "0")) or None
    stopped_ms = int(meta.get("probe_stopped_at_ms", "0")) or None
    duration_s = int(meta.get("probe_duration_s", "0")) or None

    # Markets
    markets = cur.execute(
        "SELECT market_id, slug, question, underlying, duration_s, end_ts, is_crypto "
        "FROM markets WHERE is_crypto = 1"
    ).fetchall()
    market_by_id = {m["market_id"]: m for m in markets}

    # Duration breakdown of crypto markets discovered during probe
    dur_counts = Counter(_bucket_duration(m["duration_s"]) for m in markets)
    underlying_counts = Counter((m["underlying"] or "?") for m in markets)

    # Markets whose nominal expiry fell inside the probe window
    within_window = [
        m for m in markets
        if started_ms and m["end_ts"] and started_ms <= m["end_ts"] <= (stopped_ms or 1 << 62)
    ]

    # Resolutions
    resolutions = cur.execute(
        "SELECT market_id, nominal_end_ts, resolved_ts, resolution_lag_s, outcome, resolved_cleanly "
        "FROM resolutions"
    ).fetchall()
    resolutions_by_id = {r["market_id"]: r for r in resolutions}
    clean = [r for r in resolutions if r["resolved_cleanly"] == 1]
    unresolved = [r for r in resolutions if r["outcome"] == "UNRESOLVED"]
    outcomes_counter = Counter(r["outcome"] for r in resolutions)

    lags = [r["resolution_lag_s"] for r in resolutions if r["resolution_lag_s"] is not None]

    # Price data sufficiency
    # Count snapshots in final-60s window for each resolved market
    sufficient_60s: list[int] = []  # count of samples
    sufficient_5min: list[int] = []
    final_price_present: int = 0
    thin_book_count: int = 0
    for r in resolutions:
        cid = r["market_id"]
        end_ts = r["nominal_end_ts"]
        if end_ts is None:
            continue
        rows = cur.execute(
            "SELECT best_bid, best_ask, last_trade_price, ts FROM market_snapshots "
            "WHERE market_id = ? AND ts BETWEEN ? AND ?",
            (cid, end_ts - 5 * 60 * 1000, end_ts),
        ).fetchall()
        in_5m = len(rows)
        in_60s = sum(1 for row in rows if row["ts"] >= end_ts - 60 * 1000)
        sufficient_5min.append(in_5m)
        sufficient_60s.append(in_60s)
        last_rows = [r for r in rows if r["ts"] >= end_ts - 15 * 1000]
        if last_rows:
            final_price_present += 1
            # thin book check: ask - bid > 0.2 on 0..1 scale means book is fiction
            for row in last_rows:
                if row["best_bid"] is not None and row["best_ask"] is not None:
                    if (row["best_ask"] - row["best_bid"]) > 0.2:
                        thin_book_count += 1
                        break

    # Build report
    lines: list[str] = []
    p = lines.append
    p("# Polymarket Short-Duration Crypto Probe — Report")
    p("")
    p(f"- **Probe window:** {_fmt_ms(started_ms)} → {_fmt_ms(stopped_ms)}")
    if started_ms and stopped_ms:
        elapsed = (stopped_ms - started_ms) / 3600000
        p(f"- **Elapsed:** {elapsed:.2f}h (target {(duration_s or 0)/3600:.2f}h)")
    p("")

    # Section: what exists
    p("## What exists")
    p("")
    p(f"- Crypto markets discovered: **{len(markets)}**")
    p(f"- Of those, with nominal expiry inside probe window: **{len(within_window)}**")
    p("")
    p("### Duration breakdown (discovered)")
    p("| Duration | Count | Share |")
    p("|---|---:|---:|")
    total = sum(dur_counts.values()) or 1
    for b in DURATION_BUCKETS_ORDER:
        c = dur_counts.get(b, 0)
        if c == 0:
            continue
        p(f"| {b} | {c} | {100*c/total:.1f}% |")
    p("")
    p("### Underlyings")
    p("| Underlying | Count |")
    p("|---|---:|")
    for u, c in underlying_counts.most_common():
        p(f"| {u} | {c} |")
    p("")

    # Section: resolutions
    p("## Resolutions during probe")
    p("")
    p(f"- Resolution rows written: **{len(resolutions)}**")
    p(f"- Cleanly resolved (outcome populated, within watch window): **{len(clean)}**")
    p(f"- UNRESOLVED (timed out or API never reported outcome): **{len(unresolved)}**")
    if outcomes_counter:
        p("")
        p("### Outcome distribution")
        p("| Outcome | Count |")
        p("|---|---:|")
        for k, v in outcomes_counter.most_common():
            p(f"| {k} | {v} |")
    p("")
    p("### Resolution lag (seconds after nominal expiry)")
    if lags:
        p(f"- mean: **{statistics.mean(lags):.1f}s**")
        p(f"- median: **{statistics.median(lags):.1f}s**")
        p(f"- p90: **{statistics.quantiles(lags, n=10)[-1] if len(lags) >= 10 else max(lags):.1f}s**")
        p(f"- max: **{max(lags):.1f}s**")
    else:
        p("- no lag data collected")
    p("")

    # Section: price data sufficiency
    p("## Price data sufficiency near expiry")
    p("")
    if sufficient_60s:
        counts_ge_5 = sum(1 for x in sufficient_60s if x >= 5)
        counts_ge_10 = sum(1 for x in sufficient_60s if x >= 10)
        p(f"- Resolved markets with **≥5 samples in final 60s**: {counts_ge_5} / {len(sufficient_60s)}")
        p(f"- Resolved markets with **≥10 samples in final 60s**: {counts_ge_10} / {len(sufficient_60s)}")
    if sufficient_5min:
        counts_ge_30 = sum(1 for x in sufficient_5min if x >= 30)
        p(f"- Resolved markets with **≥30 samples in final 5min**: {counts_ge_30} / {len(sufficient_5min)}")
    p(f"- Resolved markets with any sample within final 15s: **{final_price_present}** / {len(resolutions)}")
    p(f"- Of those, markets where final-stretch book was thin (ask-bid > 0.20): **{thin_book_count}**")
    p("")

    # Section: recommendation
    p("## Recommendation")
    p("")
    rec = _recommend(dur_counts, resolutions, sufficient_60s, len(within_window))
    for line in rec:
        p(line)
    p("")

    # Appendix: sample resolved markets
    if clean:
        p("## Sample resolved markets (up to 12)")
        p("| end | underlying | duration | outcome | lag (s) | slug |")
        p("|---|---|---|---|---:|---|")
        for r in clean[:12]:
            m = market_by_id.get(r["market_id"])
            if not m:
                continue
            p(f"| {_fmt_ms(m['end_ts'])} | {m['underlying'] or '?'} "
              f"| {_bucket_duration(m['duration_s'])} | {r['outcome']} "
              f"| {r['resolution_lag_s']:.1f} | {m['slug']} |")
        p("")

    conn.close()
    return "\n".join(lines)


def _recommend(
    dur_counts: Counter,
    resolutions: list,
    sufficient_60s: list[int],
    within_window: int,
) -> list[str]:
    """Return markdown lines with the explicit recommendation."""
    lines: list[str] = []
    clean = [r for r in resolutions if r["resolved_cleanly"] == 1]
    five_m = dur_counts.get("5m", 0)
    fifteen_m = dur_counts.get("15m", 0)
    one_h = dur_counts.get("1h", 0)
    clean_count = len(clean)
    with_samples = sum(1 for x in sufficient_60s if x >= 5) if sufficient_60s else 0

    # Rubric
    if five_m >= 50 and clean_count >= 20 and with_samples >= clean_count // 2:
        lines.append("### ✅ PROCEED — full Expiry Microstructure Mode on 5m markets")
        lines.append("")
        lines.append(
            f"- {five_m} five-minute crypto markets discovered (plenty of throughput)."
        )
        lines.append(
            f"- {clean_count} clean resolutions observed within the probe window."
        )
        lines.append(
            f"- {with_samples} of those had ≥5 price samples in the final 60 seconds "
            "(demonstrates final-stretch sampling is feasible at 5s cadence)."
        )
        lines.append(
            "- Next step: build the full expiry sampler on 5m markets, switching to CLOB "
            "websockets for sub-second resolution, and match the spot feed exactly to "
            "each market's resolution source (critical for validity)."
        )
    elif (fifteen_m + one_h) >= 20 and clean_count >= 10:
        lines.append("### 🟡 PROCEED with caveats — use 15m / 1h markets, not 5m")
        lines.append("")
        lines.append(
            f"- 5m throughput insufficient ({five_m} seen). 15m ({fifteen_m}) + 1h ({one_h}) "
            "is enough for a slower validation cycle."
        )
        lines.append(
            f"- {clean_count} clean resolutions observed. At 15m/1h cadence a full run takes "
            "~3-5 days to reach statistical significance."
        )
        lines.append(
            "- Adjust Expiry Mode sampling window to 180s final stretch; the longer-duration "
            "markets are expected to be more efficient, so we should expect thinner edges."
        )
    else:
        lines.append("### ❌ DO NOT PROCEED — insufficient frequency or reliability")
        lines.append("")
        lines.append(
            f"- Only {five_m} 5m / {fifteen_m} 15m / {one_h} 1h crypto markets seen, "
            f"{clean_count} clean resolutions. Not enough signal."
        )
        lines.append(
            "- Consider pivoting to event-driven measurement (news → crypto reaction) or a "
            "different venue (Limitless has historically had sub-hour crypto markets)."
        )

    lines.append("")
    lines.append("### Unresolved design blockers (must fix before full build)")
    lines.append("")
    lines.append(
        "- **Reference feed matching:** each market resolves against a specific oracle "
        "(Chainlink / Coinbase / Binance). Until we match our spot feed exactly, any "
        "observed 'mispricing' may be venue-latency artifact."
    )
    lines.append(
        "- **Analytical metric:** `|poly - outcome|` (err_H) rewards certainty, not "
        "accuracy. Replace with calibration curves, Brier score vs. spot-implied benchmark, "
        "and lead-lag cross-correlation."
    )
    lines.append(
        "- **Hindsight-biased flags:** \"market underestimated the move\" flags will fire "
        "whenever spot moves, because spot movement *is* the outcome for up/down markets. "
        "Lead-lag τ>0 is the real question."
    )
    lines.append(
        "- **REST+midpoint is too coarse for final 10s.** Full build needs CLOB websocket "
        "with separate bid/ask, not 1Hz REST midpoint."
    )
    return lines


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="probe/probe.db")
    p.add_argument("--out", default="probe/REPORT.md")
    args = p.parse_args()

    if not Path(args.db).exists():
        raise SystemExit(f"db not found: {args.db}")
    report = generate_report(args.db)
    Path(args.out).write_text(report)
    print(report)
    print(f"\n---\nreport written to {args.out}")


if __name__ == "__main__":
    main()
