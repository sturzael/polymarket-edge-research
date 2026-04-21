"""Paginate all resolved conditions from Azuro V3 subgraphs.

Strategy: use timestamp-cursor pagination (order by resolvedBlockTimestamp desc,
use `resolvedBlockTimestamp_lt: <prev_min>` to page). This beats skip for deep
pagination on TheGraph.

For each condition pulls:
  id, conditionId, coreAddress, createdBlockTimestamp, resolvedBlockTimestamp,
  status, wonOutcomeIds, margin, game { sport { name }, league { name } },
  outcomes[] { outcomeId, currentOdds, fund, result, title }

Writes one JSONL file per chain: data/04_conditions_<chain>.jsonl
"""
import json
import time
import urllib.request
import urllib.error
from pathlib import Path

URLS = {
    "polygon": "https://thegraph.azuro.org/subgraphs/name/azuro-protocol/azuro-api-polygon-v3",
    "gnosis":  "https://thegraph.azuro.org/subgraphs/name/azuro-protocol/azuro-api-gnosis-v3",
    "base":    "https://thegraph.azuro.org/subgraphs/name/azuro-protocol/azuro-api-base-v3",
    "chiliz":  "https://thegraph.azuro.org/subgraphs/name/azuro-protocol/azuro-api-chiliz-v3",
}

OUT_DIR = Path("/Users/elliotsturzaker/dev/event-impact-mvp/experiments/e20_azuro_amm/data")
OUT_DIR.mkdir(parents=True, exist_ok=True)

PAGE_Q = """
query Page($beforeTs: BigInt!) {
  conditions(first: 1000,
             orderBy: resolvedBlockTimestamp,
             orderDirection: desc,
             where: { status: Resolved,
                      resolvedBlockTimestamp_lt: $beforeTs }) {
    id
    conditionId
    coreAddress
    createdBlockTimestamp
    resolvedBlockTimestamp
    internalStartsAt
    status
    wonOutcomeIds
    margin
    _outcomesKey
    game {
      id
      gameId
      title
      startsAt
      sport { name slug }
      league { name slug }
    }
    outcomes {
      id
      outcomeId
      currentOdds
      fund
      result
      title
    }
  }
}
"""


def q(url, query, variables=None, retries=3):
    data = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data,
                                      headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                resp = json.loads(r.read().decode("utf-8"))
                if "errors" in resp:
                    err = str(resp["errors"])[:300]
                    if "timeout" in err.lower() and attempt < retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    return resp
                return resp
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise
    return resp


def pull_chain(chain: str, url: str) -> int:
    out_path = OUT_DIR / f"04_conditions_{chain}.jsonl"
    before_ts = str(10**12)  # far future
    total = 0
    t0 = time.time()
    with open(out_path, "w") as f:
        while True:
            r = q(url, PAGE_Q, {"beforeTs": before_ts})
            if "errors" in r:
                print(f"  [{chain}] GraphQL error at ts<{before_ts}: {r['errors'][:2]}")
                break
            rows = (r.get("data") or {}).get("conditions") or []
            if not rows:
                break
            for row in rows:
                f.write(json.dumps(row) + "\n")
            total += len(rows)
            # cursor
            min_ts = min(int(x["resolvedBlockTimestamp"] or 0) for x in rows if x.get("resolvedBlockTimestamp"))
            if min_ts <= 0:
                break
            rate = total / (time.time() - t0 + 1e-6)
            print(f"  [{chain}] page={len(rows):>4}  total={total:>6}  "
                  f"oldest={min_ts}  ({rate:.0f}/s)", flush=True)
            if min_ts >= int(before_ts):
                # Didn't advance — infinite loop guard
                print(f"  [{chain}] cursor stuck at {min_ts}, halting")
                break
            before_ts = str(min_ts)
            if len(rows) < 1000:
                break
    print(f"  [{chain}] DONE — {total:,} conditions → {out_path}")
    return total


def main():
    summary = {}
    for chain, url in URLS.items():
        print(f"\n=== pulling {chain} ===")
        try:
            n = pull_chain(chain, url)
            summary[chain] = n
        except Exception as e:
            print(f"  [{chain}] FAILED: {e}")
            summary[chain] = f"error: {e}"
    print("\n=== SUMMARY ===")
    for k, v in summary.items():
        print(f"  {k:<10} {v}")
    with open(OUT_DIR / "04_pull_summary.json", "w") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    main()
