"""Rate-limit discovery — send escalating parallel request bursts to
  gamma-api, CLOB, and data-api, watching for 429s and Retry-After headers.

Kept intentionally mild to avoid triggering a ban while the main probe is running.
"""
from __future__ import annotations

import asyncio
import json
import statistics
import time
from pathlib import Path

import aiohttp

TARGETS = [
    ("gamma-api",
     "https://gamma-api.polymarket.com/markets",
     {"limit": "1"}),
    ("clob-markets",
     "https://clob.polymarket.com/markets",
     {}),
    ("clob-market-by-id",
     "https://clob.polymarket.com/markets/0x04bd20bcb7818c24250e95bfd1a11d98a1a4b2c90797a2bd09bb46a0bf0f7ab0",
     {}),
    ("data-api-trades",
     "https://data-api.polymarket.com/trades",
     {"limit": "1"}),
]

SCHEDULE = [
    {"reqs": 30, "conc": 5},
    {"reqs": 50, "conc": 10},
    {"reqs": 100, "conc": 20},
]


async def one_request(session: aiohttp.ClientSession, url: str, params: dict) -> dict:
    t0 = time.monotonic()
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as r:
            # Try to read headers of interest
            ra = r.headers.get("Retry-After") or r.headers.get("retry-after")
            await r.read()
            return {"status": r.status, "latency_ms": (time.monotonic()-t0)*1000, "retry_after": ra}
    except Exception as e:
        return {"status": "ERR", "latency_ms": (time.monotonic()-t0)*1000, "err": str(e)[:100]}


async def burst(session, url, params, reqs: int, conc: int) -> dict:
    sem = asyncio.Semaphore(conc)
    results: list[dict] = []

    async def worker():
        async with sem:
            r = await one_request(session, url, params)
            results.append(r)

    t0 = time.monotonic()
    await asyncio.gather(*[worker() for _ in range(reqs)])
    elapsed = time.monotonic() - t0
    statuses: dict[str | int, int] = {}
    for r in results:
        s = r["status"]
        statuses[s] = statuses.get(s, 0) + 1
    latencies_ok = [r["latency_ms"] for r in results if r["status"] == 200]
    sample_retry_after = next((r.get("retry_after") for r in results if r.get("retry_after")), None)
    return {
        "reqs": reqs, "concurrency": conc, "elapsed_s": round(elapsed, 2),
        "req_per_s": round(reqs/elapsed, 2),
        "statuses": statuses,
        "latency_ok_mean_ms": round(statistics.mean(latencies_ok), 1) if latencies_ok else None,
        "latency_ok_p95_ms": round(sorted(latencies_ok)[int(len(latencies_ok)*0.95)-1], 1) if len(latencies_ok) >= 20 else None,
        "retry_after_seen": sample_retry_after,
    }


async def main() -> None:
    results: list[dict] = []
    async with aiohttp.ClientSession() as session:
        for name, url, params in TARGETS:
            print(f"\n=== {name} ===")
            for step in SCHEDULE:
                # If a prior step hit 429, skip remaining escalation
                prev = results[-1] if results and results[-1]["target"] == name else None
                if prev and 429 in prev.get("statuses", {}):
                    print(f"  skipping (prior 429 seen on {name})")
                    break
                res = await burst(session, url, params, step["reqs"], step["conc"])
                entry = {"target": name, **res}
                results.append(entry)
                print(f"  reqs={res['reqs']:3d} conc={res['concurrency']:2d}  "
                      f"rate={res['req_per_s']:6.1f}/s  {res['statuses']}  "
                      f"p95={res['latency_ok_p95_ms']}ms  retry_after={res['retry_after_seen']}")
                # Conservative pause between bursts
                await asyncio.sleep(5)
    out_path = Path(__file__).parent / "results.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nresults -> {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
