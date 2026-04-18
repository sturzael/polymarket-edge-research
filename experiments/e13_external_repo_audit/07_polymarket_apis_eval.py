"""Eval polymarket-apis (PyPI lib): is it nicer than hand-rolled aiohttp?

Compares against e9/scan.py which uses raw aiohttp + dict parsing for:
  - gamma-api `/markets` listing
  - clob-api `/markets/{cid}` for token IDs
  - clob-api `/book` for ask depth

If polymarket-apis covers all three with typed responses, it would shrink
e12/detector.py and trader_client.py meaningfully.

Output:
  data/07_polymarket_apis_eval.json — verdict + per-call notes
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
OUT_JSON = DATA_DIR / "07_polymarket_apis_eval.json"


async def eval_gamma() -> dict:
    out = {"call": "gamma /markets active=true closed=false"}
    try:
        from polymarket_apis import PolymarketGammaClient
        c = PolymarketGammaClient()
        # The client is sync; call from thread-pool to avoid blocking event loop
        t = time.time()
        markets = await asyncio.to_thread(c.get_markets, closed=False, active=True, limit=10)
        out["elapsed_s"] = round(time.time()-t, 2)
        out["n_returned"] = len(markets) if markets else 0
        if markets:
            sample = markets[0]
            # Markets returned are typically Pydantic models — peek at fields
            if hasattr(sample, "model_dump"):
                d = sample.model_dump()
                out["sample_fields"] = sorted(d.keys())[:20]
                out["sample_slug"] = d.get("slug")
                out["typed"] = True
            else:
                out["sample_fields"] = sorted(sample.keys()) if isinstance(sample, dict) else []
                out["typed"] = False
    except Exception as e:
        out["error"] = repr(e)
        out["traceback"] = traceback.format_exc()
    return out


async def eval_clob_market_book() -> dict:
    out = {"call": "clob /markets/{cid} + /book"}
    try:
        from polymarket_apis import PolymarketReadOnlyClobClient
        c = PolymarketReadOnlyClobClient()
        t = time.time()
        # Find an active market via gamma first
        from polymarket_apis import PolymarketGammaClient
        g = PolymarketGammaClient()
        markets = await asyncio.to_thread(g.get_markets, closed=False, active=True, limit=5)
        if not markets:
            out["error"] = "no active markets returned by gamma"
            return out
        sample = markets[0]
        cid = sample.condition_id if hasattr(sample, "condition_id") else sample.get("conditionId")
        out["test_market_cid"] = cid

        market = await asyncio.to_thread(c.get_market, cid)
        if hasattr(market, "tokens"):
            tokens = market.tokens
        elif isinstance(market, dict):
            tokens = market.get("tokens", [])
        else:
            tokens = []
        out["n_tokens"] = len(tokens) if tokens else 0
        if tokens:
            tok = tokens[0]
            tid = tok.token_id if hasattr(tok, "token_id") else tok.get("token_id")
            book = await asyncio.to_thread(c.get_order_book, tid)
            out["book_method_works"] = True
            if hasattr(book, "asks"):
                out["n_asks"] = len(book.asks)
                out["typed_book"] = True
            elif isinstance(book, dict):
                out["n_asks"] = len(book.get("asks", []))
                out["typed_book"] = False
        out["elapsed_s"] = round(time.time()-t, 2)
    except Exception as e:
        out["error"] = repr(e)
        out["traceback"] = traceback.format_exc()
    return out


async def amain():
    DATA_DIR.mkdir(exist_ok=True)
    print("[1/2] Eval gamma /markets...")
    gamma = await eval_gamma()
    print(json.dumps(gamma, indent=2, default=str))

    print()
    print("[2/2] Eval clob /markets + /book...")
    clob = await eval_clob_market_book()
    print(json.dumps(clob, indent=2, default=str))

    verdict = {
        "gamma_works": "error" not in gamma and gamma.get("n_returned", 0) > 0,
        "clob_market_works": "error" not in clob,
        "typed_responses": gamma.get("typed", False),
    }

    recommendation = []
    if verdict["gamma_works"] and verdict["typed_responses"]:
        recommendation.append("USE polymarket-apis for gamma metadata fetches in e12/detector.py")
    if verdict["clob_market_works"]:
        recommendation.append("USE polymarket-apis for clob /markets and /book in e12/detector.py")
    if not (verdict["gamma_works"] or verdict["clob_market_works"]):
        recommendation.append("KEEP hand-rolled aiohttp — lib has issues")

    out = {
        "probed_at": datetime.now(timezone.utc).isoformat(),
        "library_version": __import__("polymarket_apis").__version__,
        "gamma": gamma,
        "clob": clob,
        "verdict": verdict,
        "recommendation": recommendation,
    }
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str))
    print()
    print("=" * 60)
    print(json.dumps({"verdict": verdict, "recommendation": recommendation}, indent=2))


def main():
    asyncio.run(amain())


if __name__ == "__main__":
    main()
