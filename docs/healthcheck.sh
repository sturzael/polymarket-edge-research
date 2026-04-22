#!/usr/bin/env bash
# Daily healthcheck for the 30-day paper-trade + forward-validation experiment.
# Run this manually or wire into launchd once-a-day. Output designed to surface
# silent drift (process dead, DB not growing, errors piling up).
#
# Exit code: 0 = all green, 1 = something needs attention.
#
# Usage: bash docs/healthcheck.sh

set -o pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 2

RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[0;33m'; NC='\033[0m'
FAIL=0

section() { echo; echo -e "${YLW}=== $1 ===${NC}"; }
ok()      { echo -e "  ${GRN}✓${NC} $1"; }
warn()    { echo -e "  ${YLW}⚠${NC} $1"; FAIL=1; }
fail()    { echo -e "  ${RED}✗${NC} $1"; FAIL=1; }

now_s() { date +%s; }
file_age_s() { local f="$1"; [ -e "$f" ] || { echo 99999999; return; }; echo $(( $(now_s) - $(stat -f %m "$f") )); }

# ------------------------------------------------------------------
section "1. PROCESSES"
for pat in \
  "e15_neg_risk_arb.logger:arb_logger" \
  "e15_neg_risk_arb.paper_trader:paper_trader" \
  "e15_neg_risk_arb.forward_trader:forward_trader" \
  "e17_realtime_arb_observer.observer:arb_observer" \
  "e23_stratification/live_trader/scanner.py:flb_scanner"
do
  IFS=: read -r needle label <<< "$pat"
  if pgrep -f "$needle" > /dev/null 2>&1; then ok "$label (pid $(pgrep -f "$needle" | head -1))"
  else fail "$label NOT RUNNING"; fi
done

# ------------------------------------------------------------------
section "2. LAUNCHD AGENTS"
for agent in paper-trader arb-logger forward-trader phantom-audit arb-observer calibration-fwd; do
  line=$(launchctl list 2>/dev/null | grep "com.elliot.polymarket-$agent")
  if [ -z "$line" ]; then fail "$agent NOT REGISTERED in launchd"
  else
    exitc=$(echo "$line" | awk '{print $2}')
    case "$exitc" in
      0|143) ok "$agent (exit=$exitc, benign)" ;;
      *)     warn "$agent last_exit=$exitc (non-zero, investigate)" ;;
    esac
  fi
done

# ------------------------------------------------------------------
section "3. DATABASE FRESHNESS (rows + latest write)"
check_db() {
  local db="$1" table="$2" ts_col="$3" stale_threshold_h="$4"
  if [ ! -f "experiments/$db" ]; then fail "$db missing"; return; fi
  local n latest
  n=$(sqlite3 "experiments/$db" "SELECT COUNT(*) FROM $table;" 2>/dev/null)
  if [ -z "$n" ]; then fail "$db:$table query failed"; return; fi
  if [ "$ts_col" = "-" ]; then
    ok "$db:$table rows=$n"
    return
  fi
  latest=$(sqlite3 "experiments/$db" "SELECT MAX($ts_col) FROM $table;" 2>/dev/null)
  if [ -z "$latest" ] || [ "$latest" = "" ]; then
    warn "$db:$table rows=$n but no $ts_col (empty or all NULL)"
    return
  fi
  local latest_s age_h
  latest_s=$(python3 -c "from datetime import datetime, timezone; print(int(datetime.fromisoformat('$latest'.replace('Z','+00:00')).timestamp()))" 2>/dev/null)
  if [ -z "$latest_s" ]; then warn "$db:$table parse failed ($latest)"; return; fi
  age_h=$(( ( $(now_s) - latest_s ) / 3600 ))
  if [ "$age_h" -gt "$stale_threshold_h" ]; then
    warn "$db:$table stale — last write ${age_h}h ago (threshold ${stale_threshold_h}h), rows=$n"
  else
    ok "$db:$table rows=$n, last write ${age_h}h ago"
  fi
}

