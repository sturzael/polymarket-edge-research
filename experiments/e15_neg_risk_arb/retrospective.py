"""Retrospective analysis of historical Polymarket neg-risk events.

Question 1 (this script): of recently-resolved neg-risk events, what fraction
resolved to a LISTED candidate (one of the active sub-markets) vs a TAIL
OUTCOME (all listed sub-markets resolved NO — winner was unlisted)?

This is the highest-leverage question because tail outcomes turn the "+42% arb"
on Nobel into a -100% loss. Knowing the historical rate empirically tells us
whether the strategy class is viable at all.

Method:
  1. Pull events from gamma /events with closed=true, sorted by closedTime desc
  2. Filter to negRisk=true
  3. For each event, examine all child markets (active+inactive)
  4. Classify based on outcome_prices:
       - LISTED-WIN: at least one ACTIVE child market resolved [1, 0]
       - TAIL: all active markets resolved [0, 1] (no listed candidate won)
       - DEGENERATE: <2 active markets, or unparseable outcomes
  5. Aggregate stats + per-event breakdown

Output: data/retrospective_q1.json + stdout summary.
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx

DATA_DIR = Path(__file__).parent / "data"
GAMMA = "https://gamma-api.polymarket.com"
OUT = DATA_DIR / "retrospective_q1.json"


def parse_outcome_prices(raw) -> tuple[float, float] | None:
    """Polymarket stores like \"['1', '0']\" or [1, 0]."""
    if raw is None:
        return None
    if isinstance(raw, list) and len(raw) == 2:
        try:
            return (float(raw[0]), float(raw[1]))
        except Exception:
            return None
    if isinstance(raw, str):
        try:
            v = ast.literal_eval(raw)
            if isinstance(v, list) and len(v) == 2:
                return (float(v[0]), float(v[1]))
        except Exception:
            pass
    return None


def classify_event(event: dict) -> tuple[str, dict]:
    """Returns (LISTED-WIN | TAIL | DEGENERATE, detail)."""
    markets = event.get("markets", [])
    # We classify by what the user could BUY — so look at active markets only.
    # But check all markets to detect "Other" / "option-X" placeholders.
    active = [m for m in markets if m.get("active") and m.get("closed")]
    if len(active) < 2:
        return "DEGENERATE", {"reason": f"only {len(active)} active+closed markets"}
    n_yes_winners = 0
    n_no_winners = 0
    n_unresolved = 0
    winning_slugs = []
    for m in active:
        op = parse_outcome_prices(m.get("outcomePrices"))
        if op is None:
            n_unresolved += 1
            continue
        yes_payout = op[0]
        if yes_payout == 1.0:
            n_yes_winners += 1
            winning_slugs.append(m.get("slug"))
        elif yes_payout == 0.0:
            n_no_winners += 1
        else:
            n_unresolved += 1
    detail = {
        "n_active_closed_markets": len(active),
        "n_yes_winners": n_yes_winners,
        "n_no_winners": n_no_winners,
        "n_unresolved": n_unresolved,
        "winning_slugs": winning_slugs,
    }
    if n_unresolved > 0:
        return "DEGENERATE", detail
    if n_yes_winners >= 1:
        return "LISTED-WIN", detail
    if n_no_winners == len(active):
        return "TAIL", detail
    return "DEGENERATE", detail


def fetch_recent_resolved(days: int) -> list[dict]:
    """Paginate /events closed=true, ordered by closedTime desc, until older than `days`."""
    out: list[dict] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    offset = 0
    page = 200
    with httpx.Client(timeout=20) as client:
        while True:
            r = client.get(f"{GAMMA}/events", params={
                "closed": "true", "limit": page, "offset": offset,
                "order": "closedTime", "ascending": "false",
            })
            if r.status_code != 200:
                print(f"  gamma {r.status_code} at offset={offset}; stopping")
                break
            batch = r.json()
            if not batch:
                break
            keep = []
            stop = False
            for e in batch:
                ct = e.get("closedTime") or e.get("closed_time")
                if not ct:
                    continue
                try:
                    cdt = datetime.fromisoformat(ct.replace("Z", "+00:00"))
                except Exception:
                    continue
                if cdt < cutoff:
                    stop = True
                    break
                keep.append(e)
            out.extend(keep)
            print(f"  offset={offset} batch_size={len(batch)} kept={len(keep)} total={len(out)}")
            if stop or len(batch) < page:
                break
            offset += page
            if offset > 5000:  # safety cap
                break
            time.sleep(0.1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=90, help="how many days back to scan")
    args = ap.parse_args()

    DATA_DIR.mkdir(exist_ok=True)
    print(f"[retrospective] pulling resolved events from last {args.days} days...")
    events = fetch_recent_resolved(args.days)
    print(f"  {len(events)} resolved events total")
    neg_risk = [e for e in events if e.get("negRisk")]
    print(f"  {len(neg_risk)} neg_risk events (multi-outcome)")

    classifications: list[dict] = []
    counter: Counter = Counter()
    for e in neg_risk:
        cls, detail = classify_event(e)
        counter[cls] += 1
        classifications.append({
            "slug": e.get("slug"),
            "title": e.get("title"),
            "closed_time": e.get("closedTime"),
            "n_total_markets": len(e.get("markets", [])),
            "classification": cls,
            "detail": detail,
        })

    # Tail-rate metric (only counts non-DEGENERATE)
    n_listed = counter["LISTED-WIN"]
    n_tail = counter["TAIL"]
    n_clean = n_listed + n_tail
    tail_rate = n_tail / n_clean if n_clean > 0 else None

    summary = {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "lookback_days": args.days,
        "n_total_resolved_events": len(events),
        "n_neg_risk_resolved": len(neg_risk),
        "classification_counts": dict(counter),
        "tail_rate_among_clean": round(tail_rate, 4) if tail_rate is not None else None,
        "interpretation": (
            "tail_rate = fraction of resolved neg-risk events where NO listed candidate won "
            "(an unlisted/Other outcome was selected). Each 1% = 1% chance our 'arb' loses 100%."
        ),
    }
    OUT.write_text(json.dumps({"summary": summary, "events": classifications},
                              indent=2, default=str))
    print()
    print("=" * 60)
    print(json.dumps(summary, indent=2))
    print()
    print(f"=== TAIL events (where listed candidates all lost) ===")
    tails = [c for c in classifications if c["classification"] == "TAIL"]
    for t in tails[:30]:
        print(f"  {t['slug'][:60]:60s} closed={(t['closed_time'] or '')[:16]} n_active={t['detail']['n_active_closed_markets']}")
    print()
    print(f"=== LISTED-WIN sample ===")
    for c in [x for x in classifications if x["classification"] == "LISTED-WIN"][:5]:
        print(f"  {c['slug'][:60]:60s} winner={c['detail']['winning_slugs'][0][:50] if c['detail']['winning_slugs'] else '?'}")


if __name__ == "__main__":
    sys.exit(main() or 0)
