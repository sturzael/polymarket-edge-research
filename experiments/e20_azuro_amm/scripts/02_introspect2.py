"""Dig into ConditionLog + Selection + v3Selection entities to find
the best historical-price signal."""
import json
import urllib.request

URL = "https://thegraph.azuro.org/subgraphs/name/azuro-protocol/azuro-api-polygon-v3"

TYPE = """
query TypeFields($name: String!) {
  __type(name: $name) {
    name
    fields {
      name
      type { name kind ofType { name kind ofType { name kind ofType { name kind } } } }
    }
  }
}
"""
def q(query, variables=None):
    data = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    req = urllib.request.Request(URL, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def short(f):
    t = f["type"]
    while t.get("ofType"):
        inner = t["ofType"]
        if inner.get("name"):
            return inner["name"]
        t = inner
    return t.get("name") or "?"


out = {}
for tname in ["ConditionLog", "Selection", "LiveSelection", "LiveCondition",
              "V3Condition", "V3Outcome", "V3Selection", "V3Bet",
              "ConditionStatus", "OutcomeResult", "GameStatus",
              "Participant", "Freebet", "Cashout"]:
    r = q(TYPE, {"name": tname})
    t = r.get("data", {}).get("__type")
    if not t or not t.get("fields"):
        # enum values?
        r2 = q("""query($n:String!){__type(name:$n){enumValues{name}}}""", {"name": tname})
        tt = r2.get("data", {}).get("__type")
        if tt and tt.get("enumValues"):
            ev = [e["name"] for e in tt["enumValues"]]
            print(f"--- {tname} (enum) --- {ev}")
            out[tname] = {"enum": ev}
            continue
        print(f"--- {tname}: not found ---")
        out[tname] = None
        continue
    print(f"\n--- {tname} ({len(t['fields'])} fields) ---")
    for f in t["fields"]:
        print(f"  {f['name']}: {short(f)}")
    out[tname] = [{"name": f["name"], "type": short(f)} for f in t["fields"]]

with open("/Users/elliotsturzaker/dev/event-impact-mvp/experiments/e20_azuro_amm/data/02_schema_detail.json", "w") as f:
    json.dump(out, f, indent=2)
