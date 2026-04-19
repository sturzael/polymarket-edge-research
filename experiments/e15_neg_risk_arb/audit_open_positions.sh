#!/bin/bash
# Weekly phantom-depth audit of every open paper-trade position.
# Run via launchd (com.elliot.polymarket-phantom-audit.plist) or ad-hoc.
# Appends to logs/phantom_audit.log with a timestamped header per run.

set -euo pipefail

REPO="/Users/elliotsturzaker/dev/event-impact-mvp"
DB="$REPO/experiments/e15_neg_risk_arb/data/paper_trader.db"
LOG="$REPO/experiments/e15_neg_risk_arb/logs/phantom_audit.log"
UV="/Users/elliotsturzaker/.local/bin/uv"

cd "$REPO"

{
    echo ""
    echo "=============================================================="
    echo "phantom-audit $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "=============================================================="

    slugs=$(sqlite3 "$DB" "SELECT event_slug FROM positions WHERE status='open';")
    if [ -z "$slugs" ]; then
        echo "(no open positions — nothing to audit)"
        exit 0
    fi

    for slug in $slugs; do
        echo ""
        echo "--- $slug ---"
        "$UV" run python -m experiments.e15_neg_risk_arb.phantom_check \
            --event "$slug" --visual 2>&1 || echo "(audit failed: $slug)"
    done
} >> "$LOG" 2>&1
