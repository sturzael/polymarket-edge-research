"""Unified game-end stream from ESPN + nba_api + MLB-StatsAPI.

For v1 we expose a simple polling-based async generator. Each yield is a
GameEndEvent(sport, home, away, winner, ended_at). Consumers (detector.py)
match the (home, away, date) tuple against Polymarket sports markets.

The stream degrades gracefully: if ESPN endpoints break, it just emits
nothing from that sport — book-poll path still catches most markets.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import AsyncIterator

logger = logging.getLogger(__name__)

POLL_INTERVAL_S = 15  # how often to ping each feed for new finals


@dataclass
class GameEndEvent:
    sport: str          # 'NFL' | 'NBA' | 'MLB' | 'NHL' | 'soccer' | etc.
    home: str
    away: str
    winner: str         # 'home' | 'away' | 'draw'
    home_score: int | None
    away_score: int | None
    ended_at: datetime
    raw: dict


_seen: set[str] = set()  # dedup key: f"{sport}:{date}:{home}:{away}"


def _dedup_key(sport: str, home: str, away: str, ended_at: datetime) -> str:
    return f"{sport}:{ended_at.date().isoformat()}:{home.lower()}:{away.lower()}"


async def _poll_espn() -> list[GameEndEvent]:
    """ESPN hidden endpoints: site.api.espn.com/apis/site/v2/sports/.../scoreboard
    Multi-sport. Returns finals (status STATUS_FINAL or 'Final') from today."""
    try:
        import httpx
    except Exception:
        return []
    sports_paths = {
        "NFL":    "/football/nfl/scoreboard",
        "NBA":    "/basketball/nba/scoreboard",
        "MLB":    "/baseball/mlb/scoreboard",
        "NHL":    "/hockey/nhl/scoreboard",
        "WNBA":   "/basketball/wnba/scoreboard",
        "NCAAFB": "/football/college-football/scoreboard",
    }
    out: list[GameEndEvent] = []
    base = "https://site.api.espn.com/apis/site/v2/sports"
    async with httpx.AsyncClient(timeout=8.0) as client:
        for sport, path in sports_paths.items():
            try:
                r = await client.get(base + path)
                if r.status_code != 200:
                    continue
                data = r.json()
                for ev in data.get("events", []):
                    status = (ev.get("status", {}).get("type", {}) or {})
                    if not (status.get("completed") or status.get("name") == "STATUS_FINAL"):
                        continue
                    comps = ev.get("competitions", [{}])[0]
                    teams = comps.get("competitors", [])
                    if len(teams) != 2:
                        continue
                    home = next((t for t in teams if t.get("homeAway") == "home"), teams[0])
                    away = next((t for t in teams if t.get("homeAway") == "away"), teams[1])
                    h_score = int(home.get("score") or 0)
                    a_score = int(away.get("score") or 0)
                    if h_score == a_score:
                        winner = "draw"
                    else:
                        winner = "home" if h_score > a_score else "away"
                    ended_at_raw = ev.get("date") or comps.get("date")
                    try:
                        ended_at = datetime.fromisoformat(ended_at_raw.replace("Z", "+00:00")) if ended_at_raw else datetime.now(timezone.utc)
                    except Exception:
                        ended_at = datetime.now(timezone.utc)
                    h_name = home.get("team", {}).get("displayName") or home.get("team", {}).get("name") or "?"
                    a_name = away.get("team", {}).get("displayName") or away.get("team", {}).get("name") or "?"
                    out.append(GameEndEvent(
                        sport=sport, home=h_name, away=a_name, winner=winner,
                        home_score=h_score, away_score=a_score, ended_at=ended_at,
                        raw={"id": ev.get("id"), "espn_short_name": ev.get("shortName")},
                    ))
            except Exception as e:
                logger.warning(f"espn {sport} feed error: {e}")
    return out


async def listen() -> AsyncIterator[GameEndEvent]:
    """Async generator yielding fresh GameEndEvents. Polls every POLL_INTERVAL_S."""
    while True:
        try:
            events = await _poll_espn()
        except Exception as e:
            logger.warning(f"sports_feeds poll error: {e}")
            events = []
        for ev in events:
            key = _dedup_key(ev.sport, ev.home, ev.away, ev.ended_at)
            if key in _seen:
                continue
            _seen.add(key)
            yield ev
        await asyncio.sleep(POLL_INTERVAL_S)
