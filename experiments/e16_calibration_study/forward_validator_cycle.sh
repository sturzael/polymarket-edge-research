#!/bin/bash
# Hourly cycle: snapshot new T-7d sports markets + check for new resolutions.
# Launched by com.elliot.polymarket-calibration-fwd.plist.

set -eu

REPO="/Users/elliotsturzaker/dev/event-impact-mvp"
UV="/Users/elliotsturzaker/.local/bin/uv"
cd "$REPO"

echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) cycle start ==="

"$UV" run python -m experiments.e16_calibration_study.forward_validator scan 2>&1 \
    | sed 's/^/  scan: /'

"$UV" run python -m experiments.e16_calibration_study.forward_validator resolve 2>&1 \
    | sed 's/^/  resolve: /'

echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) cycle done ==="
