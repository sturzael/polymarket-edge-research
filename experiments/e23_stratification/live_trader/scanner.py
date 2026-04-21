"""Polymarket FLB live scanner.

Polls gamma /markets every N minutes, filters to MLB/NBA/NFL/NHL game-outcome
markets approaching T-7d ±12h at price ∈ [0.55, 0.60) with ≥$5k window volume
and ≤14d lifespan, and flags each qualifying market once per bucket-entry.

Every flag is appended to `data/flagged_markets.jsonl` and pushed to ntfy.sh.
The `phase` field in config.json is read fresh each poll so you can flip between
"observe" (no trading) and "live" (trade as flags fire) without restarting.

Run in tmux:
    uv run python experiments/e23_stratification/live_trader/scanner.py
"""
from __future__ import annotations

import ast
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

HERE = Path(__file__).parent
CONFIG_PATH = HERE / "config.json"
DATA_DIR = HERE / "data"
DATA_DIR.mkdir(exist_ok=True)
FLAGS_JSONL = DATA_DIR / "flagged_markets.jsonl"
STATE_JSON = DATA_DIR / "seen_markets.json"

GAMMA = "https://gamma-api.polymarket.com"
DATA_API = "https://data-api.polymarket.com"

# --- Category classifier (reused from e16/01_markets_audit.py) -----------
CATEGORY_RULES = [
    ("sports_nfl",    re.compile(r"\b(nfl|super[-_ ]?bowl|afc|nfc|packers|49ers|cowboys|eagles|ravens|chiefs)\b", re.I)),
    ("sports_nba",    re.compile(r"\b(nba|warriors|celtics|lakers|bucks|nets|knicks|suns|heat|thunder|mavericks|raptors|sixers|pacers|bulls)\b|\bnba-\w+|-nba-", re.I)),
    ("sports_mlb",    re.compile(r"\b(mlb|world[-_ ]?series|yankees|dodgers|red[-_ ]?sox|astros|mets|phillies|braves|rays|cubs)\b", re.I)),
    ("sports_nhl",    re.compile(r"\b(nhl|stanley[-_ ]?cup|bruins|leafs|avalanche|oilers|canadiens)\b", re.I)),
    ("sports_soccer", re.compile(r"\b(epl|premier[-_ ]?league|la[-_ ]?liga|uefa|champions[-_ ]?league|europa|bundesliga|serie[-_ ]?a|mls|fifa|world[-_ ]?cup|liverpool|arsenal|real[-_ ]?madrid|barcelona|psg|bayern|juventus|chelsea|spurs)\b", re.I)),
    ("sports_ufc_boxing", re.compile(r"\b(ufc|mma|boxing|fighter|paul[-_ ]?vs|fury[-_ ]?vs)\b", re.I)),
    ("sports_tennis", re.compile(r"\b(tennis|atp|wta|djokovic|alcaraz|sinner|us[-_ ]?open|wimbledon|french[-_ ]?open|australian[-_ ]?open)\b", re.I)),
    ("sports_f1",     re.compile(r"\b(formula[-_ ]?1|f1[-_ ]?|verstappen|hamilton|leclerc|norris|piastri|grand[-_ ]?prix)\b", re.I)),
]

# --- Sub-category classifier (distilled from Agent E's rules) ------------
FUTURES_KEYWORDS = [
    "championship", "mvp", "world-series", "super-bowl", "conference",
    "drivers-champion", "constructors-champion", "coach-of-the-year",
    "rookie-of-the-year", "finals-mvp", "nfl-playoffs", "win-the-afc",
    "win-the-nfc", "win-the-al", "win-the-nl", "top-goalscorer",
    "reach-the-quarterfinals", "reach-the-semifinals", "to-advance",
    "top-fantasy", "conn-smythe", "win-group", "advance-in", "advance-to",
    "make-the", "win-gold", "gold-medal", "series-winner",
]
PROPS_KEYWORDS = [
    "pole-position", "coin-toss", "first-goal", "first-touchdown",
    "halftime-show", "perform-", "trump-attend", "elon-attend",
    "fastest-lap", "draft-pick", "be-the-third-qb", "be-drafted",
]
SPREAD_RE = re.compile(r"-(spread|handicap)-")
TOTALS_RE = re.compile(r"(-total-\d|-match-total|-ou-|-over-under-|-over-\d|-under-\d|-btts|\d+pt\d+$)")
# game-outcome: has a date OR h2h pattern, AFTER exclusion keywords have fired
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
H2H_RE = re.compile(r"(will|can)-.+-(beat|defeat)-|-vs-|will-.+-win-his-(boxing|fight|mma)")

def classify_sport(slug: str, question: str) -> str:
    text = f"{slug} {question}".lower()
    for label, pattern in CATEGORY_RULES:
        if pattern.search(text):
            return label
    return "other"

def is_game_outcome(slug: str) -> bool:
    s = slug.lower()
    if SPREAD_RE.search(s): return False
    if TOTALS_RE.search(s): return False
    if any(k in s for k in PROPS_KEYWORDS): return False
    if any(k in s for k in FUTURES_KEYWORDS): return False
    return bool(DATE_RE.search(s) or H2H_RE.search(s))

