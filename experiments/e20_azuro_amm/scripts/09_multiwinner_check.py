import csv
from collections import Counter, defaultdict
wins_per_cond = defaultdict(int)
n_outcomes_per_cond = {}
with open("/Users/elliotsturzaker/dev/event-impact-mvp/experiments/e20_azuro_amm/data/07_close_rows.csv") as f:
    for r in csv.DictReader(f):
        cid = r["condition_id"]
        n_outcomes_per_cond[cid] = int(r["n_outcomes"])
        wins_per_cond[cid] += int(r["is_yes"])

dist = defaultdict(Counter)
for cid, nw in wins_per_cond.items():
    no = n_outcomes_per_cond[cid]
    dist[no][nw] += 1
print("n_outcomes -> {n_wins: n_conditions}")
for no in sorted(dist):
    print(f"  {no}: {dict(sorted(dist[no].items()))}")
