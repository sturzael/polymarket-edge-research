"""SII Polymarket_data dataset schema probe.

Verifies the README claims: schema, fee fields, freshness, real on-chain data.

Hard kill criteria — if ANY fails, write negative finding and skip 02-05:
  K1: orderfilled.parquet has populated maker_fee/taker_fee/protocol_fee columns
  K2: latest block_number maps to a date within the last 90 days
  K3: at least one sampled transaction_hash resolves on Polygon (we just check
      it's a 0x-prefixed 32-byte hex; full polygonscan check is out of scope
      for the cheap probe)

Storage: downloads markets.parquet (~68MB) once; orderfilled.parquet is read
via HfFileSystem row-group filtering, never persisted to disk.

Output:
  data/01_probe.json — structured findings
  stdout — human summary
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq
from huggingface_hub import HfFileSystem, hf_hub_download

DATASET = "SII-WANGZJ/Polymarket_data"
DATA_DIR = Path(__file__).parent / "data"
OUT_JSON = DATA_DIR / "01_probe.json"

REQUIRED_TRADES_COLS = {
    "timestamp", "block_number", "transaction_hash", "contract",
    "maker", "taker", "maker_asset_id", "taker_asset_id",
    "maker_amount_filled", "taker_amount_filled",
    "maker_fee", "taker_fee", "protocol_fee", "order_hash",
}
ORDERFILLED_PARTS = [f"orderfilled_part{i}.parquet" for i in (1, 2, 3, 4)]


def probe_markets() -> dict:
    """Download markets.parquet (cheap), inspect schema and row count."""
    print("[1/3] markets.parquet — downloading (~68MB)...")
    t = time.time()
    p = hf_hub_download(repo_id=DATASET, filename="markets.parquet",
                        repo_type="dataset", cache_dir=str(DATA_DIR / "hf_cache"))
    pf = pq.ParquetFile(p)
    schema = {f.name: str(f.physical_type) for f in pf.schema}
    n = pf.metadata.num_rows
    print(f"      {n:,} markets, {len(schema)} columns ({time.time()-t:.1f}s)")
    return {"path": p, "n_rows": n, "schema": schema, "elapsed_s": round(time.time()-t, 1)}


def probe_orderfilled_metadata(fs: HfFileSystem) -> dict:
    """Read parquet metadata for ALL parts — no row data. Cheap."""
    print("[2/3] orderfilled_part{1..4}.parquet — reading parquet metadata only...")
    t = time.time()
    out = {"parts": {}}
    total_rows = 0
    for part in ORDERFILLED_PARTS:
        path = f"datasets/{DATASET}/{part}"
        with fs.open(path, "rb") as f:
            pf = pq.ParquetFile(f)
            meta = pf.metadata
            out["parts"][part] = {
                "n_rows": meta.num_rows,
                "n_row_groups": meta.num_row_groups,
            }
            total_rows += meta.num_rows
    out["schema"] = {f.name: str(f.physical_type) for f in pf.schema}  # last part schema
    out["total_rows"] = total_rows
    out["elapsed_s"] = round(time.time()-t, 1)
    print(f"      {total_rows:,} total rows across {len(ORDERFILLED_PARTS)} parts "
          f"({out['elapsed_s']:.1f}s)")
    return out


def probe_orderfilled_sample(fs: HfFileSystem) -> dict:
    """Read just the LAST row group of part4 — newest data + recency + fee shape."""
    print("[3/3] orderfilled_part4.parquet — reading last row group for recency check...")
    t = time.time()
    path = f"datasets/{DATASET}/orderfilled_part4.parquet"
    with fs.open(path, "rb") as f:
        pf = pq.ParquetFile(f)
        cols = ["timestamp", "block_number", "transaction_hash",
                "maker_fee", "taker_fee", "protocol_fee",
                "maker_amount_filled", "taker_amount_filled"]
        existing = [c for c in cols if c in pf.schema_arrow.names]
        # Walk back from last row group until we find one with rows.
        rg = None
        for back in range(0, 10):
            idx = pf.metadata.num_row_groups - 1 - back
            if idx < 0:
                break
            cand = pf.read_row_group(idx, columns=existing).to_pandas()
            if len(cand) > 0:
                rg = cand
                print(f"      using row group {idx} ({len(cand):,} rows)")
                break
        if rg is None or len(rg) == 0:
            return {"error": "no non-empty row group in last 10 of part4",
                    "elapsed_s": round(time.time()-t, 1)}
    print(f"      pulled {len(rg):,} rows from last row group ({time.time()-t:.1f}s)")

    out = {
        "rows_in_last_rg": len(rg),
        "elapsed_s": round(time.time()-t, 1),
        "cols_present": existing,
        "cols_missing": [c for c in cols if c not in existing],
    }

    if "timestamp" in rg.columns:
        latest_ts = rg["timestamp"].max()
        # Could be unix seconds or ms — sniff
        if latest_ts > 1e12:
            latest_dt = datetime.fromtimestamp(latest_ts / 1000, tz=timezone.utc)
        else:
            latest_dt = datetime.fromtimestamp(latest_ts, tz=timezone.utc)
        age_days = (datetime.now(timezone.utc) - latest_dt).total_seconds() / 86400
        out["latest_timestamp_iso"] = latest_dt.isoformat()
        out["latest_block_number"] = int(rg["block_number"].max()) if "block_number" in rg.columns else None
        out["age_days"] = round(age_days, 1)
        print(f"      latest record: {latest_dt.isoformat()} (age {age_days:.1f} days)")

    if "transaction_hash" in rg.columns and len(rg) > 0:
        sample_hashes = rg["transaction_hash"].dropna().head(3).tolist()
        out["sample_tx_hashes"] = [str(h) for h in sample_hashes]
        # Sanity check — must be 0x-prefixed 64-hex
        valid = []
        for h in sample_hashes:
            s = str(h)
            if s.startswith("0x") and len(s) == 66:
                valid.append(True)
            else:
                valid.append(False)
        out["sample_hashes_well_formed"] = all(valid) if valid else False

    # Fee field populated check — fees are FIXED_LEN_BYTE_ARRAY (uint256 BE).
    # "Non-zero" means at least one byte is non-zero.
    fee_check = {}
    for col in ("maker_fee", "taker_fee", "protocol_fee"):
        if col in rg.columns:
            non_null = rg[col].notna().sum()
            def _is_nonzero(b):
                if b is None:
                    return False
                if isinstance(b, (bytes, bytearray)):
                    return any(byte != 0 for byte in b)
                try:
                    return int(b) != 0
                except Exception:
                    return False
            non_zero = int(rg[col].apply(_is_nonzero).sum())
            # Also pull a sample non-zero hex value for sanity
            sample_hex = None
            for v in rg[col].dropna().head(50):
                if isinstance(v, (bytes, bytearray)) and any(byte != 0 for byte in v):
                    sample_hex = v.hex()
                    break
            fee_check[col] = {"non_null": int(non_null),
                              "non_zero": non_zero,
                              "fraction_non_null": round(non_null / max(len(rg), 1), 3),
                              "fraction_non_zero": round(non_zero / max(len(rg), 1), 3),
                              "sample_nonzero_hex": sample_hex}
    out["fee_population"] = fee_check

    return out


def evaluate_kill_criteria(report: dict) -> dict:
    """Returns {pass: bool, kill_reasons: [str]}."""
    reasons = []
    sample = report["orderfilled_sample"]
    fees = sample.get("fee_population", {})

    # K1: fees populated. We don't insist all three are populated — protocol_fee
    # could legitimately be 0 most of the time. We DO insist taker_fee or
    # maker_fee has non-null entries.
    fee_present = any(
        fees.get(c, {}).get("non_null", 0) > 0
        for c in ("taker_fee", "maker_fee")
    )
    if not fee_present:
        reasons.append("K1: no maker_fee or taker_fee values found")

    # K2: recency
    age = sample.get("age_days")
    if age is None:
        reasons.append("K2: could not determine dataset age")
    elif age > 90:
        reasons.append(f"K2: dataset is {age:.0f} days stale (> 90)")

    # K3: tx hash format
    if not sample.get("sample_hashes_well_formed", False):
        reasons.append("K3: sampled transaction hashes don't look like 0x32 hex")

    return {"pass": not reasons, "kill_reasons": reasons}


def main():
    DATA_DIR.mkdir(exist_ok=True)
    fs = HfFileSystem()

    report = {"dataset": DATASET, "probed_at": datetime.now(timezone.utc).isoformat()}
    try:
        report["markets"] = probe_markets()
    except Exception as e:
        report["markets_error"] = repr(e)

    try:
        report["orderfilled_metadata"] = probe_orderfilled_metadata(fs)
    except Exception as e:
        report["orderfilled_metadata_error"] = repr(e)

    try:
        report["orderfilled_sample"] = probe_orderfilled_sample(fs)
    except Exception as e:
        report["orderfilled_sample_error"] = repr(e)

    if "orderfilled_sample" in report:
        report["kill_criteria"] = evaluate_kill_criteria(report)
    else:
        report["kill_criteria"] = {"pass": False, "kill_reasons": ["could not pull sample"]}

    OUT_JSON.write_text(json.dumps(report, indent=2, default=str))
    print()
    print("=" * 60)
    print(f"Probe written to {OUT_JSON}")
    print(f"Pass: {report['kill_criteria']['pass']}")
    if report["kill_criteria"]["kill_reasons"]:
        for r in report["kill_criteria"]["kill_reasons"]:
            print(f"  KILL: {r}")
    return 0 if report["kill_criteria"]["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