# --- Helpers --------------------------------------------------------------
def parse_ts(s: str | None) -> int | None:
    """Parse Polymarket timestamps. Handles:
        '2026-04-28T19:00:00Z'       (ISO with Z)
        '2026-04-28T19:00:00+00:00'  (ISO with offset)
        '2026-04-20 22:45:00+00'     (gameStartTime: space-separated, +00)
    """
    if not s: return None
    try:
        s2 = s.replace(" ", "T")
        if s2.endswith("Z"):
            s2 = s2[:-1] + "+00:00"
        elif s2.endswith("+00"):
            s2 = s2 + ":00"
        return int(datetime.fromisoformat(s2).timestamp())
    except Exception:
        return None

# --- Config + state -------------------------------------------------------
def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text())

def load_state() -> dict:
    if STATE_JSON.exists():
        return json.loads(STATE_JSON.read_text())
    return {}

def save_state(state: dict) -> None:
    STATE_JSON.write_text(json.dumps(state, indent=2, default=str))

# --- Gamma API ------------------------------------------------------------
def fetch_active_markets(client: httpx.Client) -> list[dict]:
    """Page through gamma /markets for all active non-closed sports-ish markets."""
    out: list[dict] = []
    offset = 0
    while True:
        r = client.get(f"{GAMMA}/markets", params={
            "closed": "false", "active": "true", "limit": 500, "offset": offset,
        }, timeout=30)
        r.raise_for_status()
        batch = r.json()
        if not batch: break
        out.extend(batch)
        if len(batch) < 500: break
        offset += 500
        if offset > 10_000: break  # safety
    return out

def parse_outcome_prices(raw) -> tuple[float, float] | None:
    if raw is None: return None
    s = raw if isinstance(raw, str) else (raw.decode() if isinstance(raw, bytes) else None)
    if not s: return None
    try:
        v = ast.literal_eval(s)
        if isinstance(v, (list, tuple)) and len(v) == 2:
            return float(v[0]), float(v[1])
    except Exception:
        return None
    return None

def yes_price(market: dict) -> float | None:
    prices = parse_outcome_prices(market.get("outcomePrices"))
    outcomes = parse_outcome_prices(market.get("outcomes")) if False else None
    if prices is None: return None
    # outcomes is typically ["Yes","No"]; prices[0] is Yes price
    outs_raw = market.get("outcomes")
    try:
        outs = ast.literal_eval(outs_raw) if isinstance(outs_raw, str) else outs_raw
    except Exception:
        outs = None
    if outs and len(outs) == 2:
        if str(outs[0]).strip().lower() in ("yes", "y"):
            return prices[0]
        if str(outs[1]).strip().lower() in ("yes", "y"):
            return prices[1]
    return prices[0]  # default assumption

def fetch_window_volume(client: httpx.Client, condition_id: str,
                         target_ts: int, window_hours: float) -> float:
    """USD notional traded in ±window_hours around target_ts (taker prints only)."""
    offset = 0
    total = 0.0
    window_s = int(window_hours * 3600)
    lo, hi = target_ts - window_s, target_ts + window_s
    for _ in range(6):  # max ~3000 trades scanned
        try:
            r = client.get(f"{DATA_API}/trades", params={
                "takerOnly": "true", "market": condition_id,
                "limit": 500, "offset": offset,
            }, timeout=15)
        except Exception:
            return total
        if r.status_code != 200: return total
        batch = r.json()
        if not batch: break
        for t in batch:
            ts = int(t.get("timestamp", 0))
            if lo <= ts <= hi:
                try:
                    total += float(t.get("size") or 0) * float(t.get("price") or 0)
                except Exception:
                    pass
        if len(batch) < 500: break
        if batch and int(batch[-1].get("timestamp", 0)) < lo:
            break
        offset += 500
    return total

# --- ntfy -----------------------------------------------------------------
def ntfy_send(topic: str, title: str, message: str,
              click_url: str | None = None, priority: str = "default") -> None:
    if not topic or topic.startswith("REPLACE_ME"):
        print(f"  [ntfy skipped — topic not configured]")
        return
    headers = {"Title": title, "Priority": priority}
    if click_url:
        headers["Click"] = click_url
    try:
        httpx.post(f"https://ntfy.sh/{topic}", data=message.encode("utf-8"),
                    headers=headers, timeout=10)
    except Exception as e:
        print(f"  [ntfy failed: {e}]")

