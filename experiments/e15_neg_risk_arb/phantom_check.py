"""Phantom-depth checker — for a given event, query each leg's order book in
real time and report what's actually executable vs what gamma's snapshot claims.

Two modes:
  --visual   read-only: queries CLOB /book for each leg, prints depth at top
             3 levels. Good for "does this look real?"
  --real     prints the exact pm-trader-equivalent buy commands needed to
             test 1 share on each leg. The user runs these manually with
             real money to verify the ask is actually fillable. We do NOT
             execute these from this script — that's the user's call.

Usage:
    uv run python -m experiments.e15_neg_risk_arb.phantom_check \\
        --event nobel-peace-prize-winner-2026-139 --visual
    uv run python -m experiments.e15_neg_risk_arb.phantom_check \\
        --event next-ceo-of-apple --real
"""
from __future__ import annotations

import argparse
import json
import sys

import httpx

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"


def parse_token_ids(raw):
    if not raw:
        return []
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return []
    return raw if isinstance(raw, list) else []


def fetch_event(slug: str) -> dict | None:
    with httpx.Client(timeout=15) as client:
        r = client.get(f"{GAMMA}/events", params={"closed": "false", "limit": 500})
        for e in r.json() if r.status_code == 200 else []:
            if e.get("slug") == slug:
                return e
    return None


def fetch_book(token_id: str) -> dict:
    with httpx.Client(timeout=15) as client:
        r = client.get(f"{CLOB}/book", params={"token_id": token_id})
        return r.json() if r.status_code == 200 else {}


def cmd_visual(event: dict) -> None:
    print(f"\n=== {event.get('slug')} — {event.get('title')} ===")
    print(f"end_date={event.get('endDate')} negRisk={event.get('negRisk')}")
    print(f"description: {(event.get('description') or '')[:300]}\n")

    sum_asks = 0.0
    sum_bids = 0.0
    for m in event.get("markets", []):
        if not m.get("active") or m.get("closed"):
            continue
        slug = m.get("slug", "")[:55]
        gamma_ask = m.get("bestAsk")
        gamma_bid = m.get("bestBid")
        tids = parse_token_ids(m.get("clobTokenIds"))
        yes_token = tids[0] if tids else None
        if not yes_token:
            print(f"  {slug}  (no yes_token)")
            continue
        book = fetch_book(yes_token)
        asks = sorted([(float(a["price"]), float(a["size"])) for a in book.get("asks", [])], key=lambda x: x[0])[:3]
        bids = sorted([(float(b["price"]), float(b["size"])) for b in book.get("bids", [])], key=lambda x: -x[0])[:3]
        if gamma_ask is not None:
            sum_asks += float(gamma_ask)
        if gamma_bid is not None:
            sum_bids += float(gamma_bid)
        print(f"  {slug}")
        print(f"    gamma snapshot: ask={gamma_ask} bid={gamma_bid}")
        print(f"    CLOB asks (top 3): {asks if asks else 'EMPTY'}")
        print(f"    CLOB bids (top 3): {bids if bids else 'EMPTY'}")
        # Phantom check: does CLOB top-of-book agree with gamma?
        if asks and gamma_ask is not None:
            gap = abs(asks[0][0] - float(gamma_ask))
            if gap > 0.005:
                print(f"    ⚠ ASK MISMATCH: gamma says {gamma_ask}, CLOB says {asks[0][0]}")
        if not asks:
            print(f"    ⚠ PHANTOM: gamma showed ask but CLOB book is empty")
    print(f"\n  sum gamma asks = {sum_asks:.4f}  → buy-all-arb edge = {(1 - sum_asks)*100:+.2f}%")
    print(f"  sum gamma bids = {sum_bids:.4f}")


def cmd_real(event: dict) -> None:
    print(f"=== Real-money phantom test for {event.get('slug')} ===\n")
    print("Run each command MANUALLY in pm-trader CLI. Each places ONE share at the displayed ask.")
    print("If a leg fills as expected, depth is real. If it errors / fills at worse price / hangs, depth is phantom.\n")
    print("Total cost if all fill at quoted prices:")
    sum_cost = 0.0
    for m in event.get("markets", []):
        if not m.get("active") or m.get("closed"):
            continue
        gamma_ask = m.get("bestAsk")
        if gamma_ask is None:
            continue
        sum_cost += float(gamma_ask)
    print(f"  ~${sum_cost:.4f} (= sum of YES asks). Profit if all fills clear: ${1-sum_cost:.4f} per set\n")
    print("Commands (RUN ONE AT A TIME and check fill):")
    for m in event.get("markets", []):
        if not m.get("active") or m.get("closed"):
            continue
        slug = m.get("slug", "")
        ask = m.get("bestAsk")
        if ask is None:
            continue
        # 1 share at the ask
        usd = float(ask) * 1.0
        print(f"  pm-trader buy {slug} yes {usd:.4f}    # 1 share @ {ask}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--event", required=True, help="event slug (e.g. nobel-peace-prize-winner-2026-139)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--visual", action="store_true")
    g.add_argument("--real", action="store_true")
    args = ap.parse_args()
    e = fetch_event(args.event)
    if not e:
        print(f"event not found: {args.event}")
        return 2
    if args.visual:
        cmd_visual(e)
    else:
        cmd_real(e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
