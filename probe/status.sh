#!/usr/bin/env bash
# Quick probe status — run from the project root.
set -euo pipefail

cd "$(dirname "$0")/.."

PID=$(pgrep -f "probe.main" | head -1 || true)
if [ -n "${PID:-}" ]; then
  echo "probe running: PID $PID"
  ps -p "$PID" -o pid,etime,rss,command | tail -n +1
else
  echo "probe NOT running"
fi

echo
echo "--- DB counts ---"
uv run python - <<'PY'
import sqlite3
c = sqlite3.connect("probe/probe.db")
def q(s):
    return c.execute(s).fetchone()[0]
print(f"crypto markets discovered: {q('SELECT COUNT(*) FROM markets WHERE is_crypto=1')}")
print(f"snapshots collected:       {q('SELECT COUNT(*) FROM market_snapshots')}")
print(f"distinct sampled markets:  {q('SELECT COUNT(DISTINCT market_id) FROM market_snapshots')}")
print(f"resolutions recorded:      {q('SELECT COUNT(*) FROM resolutions')}")
print(f"clean resolutions:         {q('SELECT COUNT(*) FROM resolutions WHERE resolved_cleanly=1')}")
print(f"unresolved:                {q('SELECT COUNT(*) FROM resolutions WHERE outcome=\"UNRESOLVED\"')}")
PY

echo
echo "--- last 6 log lines ---"
tail -n 6 probe/probe.log

echo
echo "Commands:"
echo "  generate report:  uv run python -m probe.report"
echo "  stop probe:       pkill -INT -f probe.main"
echo "  tail log:         tail -f probe/probe.log"
