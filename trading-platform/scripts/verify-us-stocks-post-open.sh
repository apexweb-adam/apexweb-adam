#!/usr/bin/env bash
# Post-open verification after Monday US stocks open (13:30 UTC).
set -euo pipefail

BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"

pass=0
fail=0
warn=0

ok() { echo "✓ $*"; pass=$((pass + 1)); }
bad() { echo "✗ $*"; fail=$((fail + 1)); }
note() { echo "○ $*"; warn=$((warn + 1)); }

echo "=== US Stocks Post-Open Verification — $(date -u '+%Y-%m-%d %H:%M UTC') ==="
echo "Backend: $BACKEND"
echo ""

CHECKLIST=$(curl -fsS -m 90 "$BACKEND/api/gate/us-stocks-open-checklist" 2>/dev/null || echo "{}")

python3 << PY
import json, sys
data = json.loads('''$CHECKLIST''')
if not data:
    print("  error=checklist_unreachable")
    sys.exit(1)
events = data.get("session_open_events") or {}
print(f"  phase={data.get('phase')} ready={data.get('ready')}")
print(f"  has_burst_scan={events.get('has_burst_scan')} has_auto_entry={events.get('has_auto_entry')}")
for row in data.get("checks") or []:
    print(f"  check {row.get('id')}={row.get('status')}: {row.get('message')}")
critical_fail = [c for c in (data.get("checks") or []) if c.get("critical") and c.get("status") == "fail"]
if data.get("phase") not in ("post_open", "open"):
    print("  warn=still in pre-open phase — rerun after US stocks open")
    sys.exit(2)
if critical_fail:
    print("  errors=" + ",".join(c["id"] for c in critical_fail))
    sys.exit(1)
sys.exit(0)
PY

rc=$?
if [[ $rc -eq 0 ]]; then
  ok "US stocks post-open checklist passed"
elif [[ $rc -eq 2 ]]; then
  note "US stocks not open yet — rerun after 13:30 UTC"
else
  bad "US stocks post-open checklist failed"
fi

echo ""
echo "Results: $pass passed, $fail failed, $warn notes"
[[ "$fail" -eq 0 ]]
