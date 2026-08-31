#!/usr/bin/env bash
# Post-open verification after CME Sunday reopen (run after 22:00 UTC).
# Usage: verify-cme-post-open.sh [--watch SECONDS]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/fetch_json.sh
source "$ROOT/scripts/lib/fetch_json.sh"
BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"
CODE_REV="$(grep '^EXPECTED_PLATFORM_REVISION' "$ROOT/backend/app/engines/deploy_status.py" | sed -n 's/.*"\([^"]*\)".*/\1/p')"
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

  echo "=== CME Post-Open Verification — $(date -u '+%Y-%m-%d %H:%M UTC') ==="
  echo "Backend: $BACKEND"
  echo "Expected revision (code): ${CODE_REV:-unknown}"
  echo ""

  if ! check_backend_suspension "$BACKEND"; then
    bad "Backend billing-suspended — CME post-open scan/entry verification unavailable"
    echo ""
    echo "Results: $pass passed, $fail failed, $warn notes"
    return 2
  fi

  TMP=$(mktemp -d)
  trap 'rm -rf "$TMP"' RETURN
  wake_backend "$BACKEND" 3
  fetch_json "$BACKEND/api/gate/cme-reopen-checklist" 120 3 > "$TMP/checklist.json"
  fetch_json "$BACKEND/api/status" 120 3 > "$TMP/status.json"
  fetch_json "$BACKEND/api/deploy/snapshot" 60 3 > "$TMP/snapshot.json"

  CHECKLIST_FILE="$TMP/checklist.json" STATUS_FILE="$TMP/status.json" SNAPSHOT_FILE="$TMP/snapshot.json" CODE_REV="$CODE_REV" python3 << 'PY'
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
snapshot = load("SNAPSHOT")
code_rev = os.environ.get("CODE_REV") or ""
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
extended_watch = open_ready.get("extended_watch_symbols") or []
release_margin = open_ready.get("release_margin")

print(f"  phase={phase} ready={ready}")
prod_rev = snapshot.get("platform_revision") or (status.get("deploy") or {}).get("platform_revision")
expected_rev = (
    (checklist.get("deploy") or {}).get("expected_platform_revision")
    or snapshot.get("expected_platform_revision")
    or code_rev
)
if prod_rev and expected_rev and prod_rev != expected_rev:
    print(f"  warn=revision_behind running={prod_rev} expected={expected_rev}")
elif prod_rev and code_rev and prod_rev != code_rev:
    print(f"  note=local_code_rev={code_rev} production={prod_rev}")
if snapshot.get("deploy_credentials_ready") is False:
    for item in snapshot.get("deploy_credentials_warnings") or []:
        print(f"  warn=credentials {item}")
print(f"  prep_phase={checklist.get('prep_phase')} in_session={checklist.get('in_session')}")
print(f"  open_ready={open_symbols} sticky={sticky} release_margin={release_margin}")
if extended_watch:
    print(f"  extended_watch={extended_watch}")
    dropped_watch = [sym for sym in extended_watch if sym not in open_symbols]
    if dropped_watch:
        print(f"  extended_watch_dropped={dropped_watch}")

near_floor = checklist.get("near_floor") or {}
near_symbols = near_floor.get("symbols") or []
if near_symbols:
    print(f"  near_floor_watch={near_symbols}")
for row in near_floor.get("details") or []:
    sym = row.get("symbol")
    gap = row.get("gap_to_floor")
    comp = row.get("composite")
    if sym:
        print(f"    near_floor {sym}: composite={comp} gap_to_floor={gap}")

if phase in ("post_open", "open") and near_symbols:
    still_near = [s for s in near_symbols if s not in sticky and s not in open_symbols]
    if still_near:
        print(f"  near_floor_pending={still_near} (expect sticky promotion as composite rises)")
    promoted = [s for s in near_symbols if s in sticky or s in open_symbols]
    if promoted:
        print(f"  near_floor_promoted={promoted}")
print(f"  has_burst_scan={events.get('has_burst_scan')} has_auto_entry={events.get('has_auto_entry')}")

outage = checklist.get("platform_outage_recovery") or {}
if outage.get("logged"):
    print("  platform_outage_recovery_logged=true")
if outage.get("window_active"):
    print(
        f"  platform_outage_recovery_window=true "
        f"grace_remaining_min={outage.get('grace_minutes_remaining')}"
    )

latest_burst = events.get("latest_burst_scan")
if latest_burst:
    print(f"  latest_burst_scan={latest_burst.get('detail')}")
latest_entry = events.get("latest_auto_entry")
if latest_entry:
    print(f"  latest_auto_entry symbols={latest_entry.get('symbols')} detail={latest_entry.get('detail')}")

status_events = status.get("session_open_events") or []
if status_events:
    types = [e.get("event_type") for e in status_events[:20]]
    print(f"  status.session_open_events types={types[:8]}")
    queue_adds = [e for e in status_events if e.get("event_type") == "queue_add"]
    if queue_adds:
        print(f"  queue_add_events={len(queue_adds)}")
else:
    print("  status.session_open_events=empty")

summaries = (status.get("session_open_checklists") or {}).get("cme_reopen") or {}
if summaries:
    print(
        f"  status.checklist open_ready={summaries.get('open_ready_symbols')} "
        f"near_floor={summaries.get('near_floor_symbols')}"
    )

for row in checks:
    status_val = row.get("status")
    cid = row.get("id")
    msg = row.get("message")
    print(f"  check {cid}={status_val}: {msg}")

critical_failures = [
    c for c in checks
    if c.get("critical") and c.get("status") == "fail"
]
if events.get("has_auto_entry"):
    critical_failures = [
        c for c in critical_failures if c.get("id") != "burst_scan_logged"
    ]
errors = []
if phase not in ("post_open", "open"):
    print("  warn=still in pre-open phase — rerun after CME open")
    sys.exit(2)
if not events.get("has_burst_scan") and not events.get("has_auto_entry"):
    deploy = checklist.get("deploy") or {}
    rev_current = deploy.get("platform_revision_current")
    if outage.get("window_active"):
        if rev_current is False:
            print(
                f"  warn=deploy_{code_rev or 'revision'}_required_for_platform_outage_recovery"
            )
            errors.append("revision_behind_for_outage_recovery")
        else:
            print("  note=platform_outage_recovery_pending — burst scan expected on next bot loop")
    else:
        errors.append("burst_scan_missing")
if not events.get("has_auto_entry") and open_symbols:
    errors.append("auto_entry_missing")
if critical_failures:
    errors.extend(c["id"] for c in critical_failures)
if near_symbols and phase in ("post_open", "open"):
    print("  note=monitor near_floor sticky hysteresis through first burst cycle")
if errors:
    print("  errors=" + ",".join(errors))
    sys.exit(1)
sys.exit(0)
PY

  local rc=$?
  if [[ $rc -eq 0 ]]; then
    ok "CME post-open checklist passed"
  elif [[ $rc -eq 2 ]]; then
    note "CME not open yet — rerun after 22:00 UTC"
  else
    bad "CME post-open checklist failed (see checks above)"
  fi

  echo ""
  echo "Results: $pass passed, $fail failed, $warn notes"
  return "$rc"
}

finish() {
  local rc=$1
  if [[ "$rc" -eq 1 ]]; then
    exit 1
  fi
  if [[ "$rc" -eq 0 ]]; then
    echo ""
    echo "Monday before US open (13:30 UTC):"
    echo "  bash trading-platform/scripts/verify-us-stocks-open.sh --watch 120"
    echo "Monday after US open:"
    echo "  bash trading-platform/scripts/verify-us-stocks-post-open.sh --watch 120"
  fi
  exit "$rc"
}

if [[ -n "$WATCH_INTERVAL" ]]; then
  while true; do
    run_verification
    rc=$?
    if [[ $rc -eq 0 ]]; then
      finish 0
    fi
    if [[ $rc -eq 1 ]]; then
      finish 1
    fi
    echo ""
    echo "Watching for CME post-open — next check in ${WATCH_INTERVAL}s (Ctrl+C to stop)"
    sleep "$WATCH_INTERVAL"
    echo ""
  done
else
  run_verification
  finish $?
fi
