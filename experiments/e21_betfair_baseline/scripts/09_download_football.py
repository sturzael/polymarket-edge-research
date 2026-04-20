"""Download football-data.co.uk odds (includes BFE/BFH/BFA - Betfair closing odds for home/draw/away).

This gives us a second Betfair sports calibration sample with closing (pre-kickoff) prices
for English league football. Spans many seasons (1993-present) but only recent seasons have Betfair columns.
"""
from __future__ import annotations
import httpx, pathlib, time

DATA = pathlib.Path(__file__).parent.parent / "data"
RAW = DATA / "raw_football"
RAW.mkdir(exist_ok=True, parents=True)

# Season codes from the HTML: 2526 is 2025/26, 2425 is 2024/25, etc.
# We want recent seasons with Betfair odds (roughly 2019/20 onwards).
SEASONS = ["2526", "2425", "2324", "2223", "2122", "2021", "1920"]
LEAGUES = {
    "E0": "England_Premier",
    "E1": "England_Championship",
    "E2": "England_L1",
    "E3": "England_L2",
    "SP1": "Spain_LaLiga",
    "D1": "Germany_Bundesliga",
    "I1": "Italy_SerieA",
    "F1": "France_Ligue1",
}

def main():
    with httpx.Client(headers={"User-Agent":"research"}, timeout=120, follow_redirects=True) as c:
        for season in SEASONS:
            for code, name in LEAGUES.items():
                url = f"https://www.football-data.co.uk/mmz4281/{season}/{code}.csv"
                out = RAW / f"{name}_{season}.csv"
                if out.exists() and out.stat().st_size > 1024:
                    print(f"  [skip] {out.name}")
                    continue
                try:
                    r = c.get(url)
                    if r.status_code != 200:
                        print(f"  [{r.status_code}] {out.name}")
                        continue
                    out.write_bytes(r.content)
                    print(f"  [{r.status_code}] {out.name}  ({len(r.content):,} bytes)")
                except Exception as e:
                    print(f"  [ERR] {out.name}  {e}")
                time.sleep(0.2)

if __name__ == "__main__":
    main()
