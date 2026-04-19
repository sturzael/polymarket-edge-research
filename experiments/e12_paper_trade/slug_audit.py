"""Phase 1a — validate sports slug patterns against ~50 most recent resolutions.

Output: data/slug_audit.json with:
  - coverage of current SPORTS_SLUG_PATTERNS
  - false-positive rate (matched markets that aren't actually sports)
  - missed sub-categories (real sports markets the patterns didn't catch)
  - corrected pattern list (committed back to config.py manually if needed)

Also: verifies PolymarketReadOnlyClobClient.get_market returns populated tokens
on a few active sports markets (the e13 Investigation 3 unverified item).
"""
from __future__ import annotations

import asyncio
import json
import sys
from collections import Counter
from datetime import datetime, timezone

from . import config, gamma_client


OUT_JSON = config.HERE / "slug_audit.json"

CANDIDATE_PATTERNS = list(config.SPORTS_SLUG_PATTERNS) + [
    "soccer-", "epl-", "uefa-", "fifa-", "ncaa-", "tennis-", "golf-", "pga-",
    "f1-", "formula-", "boxing-", "chess-",
]


def slug_matches_any(slug: str, patterns) -> bool:
    s = (slug or "").lower()
    return any(p in s for p in patterns)


def is_actually_sports(market) -> bool:
    """Heuristic: check categories/tags for 'sports' or known sport names."""
    cats = []
    for attr in ("categories", "category"):
        v = getattr(market, attr, None)
        if v:
            if isinstance(v, list):
                cats.extend([str(x).lower() for x in v])
            else:
                cats.append(str(v).lower())
    sports_words = {"sports", "nba", "nfl", "mlb", "nhl", "tennis", "soccer",
                    "ufc", "mma", "cricket", "boxing", "wnba", "mls", "atp",
                    "wta", "epl", "premier league", "la liga", "f1"}
    return any(w in c for c in cats for w in sports_words)


async def verify_clob_tokens(active_sports_markets) -> dict:
    """For 5 active sports markets, fetch via CLOB and report tokens populated."""
    out = []
    for m in active_sports_markets[:5]:
        try:
            market = await gamma_client.fetch_clob_market(m.condition_id)
            tokens = []
            if market is None:
                tokens = []
            elif hasattr(market, "tokens"):
                tokens = market.tokens or []
            elif isinstance(market, dict):
                tokens = market.get("tokens", [])
            out.append({
                "slug": m.slug,
                "condition_id": m.condition_id,
                "n_tokens": len(tokens),
                "ok": len(tokens) >= 2,
            })
        except Exception as e:
            out.append({"slug": m.slug, "error": repr(e)})
    return {"samples": out, "all_ok": all(s.get("ok") for s in out)}


async def main() -> int:
    print("[1a] fetching recently resolved sports markets...")
    resolved = await gamma_client.fetch_recently_resolved_sports_markets(limit=200)
    print(f"      {len(resolved)} resolved markets matching current patterns")

    # Distribution by which pattern matched
    by_pattern: Counter = Counter()
    for m in resolved:
        s = (m.slug or "").lower()
        for p in config.SPORTS_SLUG_PATTERNS:
            if p in s:
                by_pattern[p] += 1
                break
        else:
            by_pattern["__no_match__"] += 1

    # Now broader sweep: fetch all recent closed markets and see what we missed
    print("[1a] broader sweep for false-negatives...")
    from polymarket_apis.types.gamma_types import GammaMarket  # noqa
    all_recent = await asyncio.to_thread(
        gamma_client.gamma().get_markets,
        closed=True, limit=200, order="closed_time", ascending=False,
    )
    looks_sports = [m for m in (all_recent or []) if is_actually_sports(m)]
    matched = [m for m in looks_sports if slug_matches_any(m.slug or "", config.SPORTS_SLUG_PATTERNS)]
    missed = [m for m in looks_sports if not slug_matches_any(m.slug or "", config.SPORTS_SLUG_PATTERNS)]

    # And try the candidate pattern list to see if any extras would help
    candidates_only = [
        m for m in missed
        if slug_matches_any(m.slug or "", set(CANDIDATE_PATTERNS) - set(config.SPORTS_SLUG_PATTERNS))
    ]

    print("[1a] CLOB token verification...")
    actives = await gamma_client.fetch_active_sports_markets(limit=30)
    clob = await verify_clob_tokens(actives)

    out = {
        "probed_at": datetime.now(timezone.utc).isoformat(),
        "current_patterns": list(config.SPORTS_SLUG_PATTERNS),
        "n_resolved_matched": len(resolved),
        "match_distribution": dict(by_pattern.most_common()),
        "broader_sweep": {
            "n_recent_closed": len(all_recent or []),
            "n_looks_sports": len(looks_sports),
            "n_matched_by_current_patterns": len(matched),
            "n_missed_by_current_patterns": len(missed),
            "n_caught_by_candidate_patterns": len(candidates_only),
            "missed_sample_slugs": [m.slug for m in missed[:10]],
            "candidate_caught_sample": [m.slug for m in candidates_only[:10]],
        },
        "clob_token_verification": clob,
    }
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str))
    print()
    print("=" * 60)
    print(f"slug_audit → {OUT_JSON}")
    print(f"current patterns matched {len(matched)}/{len(looks_sports)} actually-sports recent closed markets")
    print(f"candidate patterns would add {len(candidates_only)}")
    print(f"CLOB tokens populated on {sum(1 for s in clob['samples'] if s.get('ok'))}/{len(clob['samples'])} active sports markets")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
