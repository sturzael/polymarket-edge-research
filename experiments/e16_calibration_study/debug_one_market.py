"""Pull SII orderfilled rows for ONE specific market, print raw + decoded prices.

Compare against gamma ground-truth to isolate the bug.
"""
from __future__ import annotations

import os
import sys
import time
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "30")

from pathlib import Path
import pyarrow.parquet as pq
from huggingface_hub import HfFileSystem

DATASET = "SII-WANGZJ/Polymarket_data"

# Ground-truth market: cbb-cin-ucf-2026-01-11-total-151pt5
CONDITION_ID = "0xd5f2fb8215e691692f3a449b10555f1d20229150efae4bbd8cc21887bd398de7"
TOKEN_YES = "8475739338716417699396894109460035333359942292723852932873197259888720876357"
TOKEN_NO  = "5130657648766891127689007984031091673206202062770698733036101670412541699278"
# End date of market: 2026-01-11 22:00:00 UTC
END_TS = 1768176000  # approx

# Window: 24h before close (narrow to speed the scan)
WINDOW_START = END_TS - 24 * 3600
WINDOW_END   = END_TS + 1000


def decstr(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bytes):
        return str(int.from_bytes(v, "big"))
    return str(v)


def amt(v, decimals=6) -> float:
    if v is None:
        return 0.0
    if isinstance(v, bytes):
        return int.from_bytes(v, "big") / (10 ** decimals)
    return float(v) / (10 ** decimals)


def main():
    fs = HfFileSystem()
    # Check parts 2,3,4 — most recent data
    for part in (4, 3, 2, 1):
        path = f"datasets/{DATASET}/orderfilled_part{part}.parquet"
        with fs.open(path, "rb") as f:
            pf = pq.ParquetFile(f)
            n_rgs = pf.metadata.num_row_groups
            print(f"[part{part}] scanning {n_rgs} row-groups for trades on market "
                  f"{CONDITION_ID[:16]}...")
            found = 0
            for rg_idx in range(n_rgs):
                batch = pf.read_row_group(rg_idx).to_pandas()
                for _, r in batch.iterrows():
                    m = decstr(r["maker_asset_id"])
                    t = decstr(r["taker_asset_id"])
                    if m not in (TOKEN_YES, TOKEN_NO) and t not in (TOKEN_YES, TOKEN_NO):
                        continue
                    ts = int(r["timestamp"])
                    if ts < WINDOW_START or ts > WINDOW_END:
                        continue
                    ma = amt(r["maker_amount_filled"])
                    ta = amt(r["taker_amount_filled"])
                    ratio_ma_ta = (ma / ta) if ta > 0 else 0
                    ratio_ta_ma = (ta / ma) if ma > 0 else 0
                    mlabel = ("YES" if m == TOKEN_YES else "NO " if m == TOKEN_NO else f"oth:{m[:6]}")
                    tlabel = ("YES" if t == TOKEN_YES else "NO " if t == TOKEN_NO else f"oth:{t[:6]}")
                    print(f"  ts={ts}  m={mlabel}({ma:.4f})  t={tlabel}({ta:.4f})  "
                          f"ma/ta={ratio_ma_ta:.4f}  ta/ma={ratio_ta_ma:.4f}")
                    found += 1
                    if found >= 10:
                        return
            print(f"[part{part}] found {found} trades for this market")


if __name__ == "__main__":
    main()
