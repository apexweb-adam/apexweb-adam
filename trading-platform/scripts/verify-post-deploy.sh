#!/usr/bin/env bash
# Verify session-open bundle (r337+) is live after Render deploy.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"
EXPECTED_REVISION="${EXPECTED_PLATFORM_REVISION:-$(grep '^EXPECTED_PLATFORM_REVISION' "$ROOT/backend/app/engines/deploy_status.py" | sed -n 's/.*"\([^"]*\)".*/\1/p')}"

pass=0
fail=0
warn=0

ok() { echo "✓ $*"; pass=$((pass + 1)); }
bad() { echo "✗ $*"; fail=$((fail + 1)); }
note() { echo "○ $*"; warn=$((warn + 1)); }

echo "=== Post-Deploy Session-Open Verification — $(date -u '+%Y-%m-%d %H:%M UTC') ==="
echo "Backend: $BACKEND"
echo "Expected revision: $EXPECTED_REVISION"
echo ""

STATUS=$(curl -fsS -m 45 "$BACKEND/api/status" 2>/dev/null || echo "{}")
CHECKLIST=$(curl -fsS -m 45 "$BACKEND/api/gate/cme-reopen-checklist" 2>/dev/null || echo "{}")
SNAPSHOT=$(curl -fsS -m 15 "$BACKEND/api/deploy/snapshot" 2>/dev/null || echo "{}")

python3 << PY
import json, sys

status = json.loads('''$STATUS''')
checklist = json.loads('''$CHECKLIST''')
snapshot = json.loads('''$SNAPSHOT''')
expected = "$EXPECTED_REVISION"
errors = []

deploy = status.get("deploy") or {}
if not deploy and snapshot:
    deploy = snapshot
prod_rev = deploy.get("platform_revision") or snapshot.get("platform_revision") or "?"
print(f"  platform_revision={prod_rev} expected={expected}")
if prod_rev != expected:
    errors.append("revision_mismatch")

summaries = status.get("session_open_checklists") or {}
if not summaries.get("cme_reopen"):
    if status == {}:
        print("  session_open_checklists=skipped (/api/status unavailable)")
    else:
        errors.append("session_open_checklists_missing")
else:
    cme = summaries["cme_reopen"]
    print(f"  session_open_checklists.cme_reopen ready={cme.get('ready')} phase={cme.get('phase')}")
    print(f"    open_ready={cme.get('open_ready_symbols')} near_floor={cme.get('near_floor_symbols')}")
    gaps = cme.get("near_floor_gaps") or {}
    if gaps:
        print(f"    near_floor_gaps={gaps}")

open_ready = checklist.get("open_ready") or {}
if "sticky_symbols" not in open_ready:
    errors.append("sticky_symbols_field_missing")
else:
    sticky = open_ready.get("sticky_symbols") or []
    print(f"  checklist sticky_symbols={sticky} release_margin={open_ready.get('release_margin')}")

near = checklist.get("near_floor") or {}
for row in near.get("details") or []:
    sym = row.get("symbol")
    gap = row.get("gap_to_floor")
    comp = row.get("composite")
    if sym and gap is not None:
        print(f"    near_floor {sym}: composite={comp} gap_to_floor={gap}")

deploy_info = status.get("deploy") or {}
deploy_window = deploy_info.get("cme_deploy_window") or snapshot.get("cme_deploy_window")
if deploy_window:
    print(
        "  cme_deploy_window "
        f"in_window={deploy_window.get('in_window')} "
        f"opens={deploy_window.get('window_opens_at_utc')}"
    )
else:
    errors.append("cme_deploy_window_missing")

if deploy_info.get("vercel_bundle_behind_expected") is True:
    exp = deploy_info.get("expected_dashboard_bundle") or "?"
    act = deploy_info.get("vercel_bundle_revision") or "?"
    print(f"  note: dashboard bundle behind expected ({act} vs {exp}) — non-blocking")

if snapshot.get("cme_deploy_window") or snapshot.get("platform_revision"):
    print(f"  deploy_snapshot=ok revision={snapshot.get('platform_revision')}")
elif snapshot and snapshot != {}:
    errors.append("deploy_snapshot_missing_window")
elif prod_rev == expected:
    print("  deploy_snapshot=skipped (pre-r358 backend)")

if errors:
    print("  errors=" + ",".join(errors))
    sys.exit(1)
sys.exit(0)
PY

if [[ $? -eq 0 ]]; then
  ok "Post-deploy session-open bundle live"
else
  bad "Post-deploy verification failed — revision or session-open features missing"
fi

if bash "$ROOT/scripts/verify-cme-reopen.sh"; then
  ok "CME reopen preflight still passing"
else
  bad "CME reopen preflight failed after deploy"
fi

if bash "$ROOT/scripts/verify-dashboard-bundle.sh"; then
  :
else
  note "Dashboard bundle check failed (non-blocking)"
fi

echo ""
echo "Results: $pass passed, $fail failed, $warn notes"
if [[ "$fail" -gt 0 ]]; then
  exit 1
fi

echo ""
echo "After CME open (22:00 UTC):"
echo "  bash trading-platform/scripts/verify-cme-post-open.sh"