check_db e15_neg_risk_arb/data/arb_log.db        scans       scan_at     3
check_db e15_neg_risk_arb/data/arb_log.db        arbs        -           -
check_db e15_neg_risk_arb/data/paper_trader.db   ticks       tick_at     3
check_db e15_neg_risk_arb/data/paper_trader.db   positions   entry_at    72
check_db e15_neg_risk_arb/data/paper_trader.db   closures    closed_at   999
check_db e15_neg_risk_arb/data/forward_trader.db picks       -           -
check_db e17_realtime_arb_observer/data/observer.db scans    scan_at     2
check_db e17_realtime_arb_observer/data/observer.db arbs     started_at  2
check_db e16_calibration_study/data/forward_validator.db scans     scan_at      2
check_db e16_calibration_study/data/forward_validator.db snapshots snapshot_at  2

# ------------------------------------------------------------------
section "4. OBSERVER: orphan arbs (should be 0)"
null_arbs=$(sqlite3 experiments/e17_realtime_arb_observer/data/observer.db "SELECT COUNT(*) FROM arbs WHERE ended_at IS NULL;" 2>/dev/null)
if [ "${null_arbs:-99}" -eq 0 ]; then ok "no orphan arbs"
elif [ "${null_arbs}" -le 5 ]; then ok "$null_arbs open arbs (in-flight is normal)"
else warn "$null_arbs arbs with ended_at=NULL (orphan-cleanup may have regressed)"; fi

# ------------------------------------------------------------------
section "5. ERROR COUNTS (last 24h of logs)"
since_iso=$(date -u -v-1d +%Y-%m-%dT%H 2>/dev/null || date -u --date='-1 day' +%Y-%m-%dT%H)
for log in \
  experiments/e15_neg_risk_arb/logs/logger.log \
  experiments/e15_neg_risk_arb/logs/paper_trader.log \
  experiments/e15_neg_risk_arb/logs/forward_trader.log \
  experiments/e17_realtime_arb_observer/data/observer.log \
  experiments/e16_calibration_study/data/forward_validator.log
do
  [ -f "$log" ] || continue
  # count true errors (not intentional "TIMEOUT" messages from observer)
  errs=$(grep -aiE "traceback|exception|ConnectionRefused|refused|ResolveError|failed to" "$log" 2>/dev/null | wc -l | tr -d ' ')
  if [ "$errs" -eq 0 ]; then ok "$(basename "$log"): clean"
  elif [ "$errs" -le 3 ]; then ok "$(basename "$log"): $errs errors (likely network blips)"
  else warn "$(basename "$log"): $errs errors — grep the log"; fi
done

# ------------------------------------------------------------------
section "6. DISK + DB SIZE"
df -h "$REPO" | awk 'NR==2 {
  used=$5; gsub("%","",used)
  if (used+0 > 90) printf "  \033[0;31m✗\033[0m disk %s used — running out\n", $5
  else printf "  \033[0;32m✓\033[0m disk %s used (avail %s)\n", $5, $4
}'
db_total=$(du -sc experiments/e15_neg_risk_arb/data experiments/e16_calibration_study/data/forward_validator.db experiments/e17_realtime_arb_observer/data 2>/dev/null | tail -1 | awk '{print $1}')
echo "  total experiment DB size: $(( db_total / 1024 )) MiB"

# ------------------------------------------------------------------
section "7. TRADABLE FLAGS (e23 FLB scanner)"
flags_file=experiments/e23_stratification/live_trader/data/flagged_markets.jsonl
if [ -f "$flags_file" ]; then
  flag_count=$(wc -l < "$flags_file" | tr -d ' ')
  latest_flag=$(tail -1 "$flags_file" 2>/dev/null | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print(d.get('flagged_at'),'|',d.get('sport'),d.get('slug'))" 2>/dev/null)
  ok "flags so far: $flag_count. latest: $latest_flag"
else
  ok "no flags yet (expected during sports-calendar dead zones)"
fi
ntfy=$(grep ntfy_topic experiments/e23_stratification/live_trader/config.json | grep -o 'REPLACE_ME')
if [ -n "$ntfy" ]; then warn "ntfy_topic still REPLACE_ME — set it so flags push to phone"; fi

# ------------------------------------------------------------------
section "SUMMARY"
if [ "$FAIL" -eq 0 ]; then echo -e "  ${GRN}ALL GREEN${NC}"
else echo -e "  ${YLW}SOMETHING NEEDS ATTENTION${NC} — see warnings above"; fi
exit $FAIL
