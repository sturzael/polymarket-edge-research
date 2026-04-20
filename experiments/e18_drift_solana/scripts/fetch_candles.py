"""Fetch 1-hour candles for every Drift -BET prediction market over its full lifetime.

Output: data/candles/{symbol}.json (raw) + data/candles_summary.csv
"""
import json
import os
import time
import urllib.request
import urllib.parse
from pathlib import Path

BASE = "https://data.api.drift.trade"
HERE = Path(__file__).parent.parent
DATA = HERE / "data"
CDIR = DATA / "candles"
CDIR.mkdir(parents=True, exist_ok=True)


def fetch_json(url: str, retries: int = 3) -> dict | None:
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "e18-drift-study/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception as e:
            print(f"  retry {i+1}/{retries}: {e}")
            time.sleep(2)
    return None


def fetch_all_candles(symbol: str, newest_ts: int, oldest_ts: int, resolution: str = "60") -> list[dict]:
    """Fetch all candles. API quirk: `startTs` is the NEWER boundary, `endTs` is the OLDER boundary
    (opposite of param-name intuition). Returned records are newest-first.
    Resolution: '1', '5', '15', '60' (minutes) or 'D' for daily.
    """
    all_recs: list[dict] = []
    cursor_newest = newest_ts
    seen_ts: set[int] = set()
    page = 0
    while cursor_newest > oldest_ts and page < 200:
        params = urllib.parse.urlencode({
            "startTs": cursor_newest,   # newer boundary
            "endTs": oldest_ts,          # older boundary
            "limit": 1000,
        })
        url = f"{BASE}/market/{symbol}/candles/{resolution}?{params}"
        data = fetch_json(url)
        if not data or not data.get("success"):
            break
        recs = data.get("records", [])
        if not recs:
            break
        new = [r for r in recs if r["ts"] not in seen_ts]
        for r in new:
            seen_ts.add(r["ts"])
        all_recs.extend(new)
        if len(recs) < 1000:
            break
        # advance cursor past the oldest (minimum) ts we just saw
        min_ts = min(r["ts"] for r in recs)
        if cursor_newest == min_ts:
            break
        cursor_newest = min_ts - 1
        page += 1
        time.sleep(0.25)
    all_recs.sort(key=lambda r: r["ts"])
    return all_recs


def main() -> None:
    all_markets = json.load(open(DATA / "all_markets.json"))["markets"]
    bets = [m for m in all_markets if m["symbol"].endswith("-BET")]
    print(f"Prediction markets to process: {len(bets)}")

    # Wide window: Jan 2024 → today (Apr 2026). All -BET markets fall in this range.
    oldest_ts = 1704067200   # 2024-01-01
    newest_ts = int(time.time())

    summary_rows = []
    for m in bets:
        sym = m["symbol"]
        print(f"\n== {sym} (idx={m['marketIndex']}) ==")
        out_path = CDIR / f"{sym}.json"
        if out_path.exists():
            recs = json.load(open(out_path))
            print(f"  cached: {len(recs)} candles")
        else:
            recs = fetch_all_candles(sym, newest_ts, oldest_ts, resolution="60")
            json.dump(recs, open(out_path, "w"))
            print(f"  fetched: {len(recs)} 1h candles")
        if not recs:
            summary_rows.append({"symbol": sym, "n_candles": 0})
            continue
        first = recs[0]
        last = recs[-1]
        first_ts = first["ts"]
        last_ts = last["ts"]
        duration_days = (last_ts - first_ts) / 86400.0
        # Average hourly quote-volume
        qv = [r.get("quoteVolume", 0) or 0 for r in recs]
        # NOTE: quoteVolume is returned as a float already in these candles
        total_qv = sum(float(x) for x in qv)
        # Final fill / oracle price (most recent candle's close)
        summary_rows.append({
            "symbol": sym,
            "n_candles": len(recs),
            "first_ts": first_ts,
            "last_ts": last_ts,
            "duration_days": round(duration_days, 2),
            "first_fill_close": first.get("fillClose"),
            "last_fill_close": last.get("fillClose"),
            "last_oracle_close": last.get("oracleClose"),
            "total_quote_volume": round(total_qv, 2),
            "market_index": m["marketIndex"],
        })
        print(f"  duration={duration_days:.1f}d  total_qv=${total_qv:,.0f}  "
              f"last_fill={last.get('fillClose')}  last_oracle={last.get('oracleClose')}")

    # Save summary
    import csv
    keys = sorted({k for row in summary_rows for k in row.keys()})
    with open(DATA / "candles_summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(summary_rows)
    print(f"\nWrote {DATA / 'candles_summary.csv'}")


if __name__ == "__main__":
    main()
