#!/usr/bin/env bash
# Preflight checks before Monday US stocks open (13:30 UTC).
# Usage: verify-us-stocks-open.sh [--watch SECONDS]
set -euo pipefail

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

run_preflight() {
  pass=0
  fail=0
  warn=0

  echo "=== US Stocks Open Preflight — $(date -u '+%Y-%m-%d %H:%M UTC') ==="
  echo "Backend: $BACKEND"
  echo ""

  CHECKLIST=$(curl -fsS -m 90 "$BACKEND/api/gate/us-stocks-open-checklist" 2>/dev/null || echo "")
  if [[ -n "$CHECKLIST" && "$CHECKLIST" != "{}" ]]; then
    python3 << PY
import json, sys
data = json.loads('''$CHECKLIST''')
open_ready = data.get("open_ready") or {}
print(f"  phase={data.get('phase')} ready={data.get('ready')}")
print(f"  prep_phase={data.get('prep_phase')} minutes_until_open={data.get('minutes_until_open')}")
print(f"  auto_entry_queued={open_ready.get('auto_entry_queued')} open_ready={open_ready.get('symbols')}")
for row in data.get("checks") or []:
    print(f"  check {row.get('id')}={row.get('status')}: {row.get('message')}")
critical_fail = [c for c in (data.get("checks") or []) if c.get("critical") and c.get("status") == "fail"]
if critical_fail:
    print("  errors=" + ",".join(c["id"] for c in critical_fail))
    sys.exit(1)
sys.exit(0)
PY
    if [[ $? -eq 0 ]]; then
      ok "US stocks open checklist passed"
    else
      bad "US stocks open checklist failed"
    fi
  else
    note "Checklist endpoint unavailable — using prep-status fallback"
    PREP=$(curl -fsS -m 45 "$BACKEND/api/gate/prep-status" 2>/dev/null || echo "{}")
    python3 << PY
import json, sys
prep = json.loads('''$PREP''')
stocks = prep.get("stocks_futures") or {}
us = (prep.get("next_session_events") or {}).get("us_stocks_open") or {}
open_ready = stocks.get("open_ready_symbols") or us.get("open_ready_symbols") or []
auto_entry = stocks.get("auto_entry_queued") or us.get("auto_entry_queued")
print(f"  minutes_until_open={stocks.get('minutes_until_open') or us.get('minutes_until_open')}")
print(f"  auto_entry_queued={auto_entry} open_ready={open_ready}")
sys.exit(0 if auto_entry or not open_ready else 1)
PY
    if [[ $? -eq 0 ]]; then
      ok "US stocks prep-status looks ready"
    else
      bad "US stocks prep-status failed"
    fi
  fi

  if curl -fsS -m 20 "$BACKEND/api/health" >/dev/null 2>&1; then
    ok "Backend health"
  else
    bad "Backend health unreachable"
  fi

  echo ""
  echo "Results: $pass passed, $fail failed, $warn notes"
  [[ "$fail" -eq 0 ]]
}

if [[ -n "$WATCH_INTERVAL" ]]; then
  while true; do
    run_preflight || true
    echo ""
    echo "Watching — next check in ${WATCH_INTERVAL}s (Ctrl+C to stop)"
    sleep "$WATCH_INTERVAL"
    echo ""
  done
else
  run_preflight
fi
