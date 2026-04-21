#!/usr/bin/env python3
"""
Analyze HL BTC-PERP quiet hours, then cross-ref against rank-2 wallet entries.
"""
import json, math, datetime, statistics
from collections import defaultdict, Counter

DIR = "/tmp/hl_study/e26_mm_research"

# Load 15m candles for hourly vol
c15 = json.load(open(f"{DIR}/btc_15m_candles.json"))
c1h = json.load(open(f"{DIR}/btc_1h_candles.json"))

# Each HL candle: {t, T, s, i, o, h, l, c, v, n}
# Realized vol per 15m bar: log(c/o). Aggregate by UTC hour-of-day.
def hour_of(t_ms):
    return datetime.datetime.fromtimestamp(t_ms/1000, datetime.UTC).hour

# ------ hour-of-day realized vol from 15m bars ------
# per-15m log return; then for each hour-of-day, compute sum of squared returns per hour -> realized vol estimator.
# Simpler: aggregate 15m bars by hour -> the hourly realized vol in bps is sqrt(sum of (log ret)^2) per hour.
# But we want DISTRIBUTION across days. So group bars by (day, hour) first.

by_day_hour = defaultdict(list)
for b in c15:
    t = b["t"]; dt = datetime.datetime.fromtimestamp(t/1000, datetime.UTC)
    key = (dt.date(), dt.hour)
    o = float(b["o"]); cc = float(b["c"])
    if o > 0 and cc > 0:
        r = math.log(cc/o)
        by_day_hour[key].append(r)

# For each (day, hour), realized vol = sqrt(sum r^2)
day_hour_vol = {}
for k, rs in by_day_hour.items():
    if len(rs) >= 3:  # need at least 3 of 4 15m bars
        rv = math.sqrt(sum(r*r for r in rs))
        day_hour_vol[k] = rv

# Distribution by hour-of-day
by_hour = defaultdict(list)
for (d,h), rv in day_hour_vol.items():
    by_hour[h].append(rv * 10000)  # convert to bps

def pct(xs, p):
    xs = sorted(xs)
    if not xs: return None
    k = (len(xs)-1)*p
    lo = int(math.floor(k)); hi = int(math.ceil(k))
    if lo == hi: return xs[lo]
    return xs[lo] + (xs[hi]-xs[lo])*(k-lo)

hourly_table = {}
for h in range(24):
    vs = by_hour.get(h, [])
    if not vs: continue
    hourly_table[h] = {
        "n_days": len(vs),
        "median_bps": round(pct(vs, 0.5), 2),
        "p25_bps": round(pct(vs, 0.25), 2),
        "p75_bps": round(pct(vs, 0.75), 2),
        "mean_bps": round(sum(vs)/len(vs), 2),
    }

# Identify quiet hours: bottom quartile by median realized vol
med_sorted = sorted(hourly_table.items(), key=lambda kv: kv[1]["median_bps"])
q_cut = int(len(med_sorted) * 0.25) or 1
quiet_hours = sorted([h for h,_ in med_sorted[:q_cut+2]])  # pad slightly to 6 hours
# Use strict bottom-quartile (6 hours):
quiet_hours_strict = sorted([h for h,_ in med_sorted[:6]])

# ------ |4h rolling ret| per hour-of-day from 1h candles ------
# 4h return: log(close_t / close_{t-4}) using hourly closes.
closes = [(b["t"], float(b["c"])) for b in c1h]
closes.sort()
four_h_rets = []
for i in range(4, len(closes)):
    t, c = closes[i]
    _, c0 = closes[i-4]
    r = math.log(c/c0)
    four_h_rets.append((t, r))

by_hour_4h = defaultdict(list)
for t, r in four_h_rets:
    h = hour_of(t - 4*3600*1000)  # hour at START of window
    by_hour_4h[h].append(abs(r))

hour_4h_table = {}
for h in range(24):
    vs = by_hour_4h.get(h, [])
    if not vs: continue
    pct_flat = sum(1 for v in vs if v < 0.005) / len(vs)
    hour_4h_table[h] = {
        "n_windows": len(vs),
        "pct_abs4h_lt_0p5pct": round(pct_flat*100, 1),
        "median_abs4h_bps": round(pct(vs,0.5)*10000, 1),
    }

# Aggregate across quiet vs active hours
quiet_set = set(quiet_hours_strict)
active_hours = [h for h in range(24) if h not in quiet_set]
def pct_flat_for(hours):
    rs = []
    for t, r in four_h_rets:
        if hour_of(t - 4*3600*1000) in hours: rs.append(abs(r))
    if not rs: return 0, 0
    return sum(1 for v in rs if v<0.005)/len(rs), len(rs)

q_pct, q_n = pct_flat_for(quiet_set)
a_pct, a_n = pct_flat_for(set(active_hours))

# ------ Rank-2 wallet BTC entries by hour ------
w = json.load(open("/tmp/hl_study/fills/0xecb63caa47c7c4e77f60f1ce858cf28dc2b82b00.json"))
btc_fills = [f for f in w if f.get("coin") == "BTC"]
# "entries" = Open fills (dir contains "Open") — those start a position
btc_entries = [f for f in btc_fills if "Open" in (f.get("dir") or "")]
btc_closes  = [f for f in btc_fills if "Close" in (f.get("dir") or "")]

