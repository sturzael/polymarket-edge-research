"""Probe Azuro subgraph endpoints.

Tests connectivity + runs schema introspection to understand available entities.
"""
import json
import urllib.request
import urllib.error

ENDPOINTS = {
    # V3 (latest) per docs
    "polygon-v3": "https://thegraph.azuro.org/subgraphs/name/azuro-protocol/azuro-api-polygon-v3",
    "gnosis-v3":  "https://thegraph.azuro.org/subgraphs/name/azuro-protocol/azuro-api-gnosis-v3",
    # V2 fallback if V3 rejects
    "polygon-v2": "https://thegraph.azuro.org/subgraphs/name/azuro-protocol/azuro-api-polygon-v2",
    "gnosis-v2":  "https://thegraph.azuro.org/subgraphs/name/azuro-protocol/azuro-api-gnosis-v2",
    # Possible onchainfeed mirrors
    "polygon-ocf-v3": "https://thegraph.onchainfeed.org/subgraphs/name/azuro-protocol/azuro-api-polygon-v3",
    "gnosis-ocf-v3":  "https://thegraph.onchainfeed.org/subgraphs/name/azuro-protocol/azuro-api-gnosis-v3",
    "arbitrum-v3": "https://thegraph.azuro.org/subgraphs/name/azuro-protocol/azuro-api-arbitrum-one-v3",
    "base-v3": "https://thegraph.azuro.org/subgraphs/name/azuro-protocol/azuro-api-base-v3",
    "chiliz-v3": "https://thegraph.azuro.org/subgraphs/name/azuro-protocol/azuro-api-chiliz-v3",
}


def query(url: str, body: dict, timeout: int = 20) -> tuple[int, dict | str]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                  headers={"Content-Type": "application/json",
                                           "User-Agent": "azuro-probe/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")[:500]
    except Exception as e:
        return 0, f"ERROR: {type(e).__name__}: {e}"


def main():
    results = {}
    for name, url in ENDPOINTS.items():
        print(f"\n=== {name} ===")
        print(f"  url: {url}")
        status, body = query(url, {"query": "{ _meta { block { number hash } deployment hasIndexingErrors } }"})
        print(f"  status: {status}")
        if isinstance(body, dict):
            print(f"  body: {json.dumps(body)[:400]}")
        else:
            print(f"  body: {body[:400]}")
        results[name] = {"status": status, "response": body if isinstance(body, dict) else str(body)[:500]}

    with open("/Users/elliotsturzaker/dev/event-impact-mvp/experiments/e20_azuro_amm/data/00_endpoint_probe.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print("\nwrote 00_endpoint_probe.json")


if __name__ == "__main__":
    main()
