"""Download a batch of Betfair datascientists CSVs covering multiple sports and years.

Strategy:
- Sports match-odds files (small) for AFL, NRL, A-League, BBL, AFLW, NRLW across years 2021-2025.
  Gives us thousands of 2-way match-odds markets with T-60min / T-30min / T-1min / kickoff prices.
- Horse racing ANZ thoroughbred CSVs for 2026 months (smaller than zipped years).
  Tens of thousands of runners with BSP and preplay weighted average prices.
"""
from __future__ import annotations
import httpx, pathlib, time

DATA = pathlib.Path(__file__).parent.parent / "data"
RAW = DATA / "raw"
RAW.mkdir(exist_ok=True, parents=True)

BASE = "https://betfair-datascientists.github.io/data/assets/"

FILES = [
    # AFL — match odds only (small, fast)
    "AFL_2021_All_Markets.csv",  # already have but re-list for completeness — skip if exists
    "AFL_2022_All_Markets.csv",
    "AFL_2023_All_Markets.csv",
    "AFL_2024_All_Markets.csv",
    "AFL_2025_All_Markets.csv",

    # AFLW
    "AFLW_2021_All_Markets.csv",
    "AFLW_2022_(S6)_All_Markets.csv",
    "AFLW_2022_(S7)_All_Markets.csv",
    "AFLW_2023_All_Markets.csv",
    "AFLW_2024_All_Markets.csv",
    "AFLW_2025_All_Markets.csv",

    # NRL
    "NRL_2021_All_Markets.csv",
    "NRL_2022_All_Markets.csv",
    "NRL_2023_All_Markets.csv",
    "NRL_2024_All_Markets.csv",
    "NRL_2025_All_Markets.csv",

    # A-League
    "A-League_2020-2021_All_Markets.csv",
    "A-League_2021-2022_All_Markets.csv",
    "A-League_2022-2023_All_Markets.csv",
    "A-League_2023-2024_All_Markets.csv",
    "A-League_2024-2025_All_Markets.csv",

    # BBL (cricket)
    "BBL10_All_Markets.csv",
    "BBL11_All_Markets.csv",
    "BBL12_All_Markets.csv",
    "BBL13_All_Markets.csv",
    "BBL14_All_Markets.csv",

    # NBL
    "NBL_2021-2022_All_Markets.csv",
    "NBL_2022-2023_All_Markets.csv",
    "NBL_2023-2024_All_Markets.csv",
    "NBL_2024-2025_All_Markets.csv",

    # Horse racing — ANZ thoroughbreds monthly (2026 is CSVs, prior years are zips)
    "ANZ_Thoroughbreds_2026_01.csv",
    "ANZ_Thoroughbreds_2026_02.csv",
    "ANZ_Thoroughbreds_2026_03.csv",
]

def main():
    with httpx.Client(headers={"User-Agent":"research"}, timeout=600, follow_redirects=True) as c:
        total_bytes = 0
        for fname in FILES:
            out = RAW / fname
            if out.exists() and out.stat().st_size > 1024:
                print(f"  [skip] {fname} ({out.stat().st_size:,} bytes)")
                total_bytes += out.stat().st_size
                continue
            url = BASE + fname
            try:
                r = c.get(url)
                if r.status_code != 200:
                    print(f"  [{r.status_code}] {fname}")
                    continue
                out.write_bytes(r.content)
                total_bytes += len(r.content)
                print(f"  [{r.status_code}] {fname}  ({len(r.content):,} bytes)")
            except Exception as e:
                print(f"  [ERR] {fname}  {e}")
            time.sleep(0.3)
    print(f"\ntotal: {total_bytes/1024/1024:.1f} MB across {len(FILES)} files")

if __name__ == "__main__":
    main()
