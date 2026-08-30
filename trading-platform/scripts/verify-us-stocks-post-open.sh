#!/usr/bin/env bash
# Post-open verification after Monday US stocks open (run after 13:30 UTC).
# Usage: verify-us-stocks-post-open.sh [--watch SECONDS]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/fetch_json.sh
source "$ROOT/scripts/lib/fetch_json.sh"
BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"
WATCH_INTERVAL=""

if [[ "${1:-}" == "--watch" ]]; then
  WATCH_INTERVAL="${2:-120}"
fi

pass=0
fail=0
warn=0

ok() { echo "✓ $*"; pass=$((pass + 1)); }
bad() { echo "✗ $*"; fail=$((fail + 1)); }
note() { echo "○ $*"; warn=$((warn + 1)); }

run_verification() {
  pass=0
  fail=0
  warn=0

  echo "=== US Stocks Post-Open Verification — $(date -u '+%Y-%m-%d %H:%M UTC') ==="
  echo "Backend: $BACKEND"
  echo ""

  TMP=$(mktemp -d)
  trap 'rm -rf "$TMP"' RETURN
  fetch_json "$BACKEND/api/gate/us-stocks-open-checklist" 90 2 > "$TMP/checklist.json" || echo "{}" > "$TMP/checklist.json"
  fetch_json "$BACKEND/api/status" 90 2 > "$TMP/status.json" || echo "{}" > "$TMP/status.json"

  CHECKLIST_FILE="$TMP/checklist.json" STATUS_FILE="$TMP/status.json" python3 << 'PY'
import json, os, sys
from pathlib import Path

def load(name: str) -> dict:
    path = Path(os.environ[f"{name}_FILE"])
    try:
        return json.loads(path.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError:
        return {}

checklist = load("CHECKLIST")
status = load("STATUS")
if not checklist:
    print("  error=checklist_unreachable")
    sys.exit(1)

phase = checklist.get("phase")
ready = checklist.get("ready")
checks = checklist.get("checks") or []
events = checklist.get("session_open_events") or {}
open_ready = checklist.get("open_ready") or {}
open_symbols = open_ready.get("symbols") or []
sticky = open_ready.get("sticky_symbols") or []

print(f"  phase={phase} ready={ready}")
print(f"  prep_phase={checklist.get('prep_phase')} in_session={checklist.get('in_session')}")
print(f"  open_ready={open_symbols} sticky={sticky}")
print(f"  has_burst_scan={events.get('has_burst_scan')} has_auto_entry={events.get('has_auto_entry')}")

latest_burst = events.get("latest_burst_scan")
if latest_burst:
    print(f"  latest_burst_scan={latest_burst.get('detail')}")
latest_entry = events.get("latest_auto_entry")
if latest_entry:
    print(f"  latest_auto_entry symbols={latest_entry.get('symbols')} detail={latest_entry.get('detail')}")

status_events = status.get("session_open_events") or []
if status_events:
    stocks_events = [e for e in status_events if e.get("bot_type") == "stocks_futures"]
    if stocks_events:
        print(f"  status.stocks_open_events={[e.get('event_type') for e in stocks_events[:6]]}")

summaries = (status.get("session_open_checklists") or {}).get("us_stocks_open") or {}
if summaries:
    print(
        f"  status.checklist open_ready={summaries.get('open_ready_symbols')} "
        f"composites={summaries.get('open_ready_composites')}"
    )

for row in checks:
    print(f"  check {row.get('id')}={row.get('status')}: {row.get('message')}")

critical_failures = [
    c for c in checks
    if c.get("critical") and c.get("status") == "fail"
]
errors = []
if phase not in ("post_open", "open"):
    print("  warn=still in pre-open phase — rerun after US stocks open")
    sys.exit(2)
if not events.get("has_burst_scan"):
    errors.append("burst_scan_missing")
if not events.get("has_auto_entry") and open_symbols:
    errors.append("auto_entry_missing")
if critical_failures:
    errors.extend(c["id"] for c in critical_failures)
if errors:
    print("  errors=" + ",".join(errors))
    sys.exit(1)
sys.exit(0)
PY

  local rc=$?
  if [[ $rc -eq 0 ]]; then
    ok "US stocks post-open checklist passed"
  elif [[ $rc -eq 2 ]]; then
    note "US stocks not open yet — rerun after 13:30 UTC"
  else
    bad "US stocks post-open checklist failed"
  fi

  echo ""
  echo "Results: $pass passed, $fail failed, $warn notes"
  return "$rc"
}

if [[ -n "$WATCH_INTERVAL" ]]; then
  while true; do
    run_verification
    rc=$?
    if [[ $rc -eq 0 ]]; then
      exit 0
    fi
    if [[ $rc -eq 1 ]]; then
      exit 1
    fi
    echo ""
    echo "Watching for US stocks post-open — next check in ${WATCH_INTERVAL}s (Ctrl+C to stop)"
    sleep "$WATCH_INTERVAL"
    echo ""
  done
else
  run_verification
  exit $?
fi
