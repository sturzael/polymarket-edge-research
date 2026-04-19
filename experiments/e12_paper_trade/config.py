"""All economic + operational assumptions for e12. Parameterized so report.py
can re-score at different fee rates / sample sizes."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

# --- Fees (e13/02 measured fee=0 across n=143 sports post-resolution trades) ---
FEE_BPS = 0
# Phase 0b shakedown verifies pm-trader bills $0 on a live sports buy.
# If pm-trader insists on a non-zero rate, see plan Phase 0b option (c).

# --- Poll cadence (Gamma /markets allows 300/10s = 30/s; we use 0.5/s) ---
POLL_INTERVAL_S = 2

# --- Sample + run bounds ---
SAMPLE_TARGET_TRADES = 75       # per cell; full-sample bar
EARLY_KILL_AFTER_TRADES = 20    # per cell; asymmetric kill-only gate
MAX_RUN_HOURS = 168             # 7-day hard stop from daemon start

# --- Account setup: 2 size_models × 2 entry caps = 4 cells (2x2 grid) ---
SEED_BALANCE = 10_000.0
ENTRY_TARGET_CAPS = (0.95, 0.97)
SIZE_MODELS = ("fixed_100", "depth_scaled")
ACCOUNTS = [
    ("sports_lag", "fixed_100",   0.95),
    ("sports_lag", "fixed_100",   0.97),
    ("sports_lag", "depth_scaled", 0.95),
    ("sports_lag", "depth_scaled", 0.97),
]

def cell_name(strategy: str, size_model: str, entry_cap: float) -> str:
    return f"{strategy}__{size_model}__cap{int(entry_cap * 100):02d}"

# --- Entry sizing ---
FIXED_USD_SIZE = 100.0          # for fixed_100 cells
DEPTH_SCALED_FRAC = 0.25        # for depth_scaled cells: take 25% of ask depth at target

# --- Risk gates (Octagon-derived) ---
MAX_DRAWDOWN_PER_CELL = 0.20    # kill cell at 20% drawdown
MAX_OPEN_PER_EVENT = 3          # max concurrent positions per event_id

# --- Detection windows ---
SPORTS_SLUG_PATTERNS = (
    "atp-", "wta-", "nba-", "nfl-", "nhl-", "mlb-",
    "cricipl-", "ufc-", "mls-", "wnba-",
)
PRICE_LO_FOR_DETECTION = 0.95   # detection floor; per-cell entry_cap is the ceiling
LAST_TRADE_RECENCY_MIN = 30     # ignore detections older than this
END_DATE_WITHIN_HOURS = 24      # only catch markets resolving in next N hours
                                # (excludes futures like Vezina/Stanley-Cup that
                                # resolve in weeks-months — needed for today/overnight verification)
MIN_VOLUME_24H_USD = 1_000      # skip near-dead markets with no recent trading

# --- V2 cutover ---
V2_CUTOVER_PAUSE_AT = datetime(2026, 4, 22, 9, 30, tzinfo=timezone.utc)
V2_CUTOVER_RESUME_NO_EARLIER_THAN = datetime(2026, 4, 23, 10, 0, tzinfo=timezone.utc)

# --- Paths ---
HERE = Path(__file__).parent
SIDECAR_DB = HERE / "sidecar.db"
CELLS_DIR = HERE / "cells"
SCHEMA_SQL = HERE / "schema.sql"

# --- Rate limits (per docs.polymarket.com/quickstart/introduction/rate-limits) ---
GAMMA_GENERAL_LIMIT_PER_10S = 4000
GAMMA_MARKETS_LIMIT_PER_10S = 300
GAMMA_EVENTS_LIMIT_PER_10S = 500
