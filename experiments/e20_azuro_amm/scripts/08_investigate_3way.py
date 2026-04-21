"""Investigate why 3-outcome conditions show wild over-performance in
0.30-0.40 buckets. Hypothesis: these are 3-way football markets and the
"draw" outcome has an unusual resolution pattern.
"""
import csv
from collections import defaultdict

rows = []
with open("/Users/elliotsturzaker/dev/event-impact-mvp/experiments/e20_azuro_amm/data/07_close_rows.csv") as f:
    rdr = csv.DictReader(f)
    for r in rdr:
        if int(r["n_outcomes"]) != 3:
            continue
        rows.append(r)

print(f"3-outcome rows: {len(rows):,}")

# Within each condition, rank outcomes by norm_prob
by_cond = defaultdict(list)
for r in rows:
    by_cond[r["condition_id"]].append(r)

# Rank-based analysis
rank_stats = defaultdict(lambda: {"n": 0, "yes": 0, "p_sum": 0.0, "p_min": 1, "p_max": 0})
sport_rank_stats = defaultdict(lambda: defaultdict(lambda: {"n": 0, "yes": 0, "p_sum": 0}))

for cond_id, outcomes in by_cond.items():
    if len(outcomes) != 3:
        continue
    outcomes_sorted = sorted(outcomes, key=lambda r: -float(r["norm_prob"]))
    for rank, r in enumerate(outcomes_sorted, start=1):
        s = rank_stats[rank]
        s["n"] += 1
        s["yes"] += int(r["is_yes"])
        s["p_sum"] += float(r["norm_prob"])
        s["p_min"] = min(s["p_min"], float(r["norm_prob"]))
        s["p_max"] = max(s["p_max"], float(r["norm_prob"]))
        sport_rank_stats[r["sport"]][rank]["n"] += 1
        sport_rank_stats[r["sport"]][rank]["yes"] += int(r["is_yes"])
        sport_rank_stats[r["sport"]][rank]["p_sum"] += float(r["norm_prob"])

print("\n=== 3-outcome conditions: by rank (favorite=1, 3rd=longshot) ===")
print(f"{'rank':<5} {'n':>7} {'mean_p':>7} {'yes_rate':>9} {'p_min':>6} {'p_max':>6}")
for rank in [1, 2, 3]:
    s = rank_stats[rank]
    if s["n"] == 0: continue
    mean_p = s["p_sum"] / s["n"]
    yes_rate = s["yes"] / s["n"]
    print(f"{rank:<5} {s['n']:>7,} {mean_p:>7.3f} {yes_rate:>9.3f} {s['p_min']:>6.3f} {s['p_max']:>6.3f}")

print("\n=== 3-outcome conditions: by sport + rank ===")
for sport in sorted(sport_rank_stats):
    print(f"\n{sport}:")
    for rank in [1, 2, 3]:
        s = sport_rank_stats[sport][rank]
        if s["n"] < 50: continue
        mean_p = s["p_sum"] / s["n"]
        yes_rate = s["yes"] / s["n"]
        dev = yes_rate - mean_p
        print(f"  rank {rank}: n={s['n']:>5,}  mean_p={mean_p:.3f}  yes_rate={yes_rate:.3f}  dev={dev:+.3f}")

# Hmm is this about football draw markets?
# Check outcomeId distribution — in football 3-way, outcomeIds often follow a pattern
# Home/draw/away. Check if the "draw" outcome (middle rank by prob) is abnormally frequent
# Let's check whether the overrepresented 0.30-0.40 bucket comes from specific outcomeIds
from collections import Counter
bucket_outcome_ids = defaultdict(Counter)
for r in rows:
    p = float(r["norm_prob"])
    if 0.30 <= p < 0.40:
        bucket_outcome_ids[r["sport"]][r["outcome_id"]] += 1

print("\n=== 0.30-0.40 bucket — top outcomeIds by sport ===")
for sport, cnt in sorted(bucket_outcome_ids.items(), key=lambda x: -sum(x[1].values()))[:5]:
    print(f"\n{sport}: (total in 0.30-0.40: {sum(cnt.values()):,})")
    for oid, n in cnt.most_common(5):
        print(f"  outcomeId={oid}: {n:,}")

# Check 0.30-0.40 bucket yes_rate by sport for 3-outcome conditions
print("\n=== 0.30-0.40 bucket — yes_rate by sport (3-outcome only) ===")
by_sport_bucket = defaultdict(lambda: {"n": 0, "yes": 0})
for r in rows:
    p = float(r["norm_prob"])
    if 0.30 <= p < 0.40:
        by_sport_bucket[r["sport"]]["n"] += 1
        by_sport_bucket[r["sport"]]["yes"] += int(r["is_yes"])
for sport, s in sorted(by_sport_bucket.items(), key=lambda x: -x[1]["n"]):
    if s["n"] < 50: continue
    yr = s["yes"] / s["n"]
    print(f"  {sport:<25} n={s['n']:>6,}  yes_rate={yr:.3f}")
