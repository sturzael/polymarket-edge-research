"""Validate whether Outcome.currentOdds on a Resolved condition is the
final AMM quote (last trade/update before resolution), or something else.

For 5 randomly sampled resolved conditions, fetch all Selections (bets)
on their outcomes ordered by block timestamp. Compare:
  - currentOdds (from conditions file)
  - odds on earliest bet vs latest bet
  - difference between early bet odds and currentOdds (our "T-7d" proxy is
    the earliest bet close to T-7d)
"""
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

URL = "https://thegraph.azuro.org/subgraphs/name/azuro-protocol/azuro-api-polygon-v3"

def q(query, variables=None):
    data = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    req = urllib.request.Request(URL, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8"))


# Pick a few conditions from the pulled polygon jsonl
sample = []
with open("/Users/elliotsturzaker/dev/event-impact-mvp/experiments/e20_azuro_amm/data/04_conditions_polygon.jsonl") as f:
    for i, line in enumerate(f):
        if i >= 50 and i % 10000 == 0:  # pick from different times
            r = json.loads(line)
            if r.get("outcomes") and len(r["outcomes"]) in (2, 3):
                sample.append(r)
                if len(sample) >= 6:
                    break

print(f"sampled {len(sample)} conditions for validation\n")

# For each sampled condition, fetch selections for its outcome IDs
QS = """
query($outcomeId: String!, $conditionEntity: String!) {
  selections(first: 30, orderBy: bet__createdBlockTimestamp, orderDirection: asc,
             where: { outcome: $outcomeId }) {
    id
    odds
    rawOdds
    bet {
      id
      amount
      createdBlockTimestamp
      _conditions { id }
    }
  }
}
"""

out_rows = []
for cond in sample:
    print(f"\n=== condition {cond['id'][:24]}... ===")
    print(f"  sport: {cond['game']['sport']['name']}  league: {cond['game']['league']['name']}")
    created = int(cond["createdBlockTimestamp"] or 0)
    resolved = int(cond["resolvedBlockTimestamp"] or 0)
    game_start = int(cond.get("game", {}).get("startsAt") or 0)
    print(f"  created:  {datetime.fromtimestamp(created, tz=timezone.utc).isoformat()[:19]}")
    print(f"  starts:   {datetime.fromtimestamp(game_start, tz=timezone.utc).isoformat()[:19] if game_start else '-'}")
    print(f"  resolved: {datetime.fromtimestamp(resolved, tz=timezone.utc).isoformat()[:19]}")
    margin = int(cond.get("margin") or 0)
    print(f"  margin (raw): {margin}  (overround encoded here)")
    print(f"  wonOutcomeIds: {cond['wonOutcomeIds']}")
    print(f"  outcomes (currentOdds at subgraph's last-update for this condition):")
    for o in cond["outcomes"]:
        print(f"    outcome={o['outcomeId']}  currentOdds={float(o['currentOdds']):.4f}  result={o['result']}  fund={o['fund']}")

    # For each outcome fetch bets
    for o in cond["outcomes"]:
        outcome_entity = o["id"]
        res = q(QS, {"outcomeId": outcome_entity, "conditionEntity": cond["id"]})
        sels = (res.get("data") or {}).get("selections", []) or []
        if not sels:
            print(f"    outcome={o['outcomeId']}: NO bets found")
            continue
        # filter to only bets on this condition
        sels = [s for s in sels
                if cond["id"] in [c["id"] for c in (s.get("bet", {}) or {}).get("_conditions", [])]]
        if not sels:
            print(f"    outcome={o['outcomeId']}: no bets on this condition")
            continue
        first = sels[0]
        last = sels[-1]
        first_ts = int(first["bet"]["createdBlockTimestamp"])
        last_ts = int(last["bet"]["createdBlockTimestamp"])
        print(f"    outcome={o['outcomeId']}: n_bets≥{len(sels)}  "
              f"first_bet_odds={float(first['odds']):.4f}@{datetime.fromtimestamp(first_ts, tz=timezone.utc).isoformat()[:16]}  "
              f"last_bet_odds={float(last['odds']):.4f}@{datetime.fromtimestamp(last_ts, tz=timezone.utc).isoformat()[:16]}  "
              f"vs currentOdds={float(o['currentOdds']):.4f}")
        out_rows.append({
            "condition_id": cond["id"],
            "outcome_id": o["outcomeId"],
            "sport": cond["game"]["sport"]["name"],
            "n_bets_sampled": len(sels),
            "current_odds": float(o["currentOdds"]),
            "first_bet_odds": float(first["odds"]),
            "last_bet_odds": float(last["odds"]),
            "first_bet_ts": first_ts,
            "last_bet_ts": last_ts,
            "resolved_ts": resolved,
            "game_start_ts": game_start,
            "created_ts": created,
            "result": o["result"],
            "is_winner": o["outcomeId"] in cond["wonOutcomeIds"],
        })

with open("/Users/elliotsturzaker/dev/event-impact-mvp/experiments/e20_azuro_amm/data/05_price_validation.json", "w") as f:
    json.dump(out_rows, f, indent=2)
print(f"\nwrote {len(out_rows)} rows to 05_price_validation.json")