# --- Main scan ------------------------------------------------------------
def scan_once(client: httpx.Client, config: dict, state: dict) -> int:
    """Returns number of new flags emitted this pass."""
    now = datetime.now(timezone.utc)
    now_ts = int(now.timestamp())
    bucket_lo = float(config["bucket_low"])
    bucket_hi = float(config["bucket_high"])
    allow = set(config["sports_allowlist"])
    max_lifespan = float(config["max_lifespan_days"])
    min_vol = float(config["min_window_volume_usd"])
    offset_days = float(config["anchor_offset_days"])
    window_hours = float(config["anchor_window_hours"])
    phase = config.get("phase", "observe")

    markets = fetch_active_markets(client)
    print(f"  fetched {len(markets):,} active markets")

    target_days_lo = offset_days - window_hours / 24.0
    target_days_hi = offset_days + window_hours / 24.0

    n_flags = 0
    n_candidates = 0
    for m in markets:
        slug = m.get("slug") or ""
        question = m.get("question") or ""
        cid = m.get("conditionId") or ""
        if not (slug and cid): continue

        sport = classify_sport(slug, question)
        if sport not in allow: continue

        if not is_game_outcome(slug): continue

        # Use gameStartTime (actual event time) — NOT endDate.
        # MLB / some sports have endDate = gameStartTime + settlement delay (≈7d);
        # filtering on endDate would false-positive on every post-game MLB market.
        # Fallback to endDate only if gameStartTime missing (props without a game).
        game_start_raw = m.get("gameStartTime") or m.get("endDate")
        end_date_raw = m.get("endDate")
        created_at = m.get("createdAt")
        if not game_start_raw: continue
        try:
            event_ts = parse_ts(game_start_raw)
            if event_ts is None: continue
        except Exception:
            continue
        days_to_event = (event_ts - now_ts) / 86400.0
        if not (target_days_lo <= days_to_event <= target_days_hi):
            continue  # not in T-7d window

        if created_at:
            ct = parse_ts(created_at)
            if ct is None: continue
            lifespan = (event_ts - ct) / 86400.0
            if lifespan > max_lifespan: continue
        else:
            continue

        price = yes_price(m)
        if price is None or not (bucket_lo <= price < bucket_hi):
            # Track transitions: if we'd previously flagged this and price left, allow re-entry later
            if cid in state and state[cid].get("in_bucket"):
                state[cid]["in_bucket"] = False
            continue

        n_candidates += 1

        # Volume gate (expensive, only for candidates passing cheap filters)
        target_ts = event_ts - int(offset_days * 86400)
        vol = fetch_window_volume(client, cid, target_ts, window_hours)
        if vol < min_vol:
            if cid in state and state[cid].get("in_bucket"):
                state[cid]["in_bucket"] = False
            continue

        # Dedup: flag only on out→in transition (or first sighting)
        prev_in = state.get(cid, {}).get("in_bucket", False)
        if prev_in:
            state[cid]["last_seen"] = now.isoformat()
            state[cid]["last_price"] = price
            continue

        # Emit flag
        polymarket_url = f"https://polymarket.com/market/{slug}"
        flag = {
            "flagged_at": now.isoformat(),
            "phase": phase,
            "condition_id": cid,
            "slug": slug,
            "question": question,
            "sport": sport,
            "yes_price": round(price, 4),
            "days_to_event": round(days_to_event, 3),
            "lifespan_days": round(lifespan, 3),
            "window_volume_usd": round(vol, 2),
            "game_start_time": game_start_raw,
            "end_date": end_date_raw,
            "created_at": created_at,
            "polymarket_url": polymarket_url,
        }
        with FLAGS_JSONL.open("a") as f:
            f.write(json.dumps(flag) + "\n")

        state[cid] = {
            "in_bucket": True,
            "first_flagged_at": now.isoformat(),
            "last_seen": now.isoformat(),
            "last_price": price,
            "phase_at_flag": phase,
        }

        prefix = "[OBSERVE]" if phase == "observe" else "[LIVE]"
        title = f"{prefix} {sport.replace('sports_','').upper()} · {price:.3f} · T-{days_to_event:.1f}d"
        body = (f"{question}\n"
                f"${vol/1000:.1f}k window vol · lifespan {lifespan:.1f}d\n"
                f"Tap to open Polymarket")
        priority = "default" if phase == "observe" else "high"
        ntfy_send(config["ntfy_topic"], title, body, polymarket_url, priority)
        print(f"  FLAG [{phase}] {slug}  price={price:.3f}  vol=${vol:.0f}  "
              f"T-{days_to_event:.2f}d")
        n_flags += 1

    print(f"  candidates_in_bucket={n_candidates}  flags_emitted={n_flags}")
    return n_flags

def main_loop() -> int:
    print(f"scanner starting — state file: {STATE_JSON}")
    while True:
        try:
            config = load_config()
        except Exception as e:
            print(f"config load failed: {e} — sleeping 60s")
            time.sleep(60); continue
        state = load_state()
        ts = datetime.now(timezone.utc).isoformat()
        phase = config.get("phase", "observe")
        print(f"\n--- poll {ts}  phase={phase} ---")
        try:
            with httpx.Client() as client:
                scan_once(client, config, state)
        except Exception as e:
            print(f"  scan error: {e}")
        save_state(state)
        interval = int(config.get("poll_interval_seconds", 900))
        print(f"  sleeping {interval}s")
        time.sleep(interval)

if __name__ == "__main__":
    sys.exit(main_loop() or 0)
