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

if [[ -z "$EXPECTED" ]]; then
  echo "verify-dashboard-bundle: could not read expected bundle revision"
  exit 1
fi

echo "=== Dashboard bundle check ==="
echo "URL:      $DASHBOARD_URL"
echo "Expected: $EXPECTED"

cfg="$(curl -fsSL --max-time 25 "${DASHBOARD_URL%/}/api/config" 2>/dev/null || echo '{}')"
actual=""
active_gate=""
if command -v jq >/dev/null 2>&1; then
  actual="$(echo "$cfg" | jq -r '.bundleRevision // empty' 2>/dev/null || true)"
  active_gate="$(echo "$cfg" | jq -r '.features.activeGate // false' 2>/dev/null || true)"
else
  actual="$(python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('bundleRevision') or '')" <<<"$cfg" 2>/dev/null || true)"
  active_gate="$(python3 -c "import json,sys; d=json.load(sys.stdin); print((d.get('features') or {}).get('activeGate', False))" <<<"$cfg" 2>/dev/null || true)"
fi

if [[ -z "$actual" ]]; then
  echo "WARN: /api/config unreachable or missing bundleRevision"
  dash_json="$(curl -fsSL --max-time 15 "$BACKEND_URL/api/dashboard-url" 2>/dev/null || echo '{}')"
  if command -v jq >/dev/null 2>&1; then
    rec="$(echo "$dash_json" | jq -r '.recommended_url // empty' 2>/dev/null || true)"
    rev="$(echo "$dash_json" | jq -r '.vercel_bundle_revision // empty' 2>/dev/null || true)"
    promote="$(echo "$dash_json" | jq -r '.vercel_promote_deployment_id // empty' 2>/dev/null || true)"
    [[ -n "$rec" ]] && echo "Backend recommends: $rec (bundle $rev)"
    [[ -n "$promote" ]] && echo "Promote deployment: $promote"
  fi
  exit 0
fi

echo "Actual:   $actual (activeGate=$active_gate)"

if [[ "$actual" == "$EXPECTED" ]]; then
  echo "OK: dashboard bundle matches code target"
  exit 0
fi

# Extract numeric rank for readable lag message
exp_num="$(echo "$EXPECTED" | sed -n 's/.*-r\([0-9]*\)$/\1/p')"
act_num="$(echo "$actual" | sed -n 's/.*-r\([0-9]*\)$/\1/p')"
if [[ -n "$exp_num" && -n "$act_num" ]]; then
  lag=$((exp_num - act_num))
  echo "WARN: dashboard bundle behind by r$lag ($actual vs $EXPECTED)"
else
  echo "WARN: dashboard bundle mismatch ($actual vs $EXPECTED)"
fi

dash_json="$(curl -fsSL --max-time 15 "$BACKEND_URL/api/dashboard-url" 2>/dev/null || echo '{}')"
if command -v jq >/dev/null 2>&1; then
  rec="$(echo "$dash_json" | jq -r '.recommended_url // empty' 2>/dev/null || true)"
  promote="$(echo "$dash_json" | jq -r '.vercel_promote_deployment_id // empty' 2>/dev/null || true)"
  [[ -n "$rec" ]] && echo "Use verified preview until promote: $rec"
  [[ -n "$promote" ]] && echo "Promote when quota allows: bash trading-platform/scripts/promote-vercel-dashboard.sh $promote"
fi

exit 0
