"""Probe Baozi.bet market universe via Solana JSON-RPC.

Baozi has NO REST API. All market state lives in on-chain accounts owned by program
`FWyTPzm5cfJwRKzfkscxozatSxF6Qu78JQovQUwKPruJ` (V4.7.6). The Baozi MCP server is just
a thin wrapper over `connection.getProgramAccounts(PROGRAM_ID, ...)` with a memcmp
filter on the first 8 bytes of each account (the Anchor discriminator).

This script:
  1. Queries mainnet-beta for all MARKET accounts.
  2. Decodes each into {market_id, question, yes_pool_sol, no_pool_sol, status,
     winning_outcome, closing_time, resolution_time, ...}.
  3. Writes a parquet with the full universe.
  4. Prints counts by status + pool-size distribution.

Usage:
    uv run python scripts/probe_baozi.py \\
        --rpc https://api.mainnet-beta.solana.com \\
        --out data/baozi_markets.parquet

If you hit rate limits on the public RPC, point `--rpc` at a Helius / QuickNode /
Triton endpoint. The filtered `getProgramAccounts` is usually allowed by public
endpoints but can return 403/429 under load.
"""
from __future__ import annotations

import argparse
import base64
import json
import struct
import sys
import time
from pathlib import Path

import httpx
import pandas as pd

try:
    import base58  # pip install base58
except ImportError:
    print("pip install base58", file=sys.stderr)
    sys.exit(1)

PROGRAM_ID = "FWyTPzm5cfJwRKzfkscxozatSxF6Qu78JQovQUwKPruJ"

# From @baozi.bet/mcp-server src/config.ts DISCRIMINATORS
DISC_MARKET = bytes([219, 190, 213, 55, 0, 227, 198, 154])
DISC_RACE = bytes([235, 196, 111, 75, 230, 113, 118, 238])
DISC_USER_POSITION = bytes([251, 248, 209, 245, 83, 234, 17, 27])
DISC_GLOBAL_CONFIG = bytes([149, 8, 156, 202, 160, 252, 176, 217])

# Status enum (inferred from MARKET_STATUS_NAMES in config.ts):
#   0 Active, 1 Closed, 2 Resolved, 3 Cancelled
STATUS_NAMES = {0: "Active", 1: "Closed", 2: "Resolved", 3: "Cancelled"}

# Layer enum:  0 Lab, 1 Official, 2 Private (guess — verify in config.ts)
LAYER_NAMES = {0: "Lab", 1: "Official", 2: "Private"}


def rpc(client: httpx.Client, url: str, method: str, params: list) -> dict:
    r = client.post(
        url,
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        headers={"Content-Type": "application/json"},
        timeout=60,
    )
    r.raise_for_status()
    body = r.json()
    if "error" in body:
        raise RuntimeError(f"RPC error: {body['error']}")
    return body["result"]


def get_program_accounts(client: httpx.Client, url: str,
                          discriminator: bytes) -> list[dict]:
    filt = {
        "memcmp": {"offset": 0, "bytes": base58.b58encode(discriminator).decode()}
    }
    result = rpc(client, url, "getProgramAccounts", [
        PROGRAM_ID,
        {"filters": [filt], "encoding": "base64"},
    ])
    return result or []


def read_string(data: bytes, offset: int) -> tuple[str, int]:
    """Borsh string: u32 length + utf-8 bytes."""
    length = struct.unpack_from("<I", data, offset)[0]
    offset += 4
    s = data[offset:offset + length].decode("utf-8", errors="replace")
    return s, offset + length