entry_hours = Counter(hour_of(f["time"]) for f in btc_entries)
all_hours = Counter(hour_of(f["time"]) for f in btc_fills)

# notional-weighted version
entry_notional_by_hour = defaultdict(float)
for f in btc_entries:
    entry_notional_by_hour[hour_of(f["time"])] += float(f["px"]) * float(f["sz"])

total_entries = sum(entry_hours.values())
total_notional = sum(entry_notional_by_hour.values())

by_hour_entry_pct = {h: round(entry_hours.get(h,0)/total_entries*100,2) for h in range(24)}
by_hour_notional_pct = {h: round(entry_notional_by_hour.get(h,0)/total_notional*100,2) for h in range(24)}

# expected uniform = 100/24 = 4.17%
# quiet-hours concentration
quiet_entry_pct = sum(by_hour_entry_pct[h] for h in quiet_set)
quiet_notional_pct = sum(by_hour_notional_pct[h] for h in quiet_set)
uniform_share = len(quiet_set)/24*100

# rank-ordered concentration
rank_ordered = sorted(by_hour_entry_pct.items(), key=lambda kv:-kv[1])

# ------ Save JSON artifacts ------
with open(f"{DIR}/btc_hourly_vol.json","w") as f:
    json.dump({
        "source": "HL info candleSnapshot 15m, 52 days (2026-02-28 to 2026-04-21)",
        "metric": "realized_vol_per_hour_bps = sqrt(sum(log(c/o)^2) across 4x15m bars) * 1e4",
        "hourly_table_utc": hourly_table,
        "quiet_hours_bottom_quartile_utc": quiet_hours_strict,
        "hour_4h_absret_table_utc": hour_4h_table,
        "quiet_vs_active_pct_4h_flat": {
            "quiet_hours": quiet_hours_strict,
            "pct_abs4h_lt_0p5pct_quiet": round(q_pct*100,2),
            "n_windows_quiet": q_n,
            "pct_abs4h_lt_0p5pct_active": round(a_pct*100,2),
            "n_windows_active": a_n,
        },
    }, f, indent=2)

with open(f"{DIR}/rank2_hour_distribution.json","w") as f:
    json.dump({
        "wallet": "0xecb63caa47c7c4e77f60f1ce858cf28dc2b82b00",
        "total_btc_fills": len(btc_fills),
        "btc_entries_n": len(btc_entries),
        "btc_closes_n": len(btc_closes),
        "entry_count_pct_by_hour_utc": by_hour_entry_pct,
        "entry_notional_pct_by_hour_utc": by_hour_notional_pct,
        "rank_ordered_top10_hours": rank_ordered[:10],
        "quiet_hours_used": quiet_hours_strict,
        "quiet_hours_expected_share_pct": round(uniform_share,2),
        "quiet_hours_actual_entry_share_pct": round(quiet_entry_pct,2),
        "quiet_hours_actual_notional_share_pct": round(quiet_notional_pct,2),
        "concentration_ratio_count": round(quiet_entry_pct/uniform_share,3),
        "concentration_ratio_notional": round(quiet_notional_pct/uniform_share,3),
        "fills_time_range_utc": [
            datetime.datetime.fromtimestamp(min(f["time"] for f in btc_fills)/1000, datetime.UTC).isoformat(),
            datetime.datetime.fromtimestamp(max(f["time"] for f in btc_fills)/1000, datetime.UTC).isoformat(),
        ],
    }, f, indent=2)

# ------ Print summary to stdout ------
print("\n=== Hour-of-day realized vol (bps, 15m-based) ===")
print("hour  n_days  p25   med   p75   mean")
for h in range(24):
    v = hourly_table.get(h);
    if v: print(f"  {h:02d}   {v['n_days']:>4}  {v['p25_bps']:>5.1f} {v['median_bps']:>5.1f} {v['p75_bps']:>5.1f} {v['mean_bps']:>5.1f}")

print(f"\nQuiet hours (bottom 6 by median rv bps): {quiet_hours_strict}")
print(f"Quiet vs active: %|4h ret|<0.5% — quiet={q_pct*100:.2f}% (n={q_n}), active={a_pct*100:.2f}% (n={a_n})")

print(f"\n=== Rank-2 BTC entry hour distribution (n={len(btc_entries)}) ===")
print("Top 10 hours by entry-count %:")
for h, p in rank_ordered[:10]:
    tag = " [QUIET]" if h in quiet_set else ""
    print(f"  {h:02d}: {p:5.2f}%{tag}")
print(f"\nQuiet hours share of entries: {quiet_entry_pct:.2f}% (expected uniform={uniform_share:.2f}%)  conc_ratio={quiet_entry_pct/uniform_share:.2f}")
print(f"Quiet hours share of notional:{quiet_notional_pct:.2f}% (expected={uniform_share:.2f}%)  conc_ratio={quiet_notional_pct/uniform_share:.2f}")
