"""Report — joins pm-trader trade history with sidecar position_context.

Per (size_model × entry_cap) cell:
  - positions opened / resolved / disputed / stuck / open
  - gross + net edge (re-scoreable via --fee-bps)
  - hit rate, avg hold, time-weighted return
  - path split (feed vs book_poll)
  - risk-gate skip counts
  - missed-opp diagnostic (no_detection / cap_too_tight / attempted_no_fill / partial_fill)
  - V2 migration status
  - Decision-criterion verdict per cell

Usage:
    uv run python -m experiments.e12_paper_trade.report
    uv run python -m experiments.e12_paper_trade.report --fee-bps 100
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

from . import config, sidecar, trader_client


def _fmt_pct(x: float | None) -> str:
    return f"{x*100:6.2f}%" if x is not None else "  n/a "


def _decision_verdict(net_edge: float | None, total_pnl: float, n: int) -> str:
    if n < config.EARLY_KILL_AFTER_TRADES:
        return "PRE-SAMPLE"
    if n < config.SAMPLE_TARGET_TRADES:
        if net_edge is not None and net_edge < 0 and total_pnl < 0:
            return "EARLY-KILLED"
        return "PROVISIONAL"
    if net_edge is None:
        return "PROVISIONAL"
    if net_edge < 0.005 or total_pnl < 0:
        return "KILL"
    if net_edge < 0.015:
        return "AMBIGUOUS_extend"
    return "PROCEED"


def report_cell(cell: str, fee_bps: float) -> dict:
    bal = trader_client.get_balance_sync(cell)
    history = trader_client.get_history_sync(cell)

    with sidecar.conn() as c:
        ctx_rows = list(c.execute(
            "SELECT * FROM position_context WHERE account = ?", (cell,),
        ))
        det_rows = list(c.execute(
            "SELECT skipped_reason, COUNT(*) AS n FROM detections WHERE account = ? GROUP BY skipped_reason",
            (cell,),
        ))

    by_status = Counter(r["resolution_status"] for r in ctx_rows)
    n_resolved = by_status["resolved_win"] + by_status["resolved_loss"]
    by_path = Counter(r["detection_path"] for r in ctx_rows)
    by_skip = {r["skipped_reason"]: r["n"] for r in det_rows if r["skipped_reason"]}

    # Per-position pnl from sidecar + historical trade entry
    per_position = []
    for r in ctx_rows:
        if r["resolution_status"] not in ("resolved_win", "resolved_loss"):
            continue
        # Gross: payout(0/1) - entry_ask
        gross = (r["resolution_price"] or 0) - r["entry_ask"]
        # Apply fee_bps to entry side: fee = bps/10000 * entry × (1-entry) per Polymarket formula
        fee_per_share = (fee_bps / 10_000) * r["entry_ask"] * (1 - r["entry_ask"])
        net = gross - fee_per_share
        # Hold time
        if r["resolved_at"] and r["detected_at"]:
            try:
                t0 = datetime.fromisoformat(r["detected_at"])
                t1 = datetime.fromisoformat(r["resolved_at"])
                hold_min = (t1 - t0).total_seconds() / 60
            except Exception:
                hold_min = None
        else:
            hold_min = None
        per_position.append({"gross": gross, "net": net, "hold_min": hold_min,
                             "entry_ask": r["entry_ask"], "ask_size": r["ask_size_at_entry"]})

    n = len(per_position)
    avg_gross = sum(p["gross"] for p in per_position) / n if n else None
    avg_net = sum(p["net"] for p in per_position) / n if n else None
    holds = [p["hold_min"] for p in per_position if p["hold_min"] is not None]
    avg_hold = sum(holds) / len(holds) if holds else None
    hits = sum(1 for r in ctx_rows if r["resolution_status"] == "resolved_win")
    hit_rate = hits / n_resolved if n_resolved else None
    total_pnl = sum(p["net"] * (p["ask_size"] or 0) for p in per_position)

    verdict = _decision_verdict(avg_net, total_pnl, n)

    return {
        "cell": cell,
        "balance": bal,
        "n_opened": len(ctx_rows),
        "by_status": dict(by_status),
        "by_path": dict(by_path),
        "skip_reasons": by_skip,
        "n_resolved": n,
        "hit_rate": hit_rate,
        "gross_edge": avg_gross,
        "net_edge": avg_net,
        "avg_hold_min": avg_hold,
        "total_pnl_usd": total_pnl,
        "verdict": verdict,
    }


def report_all(fee_bps: float) -> None:
    print(f"e12 report — fee_bps={fee_bps} — generated {datetime.now(timezone.utc).isoformat()}")
    print(f"V2 protocol_version (current): {sidecar.current_protocol_version()}, paused={sidecar.is_paused()}")
    print()
    cells = [config.cell_name(*acc) for acc in config.ACCOUNTS]
    print(f"{'cell':<42}  {'opened':>6}  {'resolved':>8}  {'hit_rate':>8}  {'gross':>7}  {'net':>7}  {'pnl_usd':>9}  {'hold_m':>6}  {'verdict':<14}")
    for cell in cells:
        r = report_cell(cell, fee_bps)
        print(f"{r['cell']:<42}  {r['n_opened']:>6}  {r['n_resolved']:>8}  "
              f"{_fmt_pct(r['hit_rate'])}  {_fmt_pct(r['gross_edge'])}  {_fmt_pct(r['net_edge'])}  "
              f"${r['total_pnl_usd']:>8,.2f}  {(r['avg_hold_min'] or 0):>5.1f}m  {r['verdict']:<14}")
        if r["skip_reasons"]:
            sk = ", ".join(f"{k}={v}" for k, v in r["skip_reasons"].items())
            print(f"  skips: {sk}")

    # Missed-opportunity diagnostic
    with sidecar.conn() as c:
        miss_rows = c.execute(
            "SELECT reason_we_missed, COUNT(*) AS n FROM missed_opportunities GROUP BY reason_we_missed ORDER BY n DESC"
        ).fetchall()
    if miss_rows:
        print()
        print("missed_opportunities diagnostic (per plan §Decision criterion):")
        total = sum(r["n"] for r in miss_rows)
        for r in miss_rows:
            pct = r["n"] / total * 100
            print(f"  {r['reason_we_missed']:<25}  {r['n']:>5}  ({pct:5.1f}%)")
        # Dominant reason hint
        top = miss_rows[0]
        hints = {
            "no_detection":      "→ poll too slow; consider WebSockets / lower POLL_INTERVAL_S",
            "cap_too_tight":     "→ edge at higher prices than caps; loosen ENTRY_TARGET_CAPS",
            "attempted_no_fill": "→ latency/contention; consider VPS",
            "partial_fill":      "→ depth too thin; reduce DEPTH_SCALED_FRAC",
        }
        print(f"  hint: {hints.get(top['reason_we_missed'], '—')}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--fee-bps", type=float, default=config.FEE_BPS)
    args = p.parse_args()
    sidecar.init_db()
    report_all(args.fee_bps)
    return 0


if __name__ == "__main__":
    sys.exit(main())
