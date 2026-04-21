"""Pull bets on a random sample of resolved 2-outcome conditions and
measure FLB at earlier pre-game timestamps.

For a stratified sample of 2000 conditions with duration ≥ 3 days:
  - Query bets placed within ±12h of (game_start - 24h) and (game_start - 7d)
  - Compute implied probability from first/mean bet odds in that window,
    apply overround correction using the condition's `margin` proxy
  - Compare to close-time (currentOdds) price

Output: data/11_early_price_flb.json
"""
import csv
import json
import math
import random
import time
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

URL = "https://thegraph.azuro.org/subgraphs/name/azuro-protocol/azuro-api-polygon-v3"
DATA = Path("/Users/elliotsturzaker/dev/event-impact-mvp/experiments/e20_azuro_amm/data")
OUT_JSON = DATA / "11_early_price_flb.json"
OUT_ROWS = DATA / "11_bet_rows.csv"

random.seed(42)


def q(query, variables=None, retries=3):
    data = json.dumps({"query": query, "variables": variables or {}}).encode()
    for a in range(retries):
        try:
            req = urllib.request.Request(URL, data=data,
                                          headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except Exception:
            if a < retries - 1:
                time.sleep(1 + a); continue
            raise


# We need the string conditionId (BigInt) not the "0xcore_bigint" composite.
# bets._conditionIds uses BigInt form.

BETS_Q = """
query Bets($conditionIdStr: BigInt!, $tsLow: BigInt!, $tsHigh: BigInt!) {
  bets(first: 100,
       orderBy: createdBlockTimestamp,
       orderDirection: asc,
       where: {
         _conditionIds_contains: [$conditionIdStr],
         createdBlockTimestamp_gte: $tsLow,
         createdBlockTimestamp_lte: $tsHigh
       }) {
    id
    createdBlockTimestamp
    odds
    amount
    selections {
      odds
      _outcomeId
      outcome { outcomeId }
    }
    _conditionIds
  }
}
"""


def bucket_label(p):
    if p < 0 or p > 1: return None
    i = min(int(p * 20), 19)
    lo = i / 20.0; hi = (i + 1) / 20.0
    return f"{lo:.2f}-{hi:.2f}", lo + 0.025


def z_binomial(yes, n, mid):
    if n <= 0: return 0.0
    se = math.sqrt(mid * (1 - mid) / n)
    if se == 0: return 0.0
    return (yes / n - mid) / se


def bucketize(rows, key):
    b = defaultdict(lambda: {"n": 0, "yes": 0, "mid_sum": 0.0})
    for r in rows:
        p = r[key]
        if p is None: continue
        lm = bucket_label(p)
        if lm is None: continue
        lbl, mid = lm
        x = b[lbl]; x["n"] += 1; x["yes"] += r["is_yes"]; x["mid_sum"] += mid
    out = []
    for lbl in sorted(b):
        x = b[lbl]
        mid = x["mid_sum"] / x["n"] if x["n"] else 0
        yr = x["yes"] / x["n"] if x["n"] else 0
        out.append({
            "bucket": lbl, "n": x["n"],
            "mid": round(mid, 4), "yes": x["yes"],
            "yes_rate": round(yr, 4),
            "deviation": round(yr - mid, 4),
            "z": round(z_binomial(x["yes"], x["n"], mid), 2),
        })
    return out


# Step 1: build condition sample
# Need: 2-outcome, single-winner, duration >=3 days, game_start_ts known
candidates = []
print("building candidate list from clean close-rows...")
wins_per = defaultdict(int)
rows_by_cond = defaultdict(list)
with open(DATA / "07_close_rows.csv") as f:
    for r in csv.DictReader(f):
        wins_per[r["condition_id"]] += int(r["is_yes"])
        rows_by_cond[r["condition_id"]].append(r)

for cid, rows in rows_by_cond.items():
    if wins_per[cid] != 1: continue
    if len(rows) != 2: continue
    rr = rows[0]
    dur = float(rr["duration_days"])
    if dur < 3: continue
    if int(rr["game_start_ts"] or 0) == 0: continue
    candidates.append(rows)

print(f"candidate conditions: {len(candidates):,}")
sample = random.sample(candidates, min(1500, len(candidates)))
print(f"sampling {len(sample)} conditions for bet queries")

# Step 2: for each, query bets around (game_start - 24h) and (game_start - 7d)
rows_t24 = []
rows_t7 = []
rows_close = []
t0 = time.time()
hits_24h = 0
hits_7d = 0

for i, outcomes in enumerate(sample):
    r0 = outcomes[0]
    cond_entity = r0["condition_id"]
    # Extract condition BigInt from the "0xcore_<bigint>" composite id
    try:
        cond_big = cond_entity.split("_")[1]
    except Exception:
        continue
    game_start = int(r0["game_start_ts"])
    created = int(r0["created_ts"])
    # Window helpers
    WIN = 12 * 3600  # ±12h
    # Outcome id -> (odds, is_yes) for this condition
    outcome_info = {o["outcome_id"]: {"is_yes": int(o["is_yes"]),
                                       "close_odds": float(o["odds"])}
                    for o in outcomes}

    # Always record close prices (normalized)
    total_overround = sum(1.0 / x["close_odds"] for x in outcome_info.values())
    for oid, info in outcome_info.items():
        raw_p = 1.0 / info["close_odds"]
        norm_p = raw_p / total_overround
        rows_close.append({"cond": cond_entity, "outcome_id": oid,
                           "is_yes": info["is_yes"],
                           "norm_prob": norm_p,
                           "horizon": "close"})

    for horizon_name, target_ts in (("t-24h", game_start - 24*3600),
                                     ("t-7d",  game_start - 7*24*3600)):
        if target_ts < created:
            continue  # market didn't exist yet
        low = target_ts - WIN
        high = target_ts + WIN
        try:
            res = q(BETS_Q, {"conditionIdStr": cond_big,
                             "tsLow": str(low), "tsHigh": str(high)})
        except Exception:
            continue
        bets = (res.get("data") or {}).get("bets") or []
        if not bets:
            continue
        # Gather odds per outcomeId across these bets (first-seen)
        outcome_odds = defaultdict(list)
        for b in bets:
            for s in b.get("selections") or []:
                oid = s.get("_outcomeId") or (s.get("outcome") or {}).get("outcomeId")
                if not oid or oid not in outcome_info: continue
                try:
                    outcome_odds[oid].append(float(s["odds"]))
                except Exception:
                    continue
        if not outcome_odds:
            continue
        # For each outcome we need a price; use mean of observed odds
        # If only 1 outcome has bets, infer the other from (odds correspond to equal margin)
        present_ids = set(outcome_odds.keys())
        all_ids = set(outcome_info.keys())
        missing = all_ids - present_ids
        # Combine; if both outcomes have bets -> normal case. If only 1, skip (can't normalize).
        if len(present_ids) < 2:
            # Try margin assumption: use close overround as proxy
            if len(present_ids) != 1:
                continue
            only_oid = next(iter(present_ids))
            mean_odds_present = sum(outcome_odds[only_oid]) / len(outcome_odds[only_oid])
            raw_p_present = 1.0 / mean_odds_present
            # Use typical overround from close as proxy
            raw_p_other = total_overround - raw_p_present
            if raw_p_other <= 0 or raw_p_other >= 1:
                continue
            outcomes_probs = {only_oid: raw_p_present}
            for mid in missing:
                outcomes_probs[mid] = raw_p_other
            overr_now = total_overround
        else:
            mean_odds = {oid: sum(v) / len(v) for oid, v in outcome_odds.items()}
            raw_probs = {oid: 1.0 / v for oid, v in mean_odds.items()}
            overr_now = sum(raw_probs.values())
            if not (1.0 < overr_now <= 1.30):
                continue
            outcomes_probs = raw_probs
        # Normalize
        norm = {oid: p / overr_now for oid, p in outcomes_probs.items()}
        for oid, info in outcome_info.items():
            if oid not in norm: continue
            record = {"cond": cond_entity, "outcome_id": oid,
                      "is_yes": info["is_yes"],
                      "norm_prob": norm[oid],
                      "horizon": horizon_name}
            if horizon_name == "t-24h":
                rows_t24.append(record); hits_24h += 1
            else:
                rows_t7.append(record); hits_7d += 1
    if (i + 1) % 100 == 0:
        rate = (i + 1) / (time.time() - t0 + 1e-6)
        print(f"  [{i+1}/{len(sample)}]  t-24h={len(rows_t24)} t-7d={len(rows_t7)}  "
              f"({rate:.1f} cond/s)", flush=True)

print(f"\nhits_24h={len(rows_t24)}  hits_7d={len(rows_t7)}  close_rows={len(rows_close)}")

# Bucketize each horizon
out = {
    "n_sample": len(sample),
    "n_rows_close": len(rows_close),
    "n_rows_t24": len(rows_t24),
    "n_rows_t7d": len(rows_t7),
    "close": bucketize(rows_close, "norm_prob"),
    "t-24h": bucketize(rows_t24, "norm_prob"),
    "t-7d": bucketize(rows_t7, "norm_prob"),
}
OUT_JSON.write_text(json.dumps(out, indent=2))

# Also dump raw rows
with open(OUT_ROWS, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["cond", "outcome_id", "is_yes", "norm_prob", "horizon"])
    w.writeheader()
    for r in rows_close + rows_t24 + rows_t7:
        w.writerow(r)

print(f"wrote {OUT_JSON} and {OUT_ROWS}")
print("\n=== T-24h calibration (normalized) ===")
for b in out["t-24h"]:
    if b["n"] >= 10:
        star = "***" if abs(b["z"]) >= 2 else ""
        print(f"  {b['bucket']} n={b['n']:>5} mid={b['mid']:.3f} yes={b['yes_rate']:.3f} dev={b['deviation']:+.3f} z={b['z']:+.2f} {star}")
print("\n=== T-7d calibration (normalized) ===")
for b in out["t-7d"]:
    if b["n"] >= 10:
        star = "***" if abs(b["z"]) >= 2 else ""
        print(f"  {b['bucket']} n={b['n']:>5} mid={b['mid']:.3f} yes={b['yes_rate']:.3f} dev={b['deviation']:+.3f} z={b['z']:+.2f} {star}")
print("\n=== Close (same sample, for apples-to-apples) ===")
for b in out["close"]:
    if b["n"] >= 10:
        star = "***" if abs(b["z"]) >= 2 else ""
        print(f"  {b['bucket']} n={b['n']:>5} mid={b['mid']:.3f} yes={b['yes_rate']:.3f} dev={b['deviation']:+.3f} z={b['z']:+.2f} {star}")
