"""Weather-market viability check (v2 — tighter filter).

Counts active weather markets on Polymarket + their volume distribution +
typical resolution cadence (daily/weekly/one-off).

Filter: require slug/question to contain a genuine WEATHER keyword (not sports
team names like "carolina-hurricanes"). Exclude known false-positive patterns.

Output: data/weather_viability.json + stdout summary.

Decision rule from the user:
  - PROMISING: >=50 genuinely-weather markets, median volume >=$10k,
               resolving daily/weekly
  - SKIP: handful of markets with thin volume
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

import httpx

DATA_DIR = Path(__file__).parent / "data"
OUT = DATA_DIR / "weather_viability.json"
GAMMA = "https://gamma-api.polymarket.com"

# Tighter weather keywords: phrases and specific terms unlikely to collide
# with sports/politics. "hurricane" alone collides with Carolina Hurricanes;
# "storm" collides with Seattle Storm. We require context.
WEATHER_PATTERNS = [
    r"\bnyc[-_ ]?temp", r"\bla[-_ ]?temp", r"\btemperature\b",
    r"\brainfall\b", r"\bprecipitation\b", r"\bsnowfall\b",
    r"\bwindspeed\b", r"\bwind[-_ ]?speed\b",
    r"\bhurricane season\b", r"\bnamed storm forms\b",
    r"\bcategory[-_ ]?[0-9]+ hurricane\b", r"\bhurricane[-_ ]?(\d|makes landfall|category)",
    r"\bwildfire\b", r"\bheat[-_ ]?wave\b", r"\bcold[-_ ]?snap\b",
    r"\bsnowstorm\b", r"\btornado\b", r"\bcyclone\b", r"\btyphoon\b",
    r"\bmonsoon\b", r"\bblizzard\b", r"\bdrought\b",
    r"\bdegrees? (celsius|fahrenheit|f)\b",
    r"\b(celsius|fahrenheit|kelvin)\b",
    r"\b(high|low|avg) (temp|temperature)\b",
    r"\bwill [a-z]+ (rain|snow) on\b",
]
WEATHER_RE = re.compile("|".join(WEATHER_PATTERNS), re.IGNORECASE)

# Known false-positive patterns to exclude (sports/politics/entertainment)
EXCLUDE_PATTERNS = [
    r"\b(nhl|nba|mlb|mls|nfl|epl|laliga)\b",
    r"\bceasefire\b", r"\bpeace (deal|parlay|plan)\b",
    r"\bstanley cup\b", r"\beurovision\b",
    r"\b(win|lose) the \d{4}\b",
    r"\bhurricanes\b(?!\s+(season|category|make))",  # "hurricanes" plural = team
]
EXCLUDE_RE = re.compile("|".join(EXCLUDE_PATTERNS), re.IGNORECASE)


def fetch_markets_paginated(client: httpx.Client, params: dict, max_pages: int = 50) -> list[dict]:
    out = []
    offset = 0
    for _ in range(max_pages):
        r = client.get(f"{GAMMA}/markets",
                       params={**params, "limit": 500, "offset": offset},
                       timeout=30)
        if r.status_code != 200:
            break
        batch = r.json()
        if not batch:
            break
        out.extend(batch)
        if len(batch) < 500:
            break
        offset += 500
    return out


def looks_weather(m: dict) -> bool:
    slug = str(m.get("slug") or "")
    question = str(m.get("question") or "")
    fields = f"{slug} {question}"
    if EXCLUDE_RE.search(fields):
        return False
    return bool(WEATHER_RE.search(fields))


def parse_ts(raw) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except Exception:
        return None


def classify_cadence(slug: str) -> str:
    """Heuristic: slug patterns → daily/weekly/monthly/one-off."""
    s = (slug or "").lower()
    if re.search(r"-\d{4}-\d{2}-\d{2}", s):
        return "daily"
    if re.search(r"week-of-|\d{1,2}-(mon|tue|wed|thu|fri|sat|sun)-", s):
        return "weekly"
    if re.search(r"-(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)-", s):
        return "monthly"
    return "one-off"


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with httpx.Client() as client:
        print("fetching active markets from gamma (paginated)...")
        active = fetch_markets_paginated(client, {"active": "true", "closed": "false"})
        print(f"  {len(active):,} active-open markets total")

        weather = [m for m in active if looks_weather(m)]
        print(f"  {len(weather)} match tightened weather filter")

        print("\nfetching recent closed markets for cadence sample...")
        recent_closed = fetch_markets_paginated(
            client, {"closed": "true", "order": "endDate", "ascending": "false"},
            max_pages=20,
        )
        recent_weather_closed = [m for m in recent_closed if looks_weather(m)]
        print(f"  {len(recent_closed):,} recent closed markets; "
              f"{len(recent_weather_closed)} weather")

    now = datetime.now(timezone.utc)

    volumes_active = sorted([float(m.get("volume") or 0) for m in weather])
    cadence_counter = Counter()
    days_to_resolution = []
    event_slugs = Counter()

    for m in weather:
        cadence_counter[classify_cadence(m.get("slug", ""))] += 1
        event_slugs[m.get("eventSlug") or "(none)"] += 1
        ed = parse_ts(m.get("endDate"))
        if ed:
            delta = (ed - now).total_seconds() / 86400.0
            if delta > -1:
                days_to_resolution.append(round(delta, 1))

    resolved_windows = []
    for m in recent_weather_closed:
        cd = parse_ts(m.get("createdAt") or m.get("startDate"))
        ed = parse_ts(m.get("endDate"))
        if cd and ed:
            resolved_windows.append(round((ed - cd).total_seconds() / 86400.0, 2))

    top_by_volume = sorted(weather, key=lambda m: -float(m.get("volume") or 0))[:20]
    sample = [
        {
            "slug": m.get("slug"),
            "question": (m.get("question") or "")[:80],
            "volume": round(float(m.get("volume") or 0), 2),
            "end_date": m.get("endDate"),
            "event_slug": m.get("eventSlug"),
            "cadence": classify_cadence(m.get("slug", "")),
        }
        for m in top_by_volume
    ]

    q_vol = {
        "n": len(volumes_active),
        "p10": volumes_active[int(0.10 * len(volumes_active))] if volumes_active else 0,
        "p50": median(volumes_active) if volumes_active else 0,
        "p90": volumes_active[int(0.90 * len(volumes_active))] if volumes_active else 0,
        "max": max(volumes_active) if volumes_active else 0,
        "total": sum(volumes_active),
    }

    # Also compute distribution for daily-cadence subset only (the genuinely
    # recurring ones — best candidates if the vertical exists)
    daily_only = [m for m in weather if classify_cadence(m.get("slug","")) == "daily"]
    daily_vols = sorted([float(m.get("volume") or 0) for m in daily_only])
    q_vol_daily = {
        "n": len(daily_only),
        "p50": median(daily_vols) if daily_vols else 0,
        "p90": daily_vols[int(0.90 * len(daily_vols))] if daily_vols else 0,
        "total": sum(daily_vols),
    }

    promising = (
        len(weather) >= 50
        and q_vol["p50"] >= 10_000
        and (cadence_counter["daily"] + cadence_counter["weekly"]) >= len(weather) / 2
    )

    result = {
        "generated_at": now.isoformat(),
        "n_active_total": len(active),
        "n_weather_active": len(weather),
        "n_recent_closed_total": len(recent_closed),
        "n_weather_closed": len(recent_weather_closed),
        "volume_active": q_vol,
        "volume_active_daily_subset": q_vol_daily,
        "cadence": dict(cadence_counter),
        "days_to_resolution_p50": median(days_to_resolution) if days_to_resolution else None,
        "resolved_window_p50_days": median(resolved_windows) if resolved_windows else None,
        "top_event_slugs": event_slugs.most_common(15),
        "top_by_volume_sample": sample,
        "decision": "PROMISING" if promising else "SKIP",
    }
    OUT.write_text(json.dumps(result, indent=2, default=str))

    print(f"\n=== WEATHER MARKET VIABILITY (v2) ===")
    print(f"  active weather markets:   {len(weather)}")
    print(f"  overall volume p50/p90:   ${q_vol['p50']:,.0f} / ${q_vol['p90']:,.0f}")
    print(f"  total active volume:      ${q_vol['total']:,.0f}")
    print(f"  cadence:                  {dict(cadence_counter)}")
    print(f"  DAILY-cadence subset:     n={q_vol_daily['n']}  "
          f"p50_vol=${q_vol_daily['p50']:,.0f}  total=${q_vol_daily['total']:,.0f}")
    print(f"  days to resolution (p50): {result['days_to_resolution_p50']}")
    print(f"  resolved window (p50):    {result['resolved_window_p50_days']} days")
    print(f"  TOP EVENTS:")
    for ev, n in event_slugs.most_common(10):
        print(f"    {n:>4}  {ev}")
    print(f"  TOP BY VOLUME (first 10):")
    for s in sample[:10]:
        print(f"    ${s['volume']:>10,.0f}  {s['cadence']:<7}  {s['slug']}")
    print(f"\n  DECISION: {result['decision']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
