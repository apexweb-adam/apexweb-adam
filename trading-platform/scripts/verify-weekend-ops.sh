#!/usr/bin/env bash
# Weekend operator checklist: deploy snapshot, dashboard bundle, CME preflight.
# Non-blocking on dashboard bundle lag; fails on CME critical checks.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"

echo "=== Weekend Ops Checklist — $(date -u '+%Y-%m-%d %H:%M UTC') ==="
echo "Backend: $BACKEND"
echo ""

SNAPSHOT=$(curl -fsS -m 15 "$BACKEND/api/deploy/snapshot" 2>/dev/null || echo "{}")
python3 << PY
import json, sys
snap = json.loads('''$SNAPSHOT''')
if not snap:
    print("○ deploy snapshot unavailable")
    sys.exit(0)
rev = snap.get("platform_revision")
exp = snap.get("expected_platform_revision")
print(f"Platform: {rev} → expected {exp} (current={snap.get('platform_revision_current')})")
window = snap.get("cme_deploy_window") or {}
if window.get("message"):
    print(f"CME window: {window.get('message')}")
bundle = snap.get("expected_dashboard_bundle")
if bundle:
    print(f"Dashboard bundle target: {bundle}")
PY

echo ""
bash "$ROOT/scripts/verify-dashboard-bundle.sh" || true

echo ""
if bash "$ROOT/scripts/watch-deploy-window.sh" --once; then
  rc=0
else
  rc=$?
fi

echo ""
if ! bash "$ROOT/scripts/verify-cme-reopen.sh"; then
  echo ""
  echo "CME preflight failed — fix before deploy window or CME open."
  exit 1
fi

if [[ "$rc" -eq 10 ]]; then
  echo ""
  echo "*** Deploy window is ACTIVE — run:"
  echo "  bash trading-platform/scripts/verify-pre-deploy.sh"
  echo "  TRIGGER_DEPLOY=true bash trading-platform/scripts/sync-render-env.sh"
  echo "  bash trading-platform/scripts/verify-post-deploy.sh"
  exit 10
fi

echo ""
echo "After CME open (22:00 UTC):"
echo "  bash trading-platform/scripts/verify-cme-post-open.sh"
echo ""
echo "Monday before US open (13:30 UTC):"
echo "  bash trading-platform/scripts/verify-us-stocks-open.sh --watch 120"
echo "Monday after US open:"
echo "  bash trading-platform/scripts/verify-us-stocks-post-open.sh"
