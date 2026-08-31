#!/usr/bin/env bash
# Compare dashboard /api/config bundleRevision against code target.
# Non-blocking: always exit 0 (warn on mismatch) so post-deploy is not blocked by Vercel lag.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_URL="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"
DASHBOARD_URL="${DASHBOARD_URL:-https://apex-trading-dashboard-flame.vercel.app}"
EXPECTED="${EXPECTED_DASHBOARD_BUNDLE:-}"

if [[ -z "$EXPECTED" ]]; then
  EXPECTED="$(grep -E '^EXPECTED_DASHBOARD_BUNDLE' "$ROOT/backend/app/engines/deploy_status.py" \
    | sed -n 's/.*"\([^"]*\)".*/\1/p' | head -1 || true)"
fi
if [[ -z "$EXPECTED" ]]; then
  EXPECTED="$(grep -E 'export const DASHBOARD_BUNDLE_REVISION' "$ROOT/dashboard/lib/deploy-health.ts" \
    | sed -n 's/.*"\([^"]*\)".*/\1/p' | head -1 || true)"
fi

check_url() {
  local url="$1"
  local label="$2"
  local cfg actual gate
  cfg="$(curl -fsSL --max-time 12 "${url%/}/api/config" 2>/dev/null || echo '{}')"
  if command -v jq >/dev/null 2>&1; then
    actual="$(echo "$cfg" | jq -r '.bundleRevision // empty' 2>/dev/null || true)"
    gate="$(echo "$cfg" | jq -r '.features.activeGate // false' 2>/dev/null || true)"
  else
    actual="$(python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('bundleRevision') or '')" <<<"$cfg" 2>/dev/null || true)"
    gate="$(python3 -c "import json,sys; d=json.load(sys.stdin); print((d.get('features') or {}).get('activeGate', False))" <<<"$cfg" 2>/dev/null || true)"
  fi
  echo "$label|$url|$actual|$gate"
}

if [[ -z "$EXPECTED" ]]; then
  echo "verify-dashboard-bundle: could not read expected bundle revision"
  exit 1
fi

echo "=== Dashboard bundle check ==="
echo "Expected: $EXPECTED"

primary="$(check_url "$DASHBOARD_URL" "production")"
IFS='|' read -r _ primary_url actual active_gate <<<"$primary"
echo "URL:      $primary_url"
echo "Actual:   ${actual:-?} (activeGate=${active_gate:-?})"

if [[ -z "$actual" ]]; then
  echo "WARN: /api/config unreachable or missing bundleRevision"
  exit 0
fi

if [[ "$actual" == "$EXPECTED" ]]; then
  echo "OK: dashboard bundle matches code target"
else
  exp_num="$(echo "$EXPECTED" | sed -n 's/.*-r\([0-9]*\)$/\1/p')"
  act_num="$(echo "$actual" | sed -n 's/.*-r\([0-9]*\)$/\1/p')"
  if [[ -n "$exp_num" && -n "$act_num" ]]; then
    lag=$((exp_num - act_num))
    echo "WARN: dashboard bundle behind by r$lag ($actual vs $EXPECTED)"
  else
    echo "WARN: dashboard bundle mismatch ($actual vs $EXPECTED)"
  fi
fi

dash_cfg="$(curl -fsSL --max-time 12 "${primary_url%/}/api/config" 2>/dev/null || echo '{}')"
health_suspended="$(echo "$dash_cfg" | python3 -c "import json,sys; d=json.load(sys.stdin); print((d.get('backendHealth') or {}).get('suspended', ''))" 2>/dev/null || true)"
if [[ "$health_suspended" == "True" || "$health_suspended" == "true" ]]; then
  echo "Note: dashboard reports backendHealth.suspended=true (Render billing outage UX active)"
fi

if [[ "$actual" == "$EXPECTED" ]]; then
  exit 0
fi

dash_json="$(curl -fsSL --max-time 12 "$BACKEND_URL/api/dashboard-url" 2>/dev/null || echo '{}')"
rec_url=""
promote=""
if command -v jq >/dev/null 2>&1; then
  rec_url="$(echo "$dash_json" | jq -r '.recommended_url // empty' 2>/dev/null || true)"
  promote="$(echo "$dash_json" | jq -r '.vercel_promote_deployment_id // empty' 2>/dev/null || true)"
fi

if [[ -n "$rec_url" && "$rec_url" != "$primary_url" ]]; then
  rec="$(check_url "$rec_url" "recommended")"
  IFS='|' read -r _ rec_url rec_actual rec_gate <<<"$rec"
  echo "Recommended: $rec_url → ${rec_actual:-?} (activeGate=${rec_gate:-?})"
  if [[ -n "$rec_actual" && "$rec_actual" == "$EXPECTED" ]]; then
    echo "OK: verified preview has target bundle — use recommended URL until flame promote"
    exit 0
  fi
fi

[[ -n "$promote" ]] && echo "Promote when quota allows: bash trading-platform/scripts/promote-vercel-dashboard.sh $promote"
echo "Note: Vercel hobby build limit may block new r98 deploys — alias promote only helps if a preview already built r98"

exit 0
