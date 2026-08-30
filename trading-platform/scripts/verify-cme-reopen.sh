#!/usr/bin/env bash
# Preflight checks before CME Sunday reopen (22:00 UTC) and Monday US open.
# Usage: verify-cme-reopen.sh [--watch SECONDS]
set -euo pipefail

BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"
EXPECTED_REVISION="${EXPECTED_PLATFORM_REVISION:-2026-08-29-r350}"
WATCH_INTERVAL=""

if [[ "${1:-}" == "--watch" ]]; then
  WATCH_INTERVAL="${2:-60}"
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

  echo "=== CME Reopen Preflight — $(date -u '+%Y-%m-%d %H:%M UTC') ==="
  echo "Backend: $BACKEND"
  echo "Expected revision (code): $EXPECTED_REVISION"
  echo ""

  CHECKLIST=$(curl -fsS -m 90 "$BACKEND/api/gate/cme-reopen-checklist" 2>/dev/null || echo "")
  if [[ -n "$CHECKLIST" && "$CHECKLIST" != "{}" ]]; then
    python3 << PY
import json, sys
data = json.loads('''$CHECKLIST''')
deploy = data.get("deploy") or {}
open_ready = data.get("open_ready") or {}
near = data.get("near_floor") or {}
print(f"  checklist_phase={data.get('phase')} ready={data.get('ready')}")
print(f"  platform_revision={deploy.get('platform_revision')} current={deploy.get('platform_revision_current')}")
urgency = deploy.get("cme_deploy_urgency")
if urgency:
    print(f"  deploy_urgency={urgency.get('message')}")
print(f"  cme_phase={data.get('prep_phase')} minutes_until_open={data.get('minutes_until_open')}")
print(f"  auto_entry_queued={open_ready.get('auto_entry_queued')} composite_floor={open_ready.get('composite_floor')}")
print(f"  open_ready={open_ready.get('symbols')}")
sticky = open_ready.get("sticky_symbols") or []
if sticky:
    print(f"  sticky_queue={sticky} (release_margin={open_ready.get('release_margin')})")
print(f"  near_floor={near.get('symbols')}")
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
      ok "CME reopen checklist passed"
    else
      bad "CME reopen checklist failed (see checks above)"
    fi
  else
    note "Checklist endpoint unavailable — using prep-status fallback"
    PREP=$(curl -fsS -m 45 "$BACKEND/api/gate/prep-status" 2>/dev/null || echo "{}")
    STATUS=$(curl -fsS -m 90 "$BACKEND/api/status" 2>/dev/null || echo "{}")

    python3 << PY
import json, sys
prep = json.loads('''$PREP''')
status = json.loads('''$STATUS''')
dep = (status.get("deploy") or {})
rev = dep.get("platform_revision") or "?"
expected = "$EXPECTED_REVISION"
print(f"  platform_revision={rev} expected={expected}")
comm = prep.get("commodities") or {}
cme = (prep.get("next_session_events") or {}).get("cme_reopen") or {}
mins = comm.get("minutes_until_open") or cme.get("minutes_until_open")
phase = comm.get("prep_phase") or cme.get("prep_phase")
open_ready = comm.get("open_ready_symbols") or cme.get("open_ready_symbols") or []
auto_entry = comm.get("auto_entry_queued") or cme.get("auto_entry_queued")
print(f"  cme_phase={phase} minutes_until_open={mins}")
print(f"  auto_entry_queued={auto_entry} open_ready={open_ready}")
errors = []
if mins is None:
    errors.append("missing_minutes_until_open")
if auto_entry is not True and open_ready:
    errors.append("auto_entry_not_queued")
if errors:
    print("  errors=" + ",".join(errors))
    sys.exit(1)
sys.exit(0)
PY
    if [[ $? -eq 0 ]]; then
      ok "CME prep-status looks ready for reopen"
    else
      bad "CME prep-status failed preflight"
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
d = json.loads('''$STATUS''')
bots = d.get("bots") or []
running = [b.get("bot_type") for b in bots if b.get("status") == "running"]
sys.exit(0 if len(running) >= 3 else 1)
PY
  if [[ $? -eq 0 ]]; then
    ok "Bots running"
  else
    bad "Not all bots running"
  fi

  echo ""
  echo "Results: $pass passed, $fail failed, $warn notes"
  if [[ "$fail" -gt 0 ]]; then
    echo ""
    echo "Deploy before CME if revision is behind:"
    echo "  TRIGGER_DEPLOY=true bash trading-platform/scripts/sync-render-env.sh"
    echo "Post-open verification:"
    echo "  bash trading-platform/scripts/verify-cme-post-open.sh"
    return 1
  fi
  return 0
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
