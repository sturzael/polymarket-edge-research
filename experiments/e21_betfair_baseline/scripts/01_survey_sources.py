"""Survey publicly-accessible Betfair historical data sources.

Fetches candidate pages and catalogs what's there. Writes HTML dumps to data/
for later inspection.
"""
from __future__ import annotations
import httpx
import pathlib
import time

DATA = pathlib.Path(__file__).parent.parent / "data"
DATA.mkdir(exist_ok=True, parents=True)

CANDIDATES = [
    # Betfair datascientists hub — known to host CSVs
    ("hub_datalist", "https://betfair-datascientists.github.io/data/dataListing/"),
    ("hub_historic", "https://betfair-datascientists.github.io/data/usingHistoricDataSite/"),
    # Academic / community repositories
    ("kaggle_1wk", "https://www.kaggle.com/datasets/zygmunt/betfair-sports"),
    ("kaggle_bsp", "https://www.kaggle.com/datasets/eonsky/betfair-sp"),
    # Official
    ("official_historicdata", "https://historicdata.betfair.com/"),
    # Free published odds (non-Betfair but classic FLB source): football-data.co.uk
    ("footballdata_main", "https://www.football-data.co.uk/data.php"),
    ("footballdata_eng", "https://www.football-data.co.uk/englandm.php"),
    # Horse racing free data: Betfair AU publishes free BSP CSVs
    ("betfair_au_bsp", "https://www.betfair.com.au/hub/racing/horse-racing/racing-data-sets/"),
    ("betfair_au_results", "https://promo.betfair.com/betfairsp/prices/"),
    ("betfair_data_archive", "https://www.betfair.com.au/hub/tools/models/bsp-ratings/"),
]


def main():
    headers = {"User-Agent": "Mozilla/5.0 (research)"}
    results = []
    with httpx.Client(headers=headers, timeout=30, follow_redirects=True) as c:
        for name, url in CANDIDATES:
            try:
                r = c.get(url)
                status = r.status_code
                size = len(r.content)
                out = DATA / f"survey_{name}.html"
                out.write_bytes(r.content)
                results.append((name, url, status, size))
                print(f"  [{status}] {name}  {size:>9,} bytes  {url}")
            except Exception as e:
                print(f"  [ERR] {name}  {e}  {url}")
                results.append((name, url, -1, 0))
            time.sleep(0.5)
    import json
    (DATA / "survey.json").write_text(json.dumps(
        [{"name": n, "url": u, "status": s, "size": sz} for n, u, s, sz in results],
        indent=2,
    ))


if __name__ == "__main__":
    main()
