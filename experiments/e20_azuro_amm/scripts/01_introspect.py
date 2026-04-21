"""Introspect Azuro V3 subgraph schema.

Dumps the root query fields + Condition/Game/Outcome/Bet entity fields so
we know exactly what to pull.
"""
import json
import urllib.request

URL = "https://thegraph.azuro.org/subgraphs/name/azuro-protocol/azuro-api-polygon-v3"


def query(q: str) -> dict:
    data = json.dumps({"query": q}).encode("utf-8")
    req = urllib.request.Request(URL, data=data,
                                  headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


ROOT = """
{
  __schema {
    queryType {
      fields {
        name
        type { name kind ofType { name kind ofType { name kind } } }
      }
    }
  }
}
"""


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


def query_with_vars(q: str, variables: dict) -> dict:
    data = json.dumps({"query": q, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(URL, data=data,
                                  headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def describe(tname: str) -> list[dict]:
    out = query_with_vars(TYPE, {"name": tname})
    t = out.get("data", {}).get("__type")
    if not t:
        return []
    return t.get("fields", []) or []


def shorten(f):
    t = f["type"]
    while t.get("ofType"):
        inner = t["ofType"]
        if inner.get("name"):
            return inner["name"]
        t = inner
    return t.get("name") or "?"


def main():
    out = {}
    root = query(ROOT)
    root_fields = root["data"]["__schema"]["queryType"]["fields"]
    out["root_fields"] = sorted([f["name"] for f in root_fields])
    print(f"root fields: {len(root_fields)}")
    for f in root_fields[:80]:
        print(f"  {f['name']}")

    # Describe interesting types
    for tname in ["Condition", "Game", "Outcome", "Bet", "Sport", "League", "Country",
                  "LiquidityPool", "Odd", "ConditionOutcome"]:
        fields = describe(tname)
        if fields:
            print(f"\n--- {tname} ({len(fields)} fields) ---")
            for f in fields:
                print(f"  {f['name']}: {shorten(f)}")
            out[tname] = [{"name": f["name"], "type": shorten(f)} for f in fields]
        else:
            print(f"\n--- {tname}: NOT FOUND ---")
            out[tname] = None

    with open("/Users/elliotsturzaker/dev/event-impact-mvp/experiments/e20_azuro_amm/data/01_schema.json", "w") as f:
        json.dump(out, f, indent=2)


if __name__ == "__main__":
    main()
