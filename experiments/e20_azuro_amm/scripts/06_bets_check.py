"""Check if bets/selections are queryable at all on the azuro-api
subgraph, or if we need a different (bets) subgraph."""
import json, urllib.request

URL = "https://thegraph.azuro.org/subgraphs/name/azuro-protocol/azuro-api-polygon-v3"

def q(query):
    req = urllib.request.Request(URL, data=json.dumps({"query": query}).encode(),
                                  headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

# total bets count in this subgraph
print("=== does azuro-api subgraph index bets? ===")
r = q("{ bets(first: 5) { id odds createdBlockTimestamp amount bettor } }")
print(json.dumps(r, indent=2)[:500])

print("\n=== selections? ===")
r = q("{ selections(first: 5) { id odds bet { createdBlockTimestamp } outcome { outcomeId } } }")
print(json.dumps(r, indent=2)[:500])

# try v3Bet
print("\n=== v3Bets? ===")
r = q("{ v3Bets(first: 5) { id } }")
print(json.dumps(r, indent=2)[:500])

# Recent bets?
print("\n=== recent bets ===")
r = q("{ bets(first: 5, orderBy: createdBlockTimestamp, orderDirection: desc) { id odds amount createdBlockTimestamp _conditionIds } }")
print(json.dumps(r, indent=2)[:1000])
