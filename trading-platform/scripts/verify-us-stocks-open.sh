#!/usr/bin/env bash
# Preflight checks before Monday US stocks open (13:30 UTC).
# Usage: verify-us-stocks-open.sh [--watch SECONDS]
set -euo pipefail

BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"
EXPECTED_REVISION="${EXPECTED_PLATFORM_REVISION:-2026-08-29-r358}"
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
  echo "Expected revision (code): $EXPECTED_REVISION"
  echo ""

  CHECKLIST=$(curl -fsS -m 90 "$BACKEND/api/gate/us-stocks-open-checklist" 2>/dev/null || echo "")
  if [[ -n "$CHECKLIST" && "$CHECKLIST" != "{}" ]]; then
    python3 << PY
import json, sys
data = json.loads('''$CHECKLIST''')
deploy = data.get("deploy") or {}
open_ready = data.get("open_ready") or {}
near = data.get("near_floor") or {}
print(f"  checklist_phase={data.get('phase')} ready={data.get('ready')}")
print(f"  platform_revision={deploy.get('platform_revision')} current={deploy.get('platform_revision_current')}")
print(f"  prep_phase={data.get('prep_phase')} minutes_until_open={data.get('minutes_until_open')}")
print(f"  auto_entry_queued={open_ready.get('auto_entry_queued')} composite_floor={open_ready.get('composite_floor')}")
print(f"  open_ready={open_ready.get('symbols')}")
sticky = open_ready.get("sticky_symbols") or []
if sticky:
    print(f"  sticky_queue={sticky} (release_margin={open_ready.get('release_margin')})")
print(f"  near_floor={near.get('symbols')}")
for row in near.get("details") or []:
    sym = row.get("symbol")
    comp = row.get("composite")
    gap = row.get("gap_to_floor")
    gap_label = f" need +{gap}" if gap is not None else ""
    print(f"    near_floor {sym}: composite={comp}{gap_label}")
for row in open_ready.get("details") or []:
    sym = row.get("symbol")
    comp = row.get("composite")
    blockers = row.get("blockers") or []
    sticky_flag = " sticky" if row.get("sticky_queue") else ""
    print(f"    {sym}: composite={comp}{sticky_flag} blockers={blockers}")
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

  STATUS=$(curl -fsS -m 90 "$BACKEND/api/status" 2>/dev/null || echo "{}")
  python3 << PY
import json, sys

status = json.loads('''$STATUS''')
deploy = status.get("deploy") or {}
rev_current = deploy.get("platform_revision_current")
errors = []
notes = []

summaries = status.get("session_open_checklists") or {}
if not summaries.get("us_stocks_open"):
    (errors if rev_current is True else notes).append("us_stocks_open_summary_missing")
else:
    us = summaries["us_stocks_open"]
    print(
        f"  status.session_open_checklists.us_stocks_open "
        f"ready={us.get('ready')} open_ready={us.get('open_ready_symbols')}"
    )
    composites = us.get("open_ready_composites") or {}
    if composites:
        print(f"  open_ready_composites={composites}")

open_ready = json.loads('''$CHECKLIST''').get("open_ready") or {} if '''$CHECKLIST''' else {}
if '''$CHECKLIST''' and "sticky_symbols" not in open_ready:
    (errors if rev_current is True else notes).append("sticky_symbols_field_missing")

for note in notes:
    print(f"  note={note} (expected until revision deploy)")
if errors:
    print("  errors=" + ",".join(errors))
    sys.exit(1)
sys.exit(0)
PY
  if [[ $? -eq 0 ]]; then
    ok "US stocks status contract"
  else
    bad "US stocks status contract failed"
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
