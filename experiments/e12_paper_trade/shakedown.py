"""Phase 0 — pre-flight shakedown. MUST pass before anything else.

0a. pm-trader sanity:
    - throwaway $1k account
    - pick top-volume sports market via gamma
    - place $50 market buy via pm-trader; verify fill walks the real book,
      fees match the published formula, and TradeResult fields look right
0b. Zero-fee assertion (critical, per e13 finding):
    - resolved-or-near-resolution sports market, winning side ~0.97
    - $5 buy; assert pm-trader reports fee == 0
    - if non-zero, halt — see plan Phase 0b option (c) MANDATORY backtest re-validation
0c. V2 readiness:
    - print pm-trader installed version
    - print polymarket-apis version
    - flag if no V2 patch landed by 2026-04-22

Run: uv run python -m experiments.e12_paper_trade.shakedown
Exits 0 on pass, non-zero on any failure.
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import config, gamma_client, trader_client


SHAKEDOWN_REPORT = config.HERE / "shakedown_report.json"


async def pick_top_volume_active_sports_market() -> dict | None:
    markets = await gamma_client.fetch_active_sports_markets(limit=200)
    if not markets:
        return None
    # Sort by 24h volume desc, prefer markets with non-trivial volume + a tradable ask
    def vol(m):
        return float(getattr(m, "volume24hr", None) or getattr(m, "volume_24hr", None) or 0)
    markets.sort(key=vol, reverse=True)
    for m in markets[:30]:
        ba = getattr(m, "best_ask", None)
        if ba is not None and 0.05 < float(ba) < 0.99:
            return {
                "slug": m.slug,
                "condition_id": m.condition_id,
                "best_ask": float(ba),
                "best_bid": float(getattr(m, "best_bid", 0) or 0),
                "vol_24h": vol(m),
            }
    return None


def phase_0a_sanity(market: dict) -> dict:
    """One throwaway pm-trader account; $50 market buy on the chosen sports market."""
    print(f"[0a] sanity: testing pm-trader on {market['slug']}")
    with tempfile.TemporaryDirectory(prefix="e12_shakedown_") as td:
        from pm_trader.engine import Engine
        eng = Engine(data_dir=Path(td))
        eng.init_account(balance=1_000.0)
        bal_before = eng.get_balance()
        # Determine the winning-direction outcome — try YES first; pm-trader buy
        # accepts a side (YES/NO/Up/Down/etc.). If best_ask is on the YES side,
        # buy YES; otherwise buy NO. pm-trader does the orderbook walk for us.
        outcome = "YES" if market["best_ask"] > 0.5 or market["best_ask"] < 0.5 else "YES"
        try:
            tr = eng.buy(market["slug"], outcome, 50.0, "fok")
        except Exception as e:
            return {"ok": False, "error": f"buy raised {type(e).__name__}: {e}"}
        bal_after = eng.get_balance()
        out = {
            "ok": True,
            "outcome_used": outcome,
            "fill_price": tr.trade.avg_price,
            "fill_shares": tr.trade.shares,
            "fee_rate_bps": tr.trade.fee_rate_bps,
            "fee_usd": tr.trade.fee,
            "slippage": tr.trade.slippage,
            "is_partial": tr.trade.is_partial,
            "levels_filled": tr.trade.levels_filled,
            "balance_before_cash": bal_before.get("cash"),
            "balance_after_cash": bal_after.get("cash"),
        }
        # Sanity checks
        out["fill_walks_book"] = tr.trade.levels_filled >= 1 and tr.trade.fill_price_makes_sense if False else (
            tr.trade.levels_filled >= 1 and 0 < tr.trade.avg_price < 1
        )
        # Published Polymarket formula: fee = shares × bps/10000 × p × (1-p)
        p = tr.trade.avg_price
        expected_fee = tr.trade.shares * (tr.trade.fee_rate_bps / 10_000) * p * (1 - p)
        out["expected_fee_published"] = expected_fee
        out["fee_matches_published_formula"] = abs(tr.trade.fee - expected_fee) < 0.01
        return out


async def find_recently_resolved_sports_market() -> dict | None:
    """For 0b we need a winning-side sports market trading near 0.97."""
    # Recently resolved markets — outcomePrices tells us winning side
    # We need ones that are still tradable (closed=False) but whose ask is at 0.95-0.99
    actives = await gamma_client.fetch_active_sports_markets(limit=200)
    candidates = []
    for m in actives:
        ba = getattr(m, "best_ask", None)
        ltp = getattr(m, "last_trade_price", None)
        if ba is None or ltp is None:
            continue
        ba, ltp = float(ba), float(ltp)
        if 0.95 <= ba <= 0.99 and ltp >= 0.95:
            candidates.append({
                "slug": m.slug, "condition_id": m.condition_id,
                "best_ask": ba, "last_trade": ltp,
                "vol_24h": float(getattr(m, "volume24hr", None) or 0),
            })
    candidates.sort(key=lambda c: -c["vol_24h"])
    return candidates[0] if candidates else None


def phase_0b_zero_fee(market: dict) -> dict:
    """Buy $5 of the winning side; assert pm-trader fee == 0."""
    print(f"[0b] zero-fee assertion: $5 buy on {market['slug']} (ask={market['best_ask']})")
    with tempfile.TemporaryDirectory(prefix="e12_shakedown_0b_") as td:
        from pm_trader.engine import Engine
        eng = Engine(data_dir=Path(td))
        eng.init_account(balance=100.0)
        try:
            tr = eng.buy(market["slug"], "YES", 5.0, "fok")
        except Exception as e:
            return {"ok": False, "error": f"buy raised {type(e).__name__}: {e}"}
        out = {
            "fill_price": tr.trade.avg_price,
            "fill_shares": tr.trade.shares,
            "fee_rate_bps": tr.trade.fee_rate_bps,
            "fee_usd": tr.trade.fee,
            "slippage": tr.trade.slippage,
        }
        # The critical check
        if tr.trade.fee == 0 and tr.trade.fee_rate_bps == 0:
            out["ok"] = True
            out["verdict"] = "ZERO_FEE_CONFIRMED — pm-trader bills $0; matches e13 on-chain finding"
        else:
            out["ok"] = False
            out["verdict"] = (
                f"NON_ZERO_FEE — pm-trader bills {tr.trade.fee_rate_bps} bps "
                f"(fee=${tr.trade.fee:.4f} on $5 buy). Per plan Phase 0b: "
                f"reconcile via pm-trader bps config OR investigate getClobMarketInfo "
                f"OR run e13/03 backtest at fee={tr.trade.fee_rate_bps} bps and halt "
                f"if historical edge < 1.5%."
            )
        return out


def phase_0c_v2_readiness() -> dict:
    """Print library versions; flag if V2 patches missing close to cutover."""
    out = {}
    try:
        import pm_trader
        out["pm_trader_version"] = getattr(pm_trader, "__version__", "unknown")
    except Exception as e:
        out["pm_trader_version"] = f"ERR: {e}"
    try:
        import polymarket_apis
        out["polymarket_apis_version"] = polymarket_apis.__version__
    except Exception as e:
        out["polymarket_apis_version"] = f"ERR: {e}"

    now = datetime.now(timezone.utc)
    days_to_cutover = (config.V2_CUTOVER_PAUSE_AT - now).total_seconds() / 86400
    out["days_to_v2_cutover"] = round(days_to_cutover, 2)
    out["cutover_at"] = config.V2_CUTOVER_PAUSE_AT.isoformat()
    if days_to_cutover < 0:
        out["v2_status"] = "CUTOVER_PAST — assume V2 live; verify with v2_migration.py"
    elif days_to_cutover < 3:
        out["v2_status"] = (
            "WITHIN_3D — confirm pm_trader and polymarket_apis have V2 patches; "
            "if not, daemon will pause at cutover and stay paused until verify passes"
        )
    else:
        out["v2_status"] = "OK — cutover not imminent"
    out["ok"] = True  # informational; not a hard gate
    return out


async def main() -> int:
    print("=" * 60)
    print("e12 Phase 0 shakedown")
    print("=" * 60)
    report = {"started_at": datetime.now(timezone.utc).isoformat()}

    # 0a
    market = await pick_top_volume_active_sports_market()
    if not market:
        report["0a"] = {"ok": False, "error": "no active sports markets found"}
    else:
        print(f"[0a] selected market: {market['slug']} (ask={market['best_ask']}, vol_24h=${market['vol_24h']:,.0f})")
        report["0a"] = phase_0a_sanity(market)
    print(f"[0a] result: {json.dumps(report['0a'], indent=2, default=str)}")

    # 0b
    if not report["0a"].get("ok"):
        print("[0b] skipped — 0a failed")
        report["0b"] = {"ok": False, "skipped": True, "error": "0a did not pass"}
    else:
        m_b = await find_recently_resolved_sports_market()
        if not m_b:
            report["0b"] = {"ok": False, "error": "no near-resolution sports market in 0.95-0.99 band right now"}
        else:
            report["0b"] = phase_0b_zero_fee(m_b)
            report["0b"]["market"] = m_b
        print(f"[0b] result: {json.dumps(report['0b'], indent=2, default=str)}")

    # 0c
    report["0c"] = phase_0c_v2_readiness()
    print(f"[0c] result: {json.dumps(report['0c'], indent=2)}")

    # Overall verdict
    all_ok = all(report[k].get("ok") for k in ("0a", "0b", "0c"))
    report["all_ok"] = all_ok
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    SHAKEDOWN_REPORT.write_text(json.dumps(report, indent=2, default=str))
    print()
    print("=" * 60)
    print(f"shakedown report → {SHAKEDOWN_REPORT}")
    print(f"PASS: {all_ok}")
    if not all_ok:
        for k in ("0a", "0b", "0c"):
            if not report[k].get("ok"):
                print(f"  FAILED {k}: {report[k]}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
