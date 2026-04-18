"""Re-run Deribit option-chain snapshot for e2.

Usage: uv run python experiments/e2_deribit_iv/snapshot.py
"""
from __future__ import annotations

import asyncio
import json
import time
from collections import Counter
from pathlib import Path

import aiohttp

OUT_DIR = Path(__file__).parent


async def main() -> None:
    ts = int(time.time())
    async with aiohttp.ClientSession() as s:
        for ccy in ("BTC", "ETH"):
            url = "https://www.deribit.com/api/v2/public/get_book_summary_by_currency"
            async with s.get(url, params={"currency": ccy, "kind": "option"}) as r:
                data = await r.json()
            path = OUT_DIR / f"{ccy.lower()}_book_summary_{ts}.json"
            path.write_text(json.dumps(data, indent=2))
            result = data.get("result", [])
            expiries: Counter[str] = Counter()
            for c in result:
                parts = c.get("instrument_name", "").split("-")
                if len(parts) >= 2:
                    expiries[parts[1]] += 1
            print(f"{ccy}: {len(result)} options  top expiries: {expiries.most_common(6)}")
            print(f"  -> {path}")


if __name__ == "__main__":
    asyncio.run(main())
