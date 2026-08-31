#!/usr/bin/env bash
# Attempt to promote verified CRM preview to production -flame alias (non-blocking).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"

if [[ -z "${VERCEL_TOKEN:-}" ]]; then
  echo "○ VERCEL_TOKEN not set — skip dashboard promote"
  exit 0
fi

DASH_JSON=$(curl -fsS -m 20 "$BACKEND/api/dashboard-url" 2>/dev/null || echo "{}")
read -r PROMOTE_ID PREVIEW_URL <<EOF
$(PROMOTE_JSON="$DASH_JSON" python3 << 'PY'
import json, os
data = json.loads(os.environ.get("PROMOTE_JSON") or "{}")
print(data.get("vercel_promote_deployment_id") or "")
print(data.get("verified_preview_url") or data.get("verified_dashboard_url") or data.get("recommended_url") or "")
PY
)
EOF

if [[ -z "$PROMOTE_ID" ]]; then
  echo "○ No vercel_promote_deployment_id from /api/dashboard-url — skip promote"
  exit 0
fi

echo "Attempting Vercel promote: $PROMOTE_ID"
if bash "$ROOT/scripts/promote-vercel-dashboard.sh" "$PROMOTE_ID" "${PREVIEW_URL:-}"; then
  echo "✓ Dashboard production alias updated"
else
  echo "WARN: dashboard promote failed (non-blocking — use verified preview URL)"
fi

exit 0
