"""Download one small CSV from the datascientists hub and inspect schema.

We want to verify:
- Does it contain pre-race prices with timestamps?
- Does it contain resolution outcome?
- Can we identify T-X anchor time and snapshot prices there?
"""
from __future__ import annotations
import httpx, pathlib, io, sys

DATA = pathlib.Path(__file__).parent.parent / "data"
BASE = "https://betfair-datascientists.github.io/data/assets/"

PROBE_FILES = [
    # Start small — match_odds files are much smaller than All_Markets
    "AFLW_2021_Match_Odds.csv",
    "A-League_2020-2021_Match_Odds.csv",
    "NRL_2021_Match_Odds.csv",
    "BBL10_Match_Odds.csv",
]

def main():
    headers = {"User-Agent": "Mozilla/5.0 (research)"}
    with httpx.Client(headers=headers, timeout=60, follow_redirects=True) as c:
        for fname in PROBE_FILES:
            url = BASE + fname
            try:
                r = c.get(url)
                if r.status_code != 200:
                    print(f"  [{r.status_code}] {fname}  ({len(r.content):,} bytes)")
                    continue
                out = DATA / fname
                out.write_bytes(r.content)
                print(f"  [{r.status_code}] {fname}  ({len(r.content):,} bytes) -> {out}")
                # Print header and first 3 rows
                text = r.content.decode("utf-8", errors="replace")
                lines = text.splitlines()[:6]
                print(f"    schema (first 6 lines):")
                for ln in lines:
                    print(f"      {ln[:240]}")
                print()
            except Exception as e:
                print(f"  [ERR] {fname}  {e}")

if __name__ == "__main__":
    main()
