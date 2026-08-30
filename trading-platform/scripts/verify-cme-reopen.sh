#!/usr/bin/env bash
# Preflight checks before CME Sunday reopen (22:00 UTC) and Monday US open.
# Usage: verify-cme-reopen.sh [--watch SECONDS]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LIB="$ROOT/scripts/lib/deploy_json.py"
# shellcheck source=lib/fetch_json.sh
source "$ROOT/scripts/lib/fetch_json.sh"
BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"
EXPECTED_REVISION="${EXPECTED_PLATFORM_REVISION:-$(grep '^EXPECTED_PLATFORM_REVISION' "$ROOT/backend/app/engines/deploy_status.py" | sed -n 's/.*"\([^"]*\)".*/\1/p')}"
WATCH_INTERVAL=""

if [[ "${1:-}" == "--watch" ]]; then
  WATCH_INTERVAL="${2:-60}"
  export CME_WATCH=1
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

  wake_backend "$BACKEND" 3
  # Checklist is lighter than /api/status and is the critical pre-open signal.
  CHECKLIST=$(fetch_json "$BACKEND/api/gate/cme-reopen-checklist" 120 3)
  if [[ -z "$CHECKLIST" || "$CHECKLIST" == "{}" ]]; then
    wake_backend "$BACKEND" 2
    CHECKLIST=$(fetch_json "$BACKEND/api/gate/cme-reopen-checklist" 120 3)
  fi
  STATUS=$(fetch_json "$BACKEND/api/status" 120 3)

  if [[ -n "$CHECKLIST" && "$CHECKLIST" != "{}" ]]; then
    if echo "$CHECKLIST" | python3 -c "
import json, os, sys
data = json.load(sys.stdin)
deploy = data.get('deploy') or {}
open_ready = data.get('open_ready') or {}
near = data.get('near_floor') or {}
mins = data.get('minutes_until_open')
print(f\"  checklist_phase={data.get('phase')} ready={data.get('ready')}\")
print(f\"  platform_revision={deploy.get('platform_revision')} current={deploy.get('platform_revision_current')}\")
urgency = deploy.get('cme_deploy_urgency')
if urgency:
    print(f\"  deploy_urgency={urgency.get('message')}\")
print(f\"  cme_phase={data.get('prep_phase')} minutes_until_open={data.get('minutes_until_open')}\")
print(f\"  auto_entry_queued={open_ready.get('auto_entry_queued')} composite_floor={open_ready.get('composite_floor')}\")
print(f\"  open_ready={open_ready.get('symbols')}\")
sticky = open_ready.get('sticky_symbols') or []
if sticky:
    print(f\"  sticky_queue={sticky} (release_margin={open_ready.get('release_margin')})\")
print(f\"  near_floor={near.get('symbols')}\")
for row in near.get('details') or []:
    sym = row.get('symbol')
    comp = row.get('composite')
    gap = row.get('gap_to_floor')
    gap_label = f' need +{gap}' if gap is not None else ''
    print(f'    near_floor {sym}: composite={comp}{gap_label}')
for row in open_ready.get('details') or []:
    sym = row.get('symbol')
    comp = row.get('composite')
    blockers = row.get('blockers') or []
    sticky_flag = ' sticky' if row.get('sticky_queue') else ''
    ext_flag = ' extended' if row.get('extended_sticky') else ''
    print(f'    {sym}: composite={comp}{sticky_flag}{ext_flag} blockers={blockers}')
extended_watch = open_ready.get('extended_watch_symbols') or []
if extended_watch:
    print(f'  extended_watch={extended_watch}')
floor = open_ready.get('composite_floor')
margin = open_ready.get('release_margin')
extended_margin = open_ready.get('extended_release_margin')
if margin is None:
    margin = 0.02
if extended_margin is None:
    extended_margin = 0.06
extended_watch_set = set(extended_watch)
thin_margin = []
for row in open_ready.get('details') or []:
    sym = row.get('symbol')
    comp = row.get('composite')
    if sym is None or comp is None or floor is None:
        continue
    effective = float(floor)
    if row.get('sticky_queue'):
        regular_effective = float(floor) - float(margin)
        extended_effective = float(floor) - float(extended_margin)
        use_extended = bool(row.get('extended_sticky')) or sym in extended_watch_set
        if not use_extended and float(comp) < regular_effective and float(comp) >= extended_effective:
            use_extended = True
        effective = extended_effective if use_extended else regular_effective
    gap = float(comp) - effective
    if gap < 0.02:
        thin_margin.append(f'{sym}(+{gap:.3f} to effective floor {effective:.2f})')
if thin_margin:
    print('  warn=thin_queue_margin ' + ', '.join(thin_margin))
dropped_watch = [sym for sym in extended_watch if sym not in (open_ready.get('symbols') or [])]
if dropped_watch and mins is not None and mins <= 360:
    print(f'  warn=extended_watch_not_queued {dropped_watch} — TV refresh continues; may re-queue if composite rises')
queue_dropped = bool(near.get('symbols')) and not open_ready.get('symbols') and not open_ready.get('auto_entry_queued')
if queue_dropped:
    print('  warn=queue_dropped near_floor without open_ready — confirm 6h prep watch is active')
if queue_dropped and mins is not None and mins <= 360:
    print('  error=queue_dropped_in_prep_window')
    sys.exit(1)
for row in data.get('checks') or []:
    print(f\"  check {row.get('id')}={row.get('status')}: {row.get('message')}\")
critical_fail = [c for c in (data.get('checks') or []) if c.get('critical') and c.get('status') == 'fail']
fail_ids = {c['id'] for c in critical_fail}
if fail_ids == {'composite_floor'}:
    floor = open_ready.get('composite_floor')
    margin = open_ready.get('release_margin')
    extended_margin = open_ready.get('extended_release_margin')
    if margin is None:
        margin = 0.02
    if extended_margin is None:
        extended_margin = 0.06
    if floor is not None:
        still_below = []
        extended_watch = set(open_ready.get('extended_watch_symbols') or [])
        for row in open_ready.get('details') or []:
            sym = row.get('symbol')
            comp = row.get('composite')
            if sym is None or comp is None:
                continue
            effective = float(floor)
            if row.get('sticky_queue'):
                regular_effective = float(floor) - float(margin)
                extended_effective = float(floor) - float(extended_margin)
                use_extended = bool(row.get('extended_sticky')) or sym in extended_watch
                if not use_extended and float(comp) < regular_effective and float(comp) >= extended_effective:
                    use_extended = True
                effective = extended_effective if use_extended else regular_effective
            if float(comp) < effective:
                still_below.append(str(sym))
        if not still_below:
            print('  note=composite_floor_ok_with_sticky_margin')
            critical_fail = []
if critical_fail:
    print('  errors=' + ','.join(c['id'] for c in critical_fail))
    sys.exit(1)
"; then
      ok "CME reopen checklist passed"
    else
      bad "CME reopen checklist failed (see checks above)"
    fi
  else
    note "Checklist endpoint unavailable — using prep-status fallback"
    PREP=$(fetch_json "$BACKEND/api/gate/prep-status" 45 2)
    if [[ -z "$PREP" || "$PREP" == "{}" ]]; then
      PREP=$(fetch_json "$BACKEND/api/gate/prep-status" 45 2)
    fi

    REV=$(echo "$STATUS" | python3 -c "import json,sys; d=json.load(sys.stdin); print((d.get('deploy') or {}).get('platform_revision') or '?')" 2>/dev/null || echo "?")
    echo "  platform_revision=$REV expected=$EXPECTED_REVISION"

    if echo "$PREP" | python3 "$LIB" cme-prep-preflight; then
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

  if [[ -z "$STATUS" || "$STATUS" == "{}" ]]; then
    if echo "$CHECKLIST" | python3 -c "
import json, sys
data = json.load(sys.stdin)
checks = {c['id']: c for c in data.get('checks') or []}
bh = checks.get('backend_health') or {}
sys.exit(0 if bh.get('status') == 'pass' else 1)
"; then
      note "Bots running (checklist fallback — /api/status unreachable)"
    else
      bad "Not all bots running (status endpoint unreachable)"
    fi
  elif echo "$STATUS" | python3 -c "import json,sys; d=json.load(sys.stdin); bots=d.get('bots') or []; running=[b.get('bot_type') for b in bots if b.get('status')=='running']; sys.exit(0 if len(running) >= 3 else 1)"; then
    ok "Bots running"
  else
    bad "Not all bots running"
  fi

  if [[ -z "$CHECKLIST" || "$CHECKLIST" == "{}" ]]; then
    CHECKLIST=$(fetch_json "$BACKEND/api/gate/cme-reopen-checklist" 45)
  fi

  export STATUS_JSON="$STATUS"
  export CHECKLIST_JSON="$CHECKLIST"
  if python3 << 'PY'
import json, os, sys

status = json.loads(os.environ.get("STATUS_JSON") or "{}")
checklist = json.loads(os.environ.get("CHECKLIST_JSON") or "{}")
status_unreachable = not status
deploy = status.get("deploy") or {}
checklist_deploy = checklist.get("deploy") or {}
rev_current = deploy.get("platform_revision_current")
if rev_current is None and status_unreachable:
    rev_current = checklist_deploy.get("platform_revision_current")
errors = []
notes = []

if status_unreachable:
    notes.append("status_endpoint_unreachable")

summaries = status.get("session_open_checklists") or {}
if not summaries.get("cme_reopen"):
    if status_unreachable and checklist.get("ready") is True:
        notes.append("session_open_checklists_missing")
    else:
        (errors if rev_current is True else notes).append("session_open_checklists_missing")
else:
    cme = summaries["cme_reopen"]
    print(
        f"  status.session_open_checklists.cme_reopen "
        f"ready={cme.get('ready')} open_ready={cme.get('open_ready_symbols')}"
    )

open_ready = checklist.get("open_ready") or {}
if checklist and "sticky_symbols" not in open_ready:
    (errors if rev_current is True else notes).append("sticky_symbols_field_missing")
elif open_ready.get("sticky_symbols"):
    print(f"  status sticky_symbols={open_ready.get('sticky_symbols')}")

deploy_window = deploy.get("cme_deploy_window")
if deploy_window:
    print(
        f"  status.cme_deploy_window in_window={deploy_window.get('in_window')} "
        f"opens={deploy_window.get('window_opens_at_utc')}"
    )
elif rev_current is True:
    print("  status.cme_deploy_window=none (revision current — outside deploy window)")
elif rev_current is False:
    notes.append("cme_deploy_window_pending_deploy")
elif status_unreachable and checklist_deploy.get("platform_revision_current") is True:
    print("  status.cme_deploy_window=none (checklist revision current — status unreachable)")
else:
    errors.append("cme_deploy_window_missing")

for note in notes:
    print(f"  note={note} (expected until revision deploy)")
if errors:
    print("  errors=" + ",".join(errors))
    sys.exit(1)
sys.exit(0)
PY
  then
    ok "Session-open status contract"
  else
    bad "Session-open status contract failed"
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
    set +e
    run_preflight
    rc=$?
    set -e
    if [[ "$rc" -ne 0 ]]; then
      echo ""
      echo "⚠ Preflight failed (exit $rc) — continuing watch"
    fi
    echo ""
    echo "Watching — next check in ${WATCH_INTERVAL}s (Ctrl+C to stop)"
    sleep "$WATCH_INTERVAL"
    echo ""
  done
else
  run_preflight
fi
