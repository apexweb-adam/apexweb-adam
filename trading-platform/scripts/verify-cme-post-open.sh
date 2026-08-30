#!/usr/bin/env bash
# Post-open verification after CME Sunday reopen (run after 22:00 UTC).
set -euo pipefail

BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"

pass=0
fail=0
warn=0

ok() { echo "✓ $*"; pass=$((pass + 1)); }
bad() { echo "✗ $*"; fail=$((fail + 1)); }
note() { echo "○ $*"; warn=$((warn + 1)); }

echo "=== CME Post-Open Verification — $(date -u '+%Y-%m-%d %H:%M UTC') ==="
echo "Backend: $BACKEND"
echo ""

CHECKLIST=$(curl -fsS -m 90 "$BACKEND/api/gate/cme-reopen-checklist" 2>/dev/null || echo "{}")
STATUS=$(curl -fsS -m 90 "$BACKEND/api/status" 2>/dev/null || echo "{}")

python3 << PY
import json, sys

checklist = json.loads('''$CHECKLIST''')
status = json.loads('''$STATUS''')
if not checklist:
    print("  error=checklist_unreachable")
    sys.exit(1)

phase = checklist.get("phase")
ready = checklist.get("ready")
checks = checklist.get("checks") or []
events = checklist.get("session_open_events") or {}
open_ready = (checklist.get("open_ready") or {}) or {}
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
errors = []
if phase not in ("post_open", "open"):
    print("  warn=still in pre-open phase — rerun after CME open")
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

rc=$?
if [[ $rc -eq 0 ]]; then
  ok "CME post-open checklist passed"
elif [[ $rc -eq 2 ]]; then
  note "CME not open yet — rerun after 22:00 UTC"
else
  bad "CME post-open checklist failed (see checks above)"
fi

echo ""
echo "Results: $pass passed, $fail failed, $warn notes"
if [[ "$fail" -gt 0 ]]; then
  exit 1
fi
echo ""
echo "Monday before US open (13:30 UTC):"
echo "  bash trading-platform/scripts/verify-us-stocks-open.sh --watch 120"
echo "Monday after US open:"
echo "  bash trading-platform/scripts/verify-us-stocks-post-open.sh"
