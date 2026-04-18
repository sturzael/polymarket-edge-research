"""Cross-correlate Binance-vs-Coinbase BTC returns at sub-second resolution.

Rig calibration: if we can't see a well-documented 50-200ms Binance→Coinbase
lead on BTC, our pipeline isn't fit to measure Polymarket-vs-spot lag either.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd


DB = Path(__file__).parent / "leadlag.db"
BIN_MS_OPTIONS = [100, 250, 500, 1000]
LAG_RANGE_MS = 3000   # ±3s sweep
OUT_DIR = Path(__file__).parent


def load_trades() -> pd.DataFrame:
    conn = sqlite3.connect(DB)
    df = pd.read_sql_query(
        "SELECT venue, exch_ts_ms, price FROM trades ORDER BY exch_ts_ms",
        conn,
    )
    conn.close()
    df["exch_ts_ms"] = df["exch_ts_ms"].astype("int64")
    return df


def binned_log_returns(df: pd.DataFrame, venue: str, bin_ms: int) -> pd.Series:
    """Volume-ignoring: take last price in each bin as the representative price,
    compute log returns. Empty bins forward-fill price."""
    sub = df[df.venue == venue].copy()
    if sub.empty:
        return pd.Series(dtype="float64")
    sub["bin"] = (sub["exch_ts_ms"] // bin_ms) * bin_ms
    last_price = sub.groupby("bin")["price"].last()
    # Reindex to dense grid
    full = pd.RangeIndex(last_price.index.min(), last_price.index.max() + bin_ms, bin_ms)
    last_price = last_price.reindex(full).ffill()
    logret = np.log(last_price).diff().dropna()
    return logret


def cross_correlate(x: pd.Series, y: pd.Series, max_lag_bins: int) -> list[tuple[int, float]]:
    """Return list of (lag_bins, corr) for lag in [-max, +max].
    Positive lag means x leads y (shift y forward to align).
    """
    out: list[tuple[int, float]] = []
    # Align x and y on shared bin grid
    idx = x.index.intersection(y.index)
    if len(idx) < 10:
        return out
    xa = x.reindex(idx)
    ya = y.reindex(idx)
    for lag in range(-max_lag_bins, max_lag_bins + 1):
        if lag >= 0:
            x2 = xa.iloc[: len(xa) - lag] if lag > 0 else xa
            y2 = ya.iloc[lag:] if lag > 0 else ya
        else:
            x2 = xa.iloc[-lag:]
            y2 = ya.iloc[: len(ya) + lag]
        if len(x2) < 10:
            continue
        if x2.std() == 0 or y2.std() == 0:
            continue
        c = float(np.corrcoef(x2.values, y2.values)[0, 1])
        out.append((lag, c))
    return out


def main() -> None:
    df = load_trades()
    print(f"trades loaded: {len(df)}  ({df.venue.value_counts().to_dict()})")
    span_min = (df.exch_ts_ms.max() - df.exch_ts_ms.min()) / 60000
    print(f"span: {span_min:.1f} min\n")

    summary: list[dict] = []
    for bin_ms in BIN_MS_OPTIONS:
        bn = binned_log_returns(df, "binance", bin_ms)
        cb = binned_log_returns(df, "coinbase", bin_ms)
        if bn.empty or cb.empty:
            continue
        max_lag_bins = LAG_RANGE_MS // bin_ms
        xc = cross_correlate(bn, cb, max_lag_bins)
        if not xc:
            continue
        # Peak (strongest abs correlation)
        peak_lag, peak_c = max(xc, key=lambda kv: abs(kv[1]))
        peak_ms = peak_lag * bin_ms
        # Also compute zero-lag correlation for reference
        zero = next((c for l, c in xc if l == 0), None)
        print(f"bin={bin_ms:4d}ms  n_binance={len(bn)}  n_coinbase={len(cb)}  "
              f"peak_lag={peak_ms:+5d}ms  peak_corr={peak_c:+.3f}  zero_corr={zero:+.3f}")
        summary.append({
            "bin_ms": bin_ms,
            "n_binance_bins": len(bn),
            "n_coinbase_bins": len(cb),
            "peak_lag_ms": peak_ms,
            "peak_corr": peak_c,
            "zero_lag_corr": zero,
            "xc_full": xc,
        })

    # Dump full xc at finest bin size to csv for plotting
    if summary:
        best = min(summary, key=lambda s: s["bin_ms"])
        xc_df = pd.DataFrame(best["xc_full"], columns=["lag_bins", "corr"])
        xc_df["lag_ms"] = xc_df["lag_bins"] * best["bin_ms"]
        xc_df[["lag_ms", "corr"]].to_csv(OUT_DIR / "xcorr_fine.csv", index=False)
        # Remove xc_full from summary for concise JSON
        for s in summary:
            s.pop("xc_full", None)
        import json
        (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2))
        print(f"\nsummary -> summary.json")
        print(f"finest-bin xcorr -> xcorr_fine.csv")


if __name__ == "__main__":
    main()