def decode_market(raw: bytes, pubkey: str) -> dict | None:
    """Decode a Baozi Market account.

    Layout (V4.7.6, inferred from MCP handlers/markets.ts and the generic Anchor layout
    documented in the MCP DISCRIMINATORS + field names). Exact offsets require the IDL,
    so some fields may need adjustment after a ground-truth pass.

    Best-effort: read discriminator, then u64 market_id, then Borsh-style question,
    then pool amounts (u64 lamports), status (u8), winning_outcome (Option<u8>),
    closing_time/resolution_time (i64), fee bps (u16), currency (u8), layer (u8),
    access_gate (u8), creator (Pubkey, 32 bytes).

    If a field doesn't parse, set to None and continue.
    """
    if len(raw) < 8 or raw[:8] != DISC_MARKET:
        return None
    out = {"pubkey": pubkey, "raw_len": len(raw)}
    try:
        off = 8
        market_id = struct.unpack_from("<Q", raw, off)[0]; off += 8
        question, off = read_string(raw, off)
        # From here, the struct order varies by program version. We surface a best-
        # effort decode; if totals look wrong, dump raw hex and cross-check with IDL.
        # Tentative next fields (per handlers/markets.ts mentions):
        yes_pool = struct.unpack_from("<Q", raw, off)[0]; off += 8
        no_pool = struct.unpack_from("<Q", raw, off)[0]; off += 8
        total_pool = yes_pool + no_pool
        closing_ts = struct.unpack_from("<q", raw, off)[0]; off += 8
        resolution_ts = struct.unpack_from("<q", raw, off)[0]; off += 8
        status_code = raw[off]; off += 1
        # winning_outcome: Option<u8>  (1 byte tag + 1 byte value if Some)
        winning = None
        if raw[off] == 1:
            winning = raw[off + 1]
            off += 2
        else:
            off += 1
        out.update({
            "market_id": market_id,
            "question": question[:280],
            "yes_pool_lamports": yes_pool,
            "no_pool_lamports": no_pool,
            "yes_pool_sol": yes_pool / 1e9,
            "no_pool_sol": no_pool / 1e9,
            "total_pool_sol": total_pool / 1e9,
            "closing_ts": closing_ts,
            "resolution_ts": resolution_ts,
            "status_code": status_code,
            "status": STATUS_NAMES.get(status_code, f"Unknown({status_code})"),
            "winning_outcome": winning,
        })
        if total_pool > 0:
            out["implied_yes_close"] = yes_pool / total_pool
        else:
            out["implied_yes_close"] = None
    except Exception as e:
        out["decode_error"] = str(e)
    return out


def categorize(question: str) -> str:
    q = question.lower()
    sports_keywords = [
        "nba", "nfl", "mlb", "nhl", "soccer", "football", "basketball",
        "baseball", "hockey", "tennis", "golf", "ufc", "boxing", "cricket",
        "champions league", "premier league", "f1", "formula 1", "olympics",
        "world cup", "super bowl", "playoff", "tournament", "vs.", " vs ",
    ]
    crypto_keywords = [
        "btc", "bitcoin", "eth", "ethereum", "sol ", "solana", "$sol", "$btc",
        "$eth", "memecoin", "token", "coin ", "dogecoin", "shib", "price of",
    ]
    politics_keywords = [
        "trump", "biden", "president", "election", "senate", "congress",
        "vote", "parliament", "prime minister", "putin", "ukraine", "israel",
    ]
    if any(k in q for k in sports_keywords):
        return "sports"
    if any(k in q for k in crypto_keywords):
        return "crypto"
    if any(k in q for k in politics_keywords):
        return "politics"
    return "other"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rpc", default="https://api.mainnet-beta.solana.com")
    ap.add_argument("--out", default="data/baozi_markets.parquet")
    ap.add_argument("--also-race", action="store_true",
                    help="Also pull race markets (different discriminator).")
    args = ap.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    with httpx.Client() as c:
        print(f"[{time.time()-t0:.1f}s] getProgramAccounts MARKET ...", flush=True)
        market_accts = get_program_accounts(c, args.rpc, DISC_MARKET)
        print(f"  -> {len(market_accts):,} market accounts")

        rows = []
        for a in market_accts:
            raw_b64 = a["account"]["data"][0]
            raw = base64.b64decode(raw_b64)
            dec = decode_market(raw, a["pubkey"])
            if dec:
                dec["market_type"] = "boolean"
                rows.append(dec)

        if args.also_race:
            print(f"[{time.time()-t0:.1f}s] getProgramAccounts RACE ...", flush=True)
            race_accts = get_program_accounts(c, args.rpc, DISC_RACE)
            print(f"  -> {len(race_accts):,} race accounts")
            # Race decoding is different (2-10 outcomes) — stub only.
            for a in race_accts:
                rows.append({
                    "pubkey": a["pubkey"],
                    "market_type": "race",
                    "raw_len": len(base64.b64decode(a["account"]["data"][0])),
                })

    df = pd.DataFrame(rows)
    df["category"] = df.get("question", pd.Series([""] * len(df))).fillna("").apply(categorize)
    df.to_parquet(out_path, index=False)
    print(f"\nwrote {out_path} — {len(df):,} rows")

    # Summaries
    if "status" in df:
        print("\nStatus breakdown:")
        print(df["status"].value_counts().to_string())
    if "total_pool_sol" in df:
        p = df["total_pool_sol"].dropna()
        if len(p):
            print(f"\nPool size (SOL): n={len(p):,}  median={p.median():.3f}  "
                  f"p75={p.quantile(0.75):.3f}  p95={p.quantile(0.95):.3f}  "
                  f"max={p.max():.3f}  sum={p.sum():.1f}")
    if "category" in df:
        print("\nCategory (keyword-inferred):")
        print(df["category"].value_counts().to_string())

    if "status" in df and "resolution_ts" in df:
        resolved = df[df["status"].isin(["Resolved", "Closed"])]
        print(f"\nResolved/closed markets: {len(resolved):,}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
