"""
Upper-bound sensitivity check: what if everything breaks our way?
- Maker fee = 1.0 bps (VIP/staking tier)
- Capture rate = 100% of spread (we always get filled first)
- Fills/day = 200 (active market, 8+ per hour)
This is the theoretical ceiling — used to determine whether the hypothesis has ANY room.
"""
import json

d = json.load(open('/Users/elliotsturzaker/dev/event-impact-mvp/experiments/e27_hl_synthetics_recon/data/spread_snapshots.json'))
MAKER = 1.0
QUOTE = 2500

print("Optimistic ceiling scenario: 100% capture, 1.0bp fee, 200 fills/day at $2500/side.")
print(f"{'coin':<18} {'spread':>7} {'net/fill':>10} {'raw_$/mo':>10} {'/5 $/mo':>10}")
print("(Anything that doesn't look good even here is structurally dead for solo retail.)")
for s in d['summary']:
    spread = s['mean_spread_bps']
    net = spread - MAKER
    raw_monthly = QUOTE * (net/10000) * 200 * 30
    adj_monthly = raw_monthly / 5
    verdict = "ceiling>0 -> ~100%-capture dream" if net > 0 else "dead even at ceiling"
    print(f"  {s['coin']:<18}  {spread:>5.2f}  {net:>7.2f}bp  ${raw_monthly:>8,.0f}  ${adj_monthly:>8,.0f}  {verdict}")
