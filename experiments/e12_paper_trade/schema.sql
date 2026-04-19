-- e12 paper-trade sidecar. pm-trader owns trades / fees / portfolio per cell;
-- we own the per-strategy metadata it doesn't model.

CREATE TABLE IF NOT EXISTS position_context (
    pm_trade_id        TEXT PRIMARY KEY,
    account            TEXT NOT NULL,            -- 'sports_lag__fixed_100__cap95' etc.
    strategy           TEXT NOT NULL,            -- always 'sports_lag' in v3
    size_model         TEXT NOT NULL,
    entry_cap          REAL NOT NULL,            -- 0.95 or 0.97
    detection_path     TEXT NOT NULL,            -- 'feed' | 'book_poll'
    market_slug        TEXT NOT NULL,
    event_id           TEXT,
    side               TEXT NOT NULL,            -- 'YES' | 'NO'
    detected_at        TEXT NOT NULL,
    entry_ask          REAL NOT NULL,
    entry_bid          REAL,
    ask_size_at_entry  REAL NOT NULL,
    protocol_version   TEXT NOT NULL,            -- 'v1' | 'v2'
    market_context     TEXT,                     -- JSON
    resolved_at        TEXT,
    resolution_price   REAL,
    resolution_status  TEXT                      -- 'open' | 'resolved_win' | 'resolved_loss' | 'disputed' | 'stuck'
);

CREATE INDEX IF NOT EXISTS idx_pc_account ON position_context (account);
CREATE INDEX IF NOT EXISTS idx_pc_event ON position_context (event_id);
CREATE INDEX IF NOT EXISTS idx_pc_status ON position_context (resolution_status);

CREATE TABLE IF NOT EXISTS detections (
    id                 INTEGER PRIMARY KEY,
    ts                 TEXT NOT NULL,
    account            TEXT,                     -- null for "pre-grid" detection logs
    strategy           TEXT NOT NULL,
    detection_path     TEXT NOT NULL,
    market_slug        TEXT NOT NULL,
    event_id           TEXT,
    last_trade         REAL,
    best_ask           REAL,
    ask_size           REAL,
    skipped_reason     TEXT,                     -- null if placed; else
                                                 --   'already_open' | 'no_depth' | 'zombie'
                                                 --   | 'drawdown_breaker' | 'event_concentration_cap'
                                                 --   | 'cap_too_tight' | 'early_killed'
    fill_attempted_at  TEXT,
    fill_completed_at  TEXT,
    fill_price         REAL,
    fill_qty           REAL,
    latency_ms         INTEGER,
    slippage_bps       REAL
);

CREATE INDEX IF NOT EXISTS idx_det_ts ON detections (ts);
CREATE INDEX IF NOT EXISTS idx_det_account ON detections (account);

CREATE TABLE IF NOT EXISTS missed_opportunities (
    id                    INTEGER PRIMARY KEY,
    market_slug           TEXT NOT NULL,
    event_id              TEXT,
    detected_via          TEXT NOT NULL,         -- 'post_facto_scan' | 'partial_fill_residual'
    arb_window_start_ts   TEXT NOT NULL,
    arb_window_end_ts     TEXT NOT NULL,
    best_price_observed   REAL,
    total_capturable_usd  REAL,
    reason_we_missed      TEXT NOT NULL,
    our_detection_id      INTEGER,
    our_fill_id           TEXT,
    logged_at             TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_mo_reason ON missed_opportunities (reason_we_missed);

-- Daemon state: paused / running, current protocol_version
CREATE TABLE IF NOT EXISTS daemon_state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT OR IGNORE INTO daemon_state (key, value) VALUES ('paused', '0');
INSERT OR IGNORE INTO daemon_state (key, value) VALUES ('protocol_version', 'v1');
