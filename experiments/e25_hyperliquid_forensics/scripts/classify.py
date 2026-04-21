"""
Per-wallet momentum-coincident % classifier.

Ported methodology (Polymarket wallet-forensics study):
- Entry = fill with dir.startswith('Open') — 'Open Long' or 'Open Short'.
- For each entry, compute return over the 4h window ending at (entry_time - 1min).
  ret = (px_at_entry_minus_1min - px_at_entry_minus_4h) / px_at_entry_minus_4h
- Momentum-coincident:
    Long entry  following ret >=  +0.005 (+0.5%)
    Short entry following ret <= -0.005
- Contrarian/structural-leaning:
    Long entry  following ret <= -0.005
    Short entry following ret >= +0.005
- Neutral: |ret| < 0.005 (flat regime, no clear directional momentum)

Classification:
  momentum_pct = momentum_coincident / (momentum + contrarian + neutral)   [% of ALL entries, includes flat regime]
  For tighter regime-sensitivity we also report momentum_pct_directional = momentum / (momentum + contrarian)
  (matches the original study's framing: "215/223 within 60s of BTC >0.5% move")

Thresholds (port):
  momentum_pct  > 80  -> momentum-lucky
  momentum_pct  < 30  -> structural candidate
  else                -> mixed
"""

import json, os, bisect
from collections import defaultdict, Counter

THRESH_MOMENTUM = 0.005
LOOKBACK_MS = 4 * 3600 * 1000
OFFSET_MS = 60 * 1000  # entry_time - 1min is the "after" point

BINANCE_COINS = {'BTC','ETH','SOL','ZEC','PUMP','ENA','WLD','TAO','ORDI','ZRO','AAVE','NEAR','CRV','ASTER','XPL'}
HL_COINS = {'HYPE','FARTCOIN','MON','IP','STBL','XMR','LIT'}
TRADABLE = BINANCE_COINS | HL_COINS


def load_prices(base='/tmp/hl_study/prices'):
    """Return {coin: (sorted_times, closes)}. Times in ms, closes as floats."""
    pr = {}
    for fn in os.listdir(base):
        coin = fn.replace('.json', '')
        data = json.load(open(f'{base}/{fn}'))
        data.sort()
        times = [r[0] for r in data]
        closes = [r[1] for r in data]
        pr[coin] = (times, closes)
    return pr


def price_at_or_before(times, closes, t, max_gap_ms=10*60*1000):
    """Find the latest candle with openTime <= t; return close, or None if gap > max_gap_ms."""
    idx = bisect.bisect_right(times, t) - 1
    if idx < 0:
        return None
    if t - times[idx] > max_gap_ms:
        return None
    return closes[idx]


def classify_wallet(fills, prices):
    """
    Returns dict with counts and classification.
    """
    stats = {
        'total_entries': 0,
        'coverable_entries': 0,
        'by_coin': Counter(),
        'momentum': 0,          # entry direction matches 4h trend, |ret|>=0.5%
        'contrarian': 0,        # entry direction opposite to 4h trend, |ret|>=0.5%
        'neutral': 0,           # |ret|<0.5%
        'missing_price': 0,
        'returns': [],          # for distribution inspection: (signed_return, side) where signed_return = ret * side_sign
    }
    for f in fills:
        if not f.get('dir', '').startswith('Open'):
            continue
        stats['total_entries'] += 1
        coin = f['coin']
        if coin not in prices:
            continue
        side = f['side']  # B=buy=long, A=ask=short
        is_long = (side == 'B')
        t_entry = f['time']
        t_after = t_entry - OFFSET_MS
        t_before = t_entry - OFFSET_MS - LOOKBACK_MS

        times, closes = prices[coin]
        px_after = price_at_or_before(times, closes, t_after)
        px_before = price_at_or_before(times, closes, t_before)
        if px_after is None or px_before is None or px_before == 0:
            stats['missing_price'] += 1
            continue
        ret = (px_after - px_before) / px_before

        stats['coverable_entries'] += 1
        stats['by_coin'][coin] += 1
        signed = ret if is_long else -ret
        stats['returns'].append(signed)

        if abs(ret) < THRESH_MOMENTUM:
            stats['neutral'] += 1
        elif (ret > 0 and is_long) or (ret < 0 and not is_long):
            stats['momentum'] += 1
        else:
            stats['contrarian'] += 1
    n = stats['momentum'] + stats['contrarian'] + stats['neutral']
    stats['n_classified'] = n
    if n > 0:
        stats['momentum_pct'] = 100.0 * stats['momentum'] / n
        stats['contrarian_pct'] = 100.0 * stats['contrarian'] / n
        stats['neutral_pct'] = 100.0 * stats['neutral'] / n
        dn = stats['momentum'] + stats['contrarian']
        stats['momentum_pct_directional'] = 100.0 * stats['momentum'] / dn if dn else None
    else:
        stats['momentum_pct'] = None
        stats['momentum_pct_directional'] = None
    return stats


