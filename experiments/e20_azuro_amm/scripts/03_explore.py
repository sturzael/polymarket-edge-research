"""Exploratory: how many resolved conditions exist on Polygon/Gnosis,
what's the date range, time from createdBlockTimestamp→resolvedBlockTimestamp,
how many bets per condition, what do odds look like?"""
import json
import urllib.request
from datetime import datetime, timezone

URLS = {
    "polygon": "https://thegraph.azuro.org/subgraphs/name/azuro-protocol/azuro-api-polygon-v3",
    "gnosis":  "https://thegraph.azuro.org/subgraphs/name/azuro-protocol/azuro-api-gnosis-v3",
    "base":    "https://thegraph.azuro.org/subgraphs/name/azuro-protocol/azuro-api-base-v3",
    "chiliz":  "https://thegraph.azuro.org/subgraphs/name/azuro-protocol/azuro-api-chiliz-v3",
}


def q(url, query, variables=None):
    data = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8"))


# Count resolved conditions; get earliest + latest
COUNT_Q = """
{
  resolvedRecent: conditions(first: 5, orderBy: resolvedBlockTimestamp, orderDirection: desc,
    where: { status: Resolved }) {
    id
    status
    createdBlockTimestamp
    resolvedBlockTimestamp
    internalStartsAt
    outcomesIds
    wonOutcomeIds
    game { sport { name } league { name } title startsAt }
    outcomes { outcomeId currentOdds fund title result }
  }
  resolvedOldest: conditions(first: 5, orderBy: resolvedBlockTimestamp, orderDirection: asc,
    where: { status: Resolved }) {
    id
    createdBlockTimestamp
    resolvedBlockTimestamp
    internalStartsAt
    game { sport { name } title startsAt }
  }
  totalCount: conditions(where: { status: Resolved }, first: 1000,
    orderBy: resolvedBlockTimestamp, orderDirection: desc) {
    id
  }
  sports: sports(first: 50) { name slug }
}
"""

for chain, url in URLS.items():
    print(f"\n========== {chain.upper()} ==========")
    try:
        r = q(url, COUNT_Q)
    except Exception as e:
        print(f"  ERROR: {e}")
        continue
    if "errors" in r:
        print(f"  errors: {r['errors'][:2]}")
        continue
    data = r.get("data", {})
    print(f"sports found: {len(data.get('sports', []))}")
    for s in data.get("sports", [])[:30]:
        print(f"  {s['slug']:<30}  {s['name']}")
    print(f"\nrecent resolved conditions (last 5):")
    for c in data.get("resolvedRecent", []):
        ts_created = int(c["createdBlockTimestamp"] or 0)
        ts_resolved = int(c["resolvedBlockTimestamp"] or 0)
        ts_starts = int(c.get("internalStartsAt") or 0)
        g = c.get("game") or {}
        sport = (g.get("sport") or {}).get("name", "?")
        print(f"  id={c['id'][:12]}  sport={sport}")
        print(f"    created {datetime.fromtimestamp(ts_created, tz=timezone.utc).isoformat()[:19] if ts_created else '-'}")
        print(f"    starts  {datetime.fromtimestamp(ts_starts, tz=timezone.utc).isoformat()[:19] if ts_starts else '-'}")
        print(f"    resolved{datetime.fromtimestamp(ts_resolved, tz=timezone.utc).isoformat()[:19] if ts_resolved else '-'}")
        print(f"    duration created→resolved: {(ts_resolved - ts_created)/86400:.2f} days")
        print(f"    outcomes: {[o.get('title') for o in c.get('outcomes',[])]}")
        print(f"    won: {c.get('wonOutcomeIds')}")
        print(f"    odds: {[float(o.get('currentOdds') or 0) for o in c.get('outcomes',[])]}")
    print(f"\noldest resolved conditions (first 3):")
    for c in data.get("resolvedOldest", [])[:3]:
        ts = int(c["resolvedBlockTimestamp"] or 0)
        print(f"  resolved {datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()[:19] if ts else '-'}  id={c['id'][:16]}")
    # totalCount hits 1000 cap — so if we get 1000 there are ≥1000
    tc = data.get("totalCount") or []
    print(f"\nresolved conditions in first 1000-window (cap=1000): {len(tc)}")
