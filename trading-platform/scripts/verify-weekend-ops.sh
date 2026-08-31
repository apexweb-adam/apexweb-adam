#!/usr/bin/env bash
# Weekend operator checklist: deploy snapshot, dashboard bundle, CME preflight.
# Non-blocking on dashboard bundle lag; fails on CME critical checks.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/fetch_json.sh
source "$ROOT/scripts/lib/fetch_json.sh"
BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"
CODE_REV="$(grep '^EXPECTED_PLATFORM_REVISION' "$ROOT/backend/app/engines/deploy_status.py" | sed -n 's/.*"\([^"]*\)".*/\1/p')"

echo "=== Weekend Ops Checklist — $(date -u '+%Y-%m-%d %H:%M UTC') ==="
echo "Backend: $BACKEND"
echo "Code target: $CODE_REV"
echo ""

SNAPSHOT=$(fetch_json "$BACKEND/api/deploy/snapshot" 45 2)
export SNAPSHOT_JSON="$SNAPSHOT" CODE_REV="$CODE_REV"
python3 << 'PY'
import json, os, sys

snap = json.loads(os.environ.get("SNAPSHOT_JSON") or "{}")
code_rev = os.environ.get("CODE_REV") or ""
if not snap:
    print("○ deploy snapshot unavailable")
    if code_rev:
        print(f"  code_target={code_rev}")
    sys.exit(0)
rev = snap.get("platform_revision")
exp = snap.get("expected_platform_revision")
print(f"Platform: {rev} → prod expected {exp} (current={snap.get('platform_revision_current')})")
if code_rev and exp and code_rev != exp:
    print(f"  deploy will advance prod expected {exp} → {code_rev}")
elif code_rev and rev and code_rev != rev:
    print(f"  production behind code: {rev} → {code_rev}")
if snap.get("deploy_credentials_ready") is False:
    for item in snap.get("deploy_credentials_warnings") or []:
        print(f"WARN: {item}")
window = snap.get("cme_deploy_window") or {}
if window.get("message"):
    print(f"CME window: {window.get('message')}")
learning = snap.get("learning") or {}
content = snap.get("content_study") or {}
if learning:
    print(
        f"Learning: analyses={learning.get('trade_analyses')} "
        f"reviews={learning.get('daily_reviews')} "
        f"intel_pattern_alerts={learning.get('intel_pattern_count') or 0}"
    )
if content.get("recent"):
    for row in (content.get("recent") or [])[:2]:
        label = row.get("source_label") or row.get("source_type") or "unknown"
        title = (row.get("title") or "")[:40]
        print(f"  content_study [{label}] {title}")
bundle = snap.get("expected_dashboard_bundle")
if bundle:
    print(f"Dashboard bundle target: {bundle}")
for key in ("dashboard_bundle_verify_command", "weekend_ops_verify_command", "crm_learning_verify_command"):
    cmd = snap.get(key)
    if cmd:
        print(f"  {cmd}")
PY

bash "$ROOT/scripts/ops-gate-summary.sh" || true
echo ""
bash "$ROOT/scripts/check-deploy-credentials.sh" || true

US_CHECKLIST=$(fetch_json "$BACKEND/api/gate/us-stocks-open-checklist" 45 2)
US_NOTE=$(echo "$US_CHECKLIST" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if not data:
    raise SystemExit(0)
checks = {c.get('id'): c for c in data.get('checks') or []}
stocks = checks.get('stocks_active') or {}
open_ready = (data.get('open_ready') or {}).get('symbols') or []
mins = data.get('minutes_until_open')
if stocks.get('status') == 'fail':
    syms = ', '.join(open_ready) if open_ready else 'none'
    print(f'US stocks: bot paused — Monday auto-entry for {syms} blocked until profitability gate clears (open in {mins}min)')
elif stocks.get('status') == 'warn':
    syms = ', '.join(open_ready) if open_ready else 'none'
    print(f'US stocks: shadow mode — Monday gate-skip armed for {syms} (open in {mins}min)')
elif open_ready:
    print(f'US stocks: open_ready={open_ready} (opens in {mins}min)')
" 2>/dev/null || true)
if [[ -n "$US_NOTE" ]]; then
  echo "$US_NOTE"
fi

CME_CHECKLIST=$(fetch_json "$BACKEND/api/gate/cme-reopen-checklist" 60 2)
CME_NOTE=$(echo "$CME_CHECKLIST" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if not data:
    raise SystemExit(0)
open_ready = (data.get('open_ready') or {}).get('symbols') or []
sticky = (data.get('open_ready') or {}).get('sticky_symbols') or []
near = (data.get('near_floor') or {}).get('symbols') or []
auto_entry = (data.get('open_ready') or {}).get('auto_entry_queued')
mins = data.get('minutes_until_open')
parts = [f\"CME: open_ready={open_ready or 'none'}\"]
if sticky:
    parts.append(f'sticky={sticky}')
if near:
    parts.append(f'near_floor={near}')
parts.append(f'auto_entry={auto_entry}')
if mins is not None:
    parts.append(f'open in {mins}min')
print('; '.join(parts))
" 2>/dev/null || true)
if [[ -n "$CME_NOTE" ]]; then
  echo "$CME_NOTE"
fi

if [[ -f "$ROOT/.crm-load-baseline" ]]; then
  echo "CRM baseline: $(tr -d '[:space:]' < "$ROOT/.crm-load-baseline")s (pre-deploy; target <30s after r371)"
elif CRM_SEC=$(curl -sS -o /dev/null -m 120 -w "%{time_total}" "$BACKEND/crm" 2>/dev/null); [[ -n "$CRM_SEC" ]]; then
  echo "CRM load: $(python3 -c "print(f'{float('$CRM_SEC'):.1f}')")s (target <30s after r367-r371 deploy)"
fi

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
  bash "$ROOT/scripts/print-deploy-window-summary.sh" || true
  echo ""
  echo "*** DEPLOY WINDOW ACTIVE — run:"
  echo "  bash trading-platform/scripts/run-deploy-window.sh"
  echo "  # preflight only:"
  echo "  bash trading-platform/scripts/run-deploy-window.sh --dry-run"
  echo "  # or step-by-step:"
  echo "  bash trading-platform/scripts/verify-pre-deploy.sh"
  echo "  TRIGGER_DEPLOY=true bash trading-platform/scripts/sync-render-env.sh"
  echo "  bash trading-platform/scripts/wait-for-render-deploy.sh --verify"
  exit 10
fi

echo ""
echo "After CME open (22:00 UTC):"
echo "  bash trading-platform/scripts/verify-cme-post-open.sh --watch 120"
echo ""
echo "Monday before US open (13:30 UTC):"
echo "  bash trading-platform/scripts/verify-us-stocks-open.sh --watch 120"
echo "Monday after US open:"
echo "  bash trading-platform/scripts/verify-us-stocks-post-open.sh --watch 120"
echo ""
echo "--- CRM learning loop ---"
bash "$ROOT/scripts/verify-crm-learning.sh" || true
