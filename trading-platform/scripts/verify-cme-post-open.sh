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

python3 << PY
import json, sys

data = json.loads('''$CHECKLIST''')
if not data:
    print("  error=checklist_unreachable")
    sys.exit(1)

phase = data.get("phase")
ready = data.get("ready")
checks = data.get("checks") or []
events = data.get("session_open_events") or {}
open_ready = (data.get("open_ready") or {}).get("symbols") or []

print(f"  phase={phase} ready={ready}")
print(f"  prep_phase={data.get('prep_phase')} in_session={data.get('in_session')}")
print(f"  open_ready={open_ready}")
print(f"  has_burst_scan={events.get('has_burst_scan')} has_auto_entry={events.get('has_auto_entry')}")

latest_burst = events.get("latest_burst_scan")
if latest_burst:
    print(f"  latest_burst_scan={latest_burst.get('detail')}")
latest_entry = events.get("latest_auto_entry")
if latest_entry:
    print(f"  latest_auto_entry={latest_entry.get('detail')}")

for row in checks:
    status = row.get("status")
    cid = row.get("id")
    msg = row.get("message")
    print(f"  check {cid}={status}: {msg}")

critical_failures = [
    c for c in checks
    if c.get("critical") and c.get("status") == "fail"
]
if phase not in ("post_open", "open"):
    print("  warn=still in pre-open phase — rerun after CME open")
    sys.exit(2)
if critical_failures:
    print("  errors=" + ",".join(c["id"] for c in critical_failures))
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