def classify_label(momentum_pct):
    if momentum_pct is None:
        return 'insufficient'
    if momentum_pct > 80:
        return 'momentum-lucky'
    if momentum_pct < 30:
        return 'structural'
    return 'mixed'


if __name__ == '__main__':
    print("loading prices...")
    prices = load_prices()
    print(f"loaded {len(prices)} coins: {sorted(prices.keys())}")

    top50 = json.load(open('/tmp/hl_study/top50.json'))
    addr_to_rank = {r['ethAddress']: i+1 for i, r in enumerate(top50)}
    addr_to_pnl = {r['ethAddress']: float(next(p for w,p in [(w, p) for w,p in r['windowPerformances']])[0]) for r in top50}  # placeholder
    # simpler: recompute
    addr_to_pnl = {}
    addr_to_vlm = {}
    addr_to_monthpnl = {}
    for r in top50:
        for w, p in r['windowPerformances']:
            if w == 'allTime':
                addr_to_pnl[r['ethAddress']] = float(p['pnl'])
                addr_to_vlm[r['ethAddress']] = float(p['vlm'])
            if w == 'month':
                addr_to_monthpnl[r['ethAddress']] = float(p['pnl'])

    results = []
    for fn in sorted(os.listdir('/tmp/hl_study/fills')):
        addr = fn.replace('.json','')
        fills = json.load(open(f'/tmp/hl_study/fills/{fn}'))
        s = classify_wallet(fills, prices)
        s['addr'] = addr
        s['rank'] = addr_to_rank.get(addr)
        s['allTime_pnl'] = addr_to_pnl.get(addr)
        s['allTime_vlm'] = addr_to_vlm.get(addr)
        s['month_pnl'] = addr_to_monthpnl.get(addr)
        s['label'] = classify_label(s['momentum_pct'])
        results.append(s)

    # Sort by rank
    results.sort(key=lambda r: r['rank'])

    print(f"\n{'rank':>4} {'addr':<44} {'allTime_pnl':>14} {'n_cls':>6} {'mom%':>6} {'con%':>6} {'neu%':>6} {'mom_dir%':>8} label")
    for r in results:
        if r['n_classified'] == 0:
            print(f"{r['rank']:>4} {r['addr']:<44} {r['allTime_pnl']:>14,.0f} {'-':>6} {'-':>6} {'-':>6} {'-':>6} {'-':>8} no-tradable-assets")
            continue
        mp = r['momentum_pct']; cp = r['contrarian_pct']; np_ = r['neutral_pct']
        mpd = r['momentum_pct_directional']
        print(f"{r['rank']:>4} {r['addr']:<44} {r['allTime_pnl']:>14,.0f} {r['n_classified']:>6} {mp:>6.1f} {cp:>6.1f} {np_:>6.1f} {mpd if mpd is not None else 0:>8.1f} {r['label']}")

    with open('/tmp/hl_study/results.json','w') as f:
        # Strip returns list for serialization (keep for distribution plot separately)
        serializable = []
        for r in results:
            r2 = dict(r)
            r2['by_coin'] = list(r2['by_coin'].items()) if 'by_coin' in r2 else []
            r2['returns'] = r2.get('returns', [])
            serializable.append(r2)
        json.dump(serializable, f, indent=2, default=str)
