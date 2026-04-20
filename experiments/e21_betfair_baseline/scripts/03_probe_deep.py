"""Probe deeper schema — AFL all markets, horse racing."""
from __future__ import annotations
import httpx, pathlib

DATA = pathlib.Path(__file__).parent.parent / "data"
BASE = "https://betfair-datascientists.github.io/data/assets/"

FILES = [
    "AFL_2021_All_Markets.csv",          # deeper schema maybe
    "ANZ_Thoroughbreds_2026_01.csv",     # horse racing, most recent
]

def main():
    with httpx.Client(headers={"User-Agent":"research"}, timeout=300, follow_redirects=True) as c:
        for fname in FILES:
            url = BASE + fname
            r = c.get(url)
            if r.status_code != 200:
                print(f"  [{r.status_code}] {fname}")
                continue
            out = DATA / fname
            out.write_bytes(r.content)
            print(f"  [{r.status_code}] {fname}  ({len(r.content):,} bytes) -> {out}")

if __name__ == "__main__":
    main()
