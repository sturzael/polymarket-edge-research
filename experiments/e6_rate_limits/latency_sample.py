"""Conservative rate-limit/latency sampling.

Sequential (not parallel) requests at normal rates, measuring response latency
to establish a baseline and observe any throttling signals passively.
No bursts. Equivalent load to a single user browsing.
"""
from __future__ import annotations

import asyncio
import json
import statistics
import time
from pathlib import Path

import aiohttp

TARGETS = [
    ("gamma-api",        "https://gamma-api.polymarket.com/markets",      {"limit": "1"}),
    ("clob-markets",     "https://clob.polymarket.com/markets",           {}),
    ("clob-by-id",
     "https://clob.polymarket.com/markets/0x04bd20bcb7818c24250e95bfd1a11d98a1a4b2c90797a2bd09bb46a0bf0f7ab0",
     {}),
    ("data-api-trades",  "https://data-api.polymarket.com/trades",        {"limit": "1"}),
]

N_SAMPLES = 10
INTERVAL_S = 1.0


async def sample(session: aiohttp.ClientSession, name: str, url: str, params: dict) -> dict:
    latencies: list[float] = []
    statuses: dict[str, int] = {}
    for i in range(N_SAMPLES):
        t0 = time.monotonic()
        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as r:
                await r.read()
                dt_ms = (time.monotonic() - t0) * 1000
                statuses[str(r.status)] = statuses.get(str(r.status), 0) + 1
                if r.status == 200:
                    latencies.append(dt_ms)
        except Exception as e:
            statuses["ERR"] = statuses.get("ERR", 0) + 1
        await asyncio.sleep(INTERVAL_S)
    return {
        "target": name,
        "samples": N_SAMPLES,
        "interval_s": INTERVAL_S,
        "statuses": statuses,
        "latency_ms_mean": round(statistics.mean(latencies), 1) if latencies else None,
        "latency_ms_median": round(statistics.median(latencies), 1) if latencies else None,
        "latency_ms_p90": round(sorted(latencies)[int(len(latencies)*0.9)-1], 1) if len(latencies) >= 5 else None,
    }


async def main() -> None:
    results: list[dict] = []
    async with aiohttp.ClientSession() as session:
        for name, url, params in TARGETS:
            r = await sample(session, name, url, params)
            results.append(r)
            print(f"{r['target']:20s}  {r['statuses']}  mean={r['latency_ms_mean']}ms  p90={r['latency_ms_p90']}ms")
    (Path(__file__).parent / "latency_results.json").write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
