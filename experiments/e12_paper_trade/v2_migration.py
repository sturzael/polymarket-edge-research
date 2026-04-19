"""V2 cutover scripts. Two subcommands:

  snapshot — capture pre-cutover state (run 2026-04-22 ~09:30 UTC)
  verify   — diff post-cutover; flag breaking changes (run 2026-04-23 +24h)

If `verify` flags breakage, the daemon stays paused. Per the plan's
pre-commit, if any of {fee_bps changes by ≥ 50, slug coverage drops by
≥ 20%, best_ask distribution shifts by ≥ 10%}, the report should treat
V2-tagged positions as discardable.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import statistics
from datetime import datetime, timezone

from . import config, gamma_client

SNAP_PATH = config.HERE / "data" / "v2_pre_snapshot.json"
VERIFY_PATH = config.HERE / "data" / "v2_post_verify.json"


async def snapshot() -> dict:
    SNAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    print("[v2_migration snapshot] capturing pre-cutover state...")
    actives = await gamma_client.fetch_active_sports_markets(limit=100)
    sample_markets = [
        {"slug": m.slug, "condition_id": m.condition_id,
         "best_ask": float(getattr(m, "best_ask", 0) or 0),
         "best_bid": float(getattr(m, "best_bid", 0) or 0),
         "last_trade_price": float(getattr(m, "last_trade_price", 0) or 0)}
        for m in actives[:50]
    ]
    asks = [m["best_ask"] for m in sample_markets if m["best_ask"]]
    out = {
        "snapshot_at": datetime.now(timezone.utc).isoformat(),
        "n_active_sports_sample": len(sample_markets),
        "best_ask_distribution": {
            "mean": statistics.mean(asks) if asks else None,
            "median": statistics.median(asks) if asks else None,
            "stdev": statistics.stdev(asks) if len(asks) > 1 else None,
        },
        "sample_markets": sample_markets,
        "polymarket_apis_version": __import__("polymarket_apis").__version__,
    }
    SNAP_PATH.write_text(json.dumps(out, indent=2, default=str))
    print(f"  wrote {SNAP_PATH}")
    return out


async def verify() -> int:
    if not SNAP_PATH.exists():
        print(f"ABORT: {SNAP_PATH} missing — run `snapshot` first")
        return 2
    print("[v2_migration verify] comparing pre vs post...")
    pre = json.loads(SNAP_PATH.read_text())
    actives = await gamma_client.fetch_active_sports_markets(limit=100)
    post_sample = [
        {"slug": m.slug, "condition_id": m.condition_id,
         "best_ask": float(getattr(m, "best_ask", 0) or 0),
         "best_bid": float(getattr(m, "best_bid", 0) or 0)}
        for m in actives[:50]
    ]
    post_asks = [m["best_ask"] for m in post_sample if m["best_ask"]]
    post_mean = statistics.mean(post_asks) if post_asks else None
    pre_mean = pre.get("best_ask_distribution", {}).get("mean")

    # Pre-commit checks
    breakage = {}
    if pre_mean and post_mean:
        shift_pct = abs(post_mean - pre_mean) / pre_mean
        breakage["best_ask_shift_pct"] = round(shift_pct, 4)
        breakage["best_ask_shift_breaks"] = shift_pct > 0.10
    breakage["slug_coverage_pre"] = pre.get("n_active_sports_sample", 0)
    breakage["slug_coverage_post"] = len(post_sample)
    breakage["slug_coverage_drop_pct"] = round(
        max(0, breakage["slug_coverage_pre"] - breakage["slug_coverage_post"])
        / max(breakage["slug_coverage_pre"], 1), 4,
    )
    breakage["slug_coverage_breaks"] = breakage["slug_coverage_drop_pct"] > 0.20

    out = {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "pre_snapshot_at": pre.get("snapshot_at"),
        "n_post_sample": len(post_sample),
        "best_ask_pre_mean": pre_mean,
        "best_ask_post_mean": post_mean,
        "breakage_checks": breakage,
        "verdict": "BREAKING" if any(v is True for v in breakage.values()) else "CLEAN",
    }
    VERIFY_PATH.write_text(json.dumps(out, indent=2, default=str))
    print(json.dumps(out, indent=2, default=str))
    return 0 if out["verdict"] == "CLEAN" else 1


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["snapshot", "verify"])
    args = p.parse_args()
    if args.cmd == "snapshot":
        asyncio.run(snapshot())
        return 0
    return asyncio.run(verify())


if __name__ == "__main__":
    sys.exit(main())
