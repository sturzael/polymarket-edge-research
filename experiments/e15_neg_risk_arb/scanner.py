"""Neg-risk arb scanner.

For every active negRisk event on Polymarket, compute the sum of YES best_asks
across active child markets. Flag opportunities where sum < 1.00.

CRITICAL — completeness check:
  Some neg-risk events have INACTIVE placeholder markets ("will-option-X-win-",
  "will-other-win-") and a description like "may be added at a later date."
  In those events, a third-party winner means our basket loses 100%. The arb
  is probabilistic, not arithmetic. We classify each event as:
    - GUARANTEED — all outcomes active, no Other/placeholder, no "added at a
      later date" language. Sum < 1 = pure arithmetic arb.
    - PROBABILISTIC — has placeholders or Other slot. Edge × P(known-outcome-wins).
    - DEGENERATE — only 1 active market (not actually a multi-outcome event).

Output: data/scan.json + sorted stdout table.

Usage:
    uv run python -m experiments.e15_neg_risk_arb.scanner
    uv run python -m experiments.e15_neg_risk_arb.scanner --depth   # also check book depth
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx

DATA_DIR = Path(__file__).parent / "data"
GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"

PLACEHOLDER_SLUGS = ("will-option-", "will-other-")
COMPLETENESS_RED_FLAGS = (
    "may be added", "added at a later date", "will be added",
    "additional candidates", "other candidates",
)


@dataclass
class MarketLeg:
    slug: str
    yes_token_id: str
    best_ask: float
    best_bid: float
    last_trade: float | None
    ask_depth: float = 0.0     # filled if --depth
    bid_depth: float = 0.0


@dataclass
class Opportunity:
    event_slug: str
    event_title: str
    end_date: str
    n_active: int
    n_inactive_placeholders: int
    completeness: str          # 'GUARANTEED' | 'PROBABILISTIC' | 'DEGENERATE'
    sum_asks: float
    sum_bids: float
    edge_pct: float            # positive = buy-all arb
    legs: list[MarketLeg] = field(default_factory=list)
    description_excerpt: str = ""
    has_red_flag_language: bool = False
    days_to_resolution: float | None = None
    min_executable_sets: float | None = None  # min ask_depth across legs (only with --depth)
    max_profit_usd: float | None = None       # min_sets × edge


def parse_token_ids(raw) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return []
    if isinstance(raw, list):
        return raw
    return []


def classify_completeness(event: dict) -> tuple[str, int, bool]:
    """Returns (completeness_label, n_inactive_placeholders, has_red_flag_language)."""
    desc = (event.get("description") or "").lower()
    has_red_flag = any(rf in desc for rf in COMPLETENESS_RED_FLAGS)
    markets = event.get("markets", [])
    n_active = sum(1 for m in markets if m.get("active") and not m.get("closed"))
    n_placeholders = sum(
        1 for m in markets
        if any((m.get("slug") or "").startswith(p) for p in PLACEHOLDER_SLUGS)
    )
    if n_active < 2:
        return "DEGENERATE", n_placeholders, has_red_flag
    if has_red_flag or n_placeholders > 0:
        return "PROBABILISTIC", n_placeholders, has_red_flag
    return "GUARANTEED", 0, False


def fetch_book_depth(client: httpx.Client, token_id: str, side: str) -> float:
    """Sum of size at the best price level (within 0.5¢)."""
    try:
        r = client.get(f"{CLOB}/book", params={"token_id": token_id}, timeout=10)
        if r.status_code != 200:
            return 0.0
        book = r.json()
        levels = book.get(side, [])
        if not levels:
            return 0.0
        if side == "asks":
            levels.sort(key=lambda x: float(x["price"]))
        else:
            levels.sort(key=lambda x: -float(x["price"]))
        best_p = float(levels[0]["price"])
        # Sum size within 0.5¢ of best
        return sum(float(l["size"]) for l in levels if abs(float(l["price"]) - best_p) <= 0.005)
    except Exception:
        return 0.0


def scan(check_depth: bool = False) -> list[Opportunity]:
    DATA_DIR.mkdir(exist_ok=True)
    with httpx.Client() as client:
        r = client.get(f"{GAMMA}/events",
                       params={"closed": "false", "active": "true", "limit": 500},
                       timeout=20)
        events = r.json() if r.status_code == 200 else []

    opportunities: list[Opportunity] = []
    now = datetime.now(timezone.utc)
    with httpx.Client() as client:
        for e in events:
            if not e.get("negRisk"):
                continue
            completeness, n_placeholders, has_red_flag = classify_completeness(e)
            if completeness == "DEGENERATE":
                continue

            legs: list[MarketLeg] = []
            for m in e.get("markets", []):
                if not m.get("active") or m.get("closed"):
                    continue
                ba = m.get("bestAsk")
                bb = m.get("bestBid")
                if ba is None:
                    continue
                try:
                    ba = float(ba); bb = float(bb) if bb else 0.0
                except Exception:
                    continue
                if not (0 < ba < 1):
                    continue
                tids = parse_token_ids(m.get("clobTokenIds"))
                yes_tok = tids[0] if tids else ""
                legs.append(MarketLeg(
                    slug=m.get("slug", ""),
                    yes_token_id=yes_tok,
                    best_ask=ba, best_bid=bb,
                    last_trade=float(m.get("lastTradePrice") or 0) or None,
                ))
            if len(legs) < 2:
                continue

            sum_asks = sum(l.best_ask for l in legs)
            sum_bids = sum(l.best_bid for l in legs)
            edge_pct = (1 - sum_asks) * 100  # buy-all arb

            if edge_pct <= 0 and (sum_bids - 1) * 100 <= 0:
                continue  # no opportunity in either direction

            ed = e.get("endDate")
            days = None
            if ed:
                try:
                    edt = datetime.fromisoformat(ed.replace("Z", "+00:00"))
                    days = (edt - now).total_seconds() / 86400
                except Exception:
                    pass
            # Filter past-end-date events — orphaned positions, not arbs
            if days is not None and days < 0:
                continue

            opp = Opportunity(
                event_slug=e.get("slug", ""),
                event_title=e.get("title", ""),
                end_date=ed or "",
                n_active=len(legs),
                n_inactive_placeholders=n_placeholders,
                completeness=completeness,
                sum_asks=round(sum_asks, 4),
                sum_bids=round(sum_bids, 4),
                edge_pct=round(edge_pct, 3),
                legs=legs,
                description_excerpt=(e.get("description") or "")[:200],
                has_red_flag_language=has_red_flag,
                days_to_resolution=round(days, 1) if days is not None else None,
            )

            if check_depth:
                for leg in opp.legs:
                    if leg.yes_token_id:
                        leg.ask_depth = fetch_book_depth(client, leg.yes_token_id, "asks")
                        leg.bid_depth = fetch_book_depth(client, leg.yes_token_id, "bids")
                if opp.legs and all(l.ask_depth > 0 for l in opp.legs):
                    opp.min_executable_sets = min(l.ask_depth for l in opp.legs)
                    opp.max_profit_usd = (opp.min_executable_sets * (1 - opp.sum_asks)) if opp.edge_pct > 0 else 0.0

            opportunities.append(opp)

    opportunities.sort(key=lambda o: -abs(o.edge_pct))
    return opportunities


def print_report(opps: list[Opportunity]) -> None:
    by_class: dict[str, list[Opportunity]] = {"GUARANTEED": [], "PROBABILISTIC": []}
    for o in opps:
        by_class.setdefault(o.completeness, []).append(o)

    for cls in ("GUARANTEED", "PROBABILISTIC"):
        bucket = by_class.get(cls, [])
        if not bucket:
            continue
        print(f"\n=== {cls} ({len(bucket)}) ===")
        print(f"{'edge':>6}  {'sum_asks':>8}  {'sum_bids':>8}  {'n':>3}  {'days':>6}  {'min_sets':>8}  {'profit':>7}  event_slug")
        for o in bucket[:30]:
            ms = f"{o.min_executable_sets:.0f}" if o.min_executable_sets is not None else "?"
            mp = f"${o.max_profit_usd:.2f}" if o.max_profit_usd is not None else "?"
            d = f"{o.days_to_resolution:.0f}" if o.days_to_resolution is not None else "?"
            print(f"  {o.edge_pct:+5.2f}%  {o.sum_asks:8.4f}  {o.sum_bids:8.4f}  {o.n_active:>3d}  {d:>6}  {ms:>8}  {mp:>7}  {o.event_slug[:55]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--depth", action="store_true", help="also fetch order book depth (slower)")
    args = ap.parse_args()
    print(f"scanning at {datetime.now(timezone.utc).isoformat()}...")
    opps = scan(check_depth=args.depth)
    DATA_DIR.mkdir(exist_ok=True)
    out_path = DATA_DIR / f"scan_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.json"
    out_path.write_text(json.dumps([{
        "event_slug": o.event_slug, "completeness": o.completeness,
        "edge_pct": o.edge_pct, "sum_asks": o.sum_asks, "sum_bids": o.sum_bids,
        "n_active": o.n_active, "n_inactive_placeholders": o.n_inactive_placeholders,
        "days_to_resolution": o.days_to_resolution,
        "has_red_flag_language": o.has_red_flag_language,
        "min_executable_sets": o.min_executable_sets,
        "max_profit_usd": o.max_profit_usd,
        "legs": [{"slug": l.slug, "ask": l.best_ask, "bid": l.best_bid,
                  "ask_depth": l.ask_depth, "bid_depth": l.bid_depth} for l in o.legs],
        "description_excerpt": o.description_excerpt,
    } for o in opps], indent=2))
    print(f"wrote {out_path}")
    print(f"\n{len(opps)} total opportunities (any direction, any completeness)")
    print_report(opps)


if __name__ == "__main__":
    sys.exit(main() or 0)
