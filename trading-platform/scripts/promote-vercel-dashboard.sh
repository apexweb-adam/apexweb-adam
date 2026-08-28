#!/usr/bin/env bash
# Promote verified r27 CRM preview to production -flame alias.
# Requires VERCEL_TOKEN (GitHub secret or local export).
set -euo pipefail

TEAM_ID="${VERCEL_ORG_ID:-team_K7OUE7uroVXeVUf42cUAQvAl}"
PROJECT_ID="${VERCEL_PROJECT_ID:-prj_HGbG5vHgfutHi31QfXDqSsTnTAGv}"
DEPLOYMENT_ID="${1:-dpl_9cVRxRBgcHVStS2A35ZmPFbwrZTS}"
PREVIEW_URL="${2:-https://apex-trading-dashboard-fh95xdpz2-apexweb-adams-projects.vercel.app}"
PROD_URL="https://apex-trading-dashboard-flame.vercel.app"

if [[ -z "${VERCEL_TOKEN:-}" ]]; then
  echo "VERCEL_TOKEN not set."
  echo "Manual: Vercel → apex-trading-dashboard → Deployments → $DEPLOYMENT_ID → Promote to Production"
  echo "Preview (works now): $PREVIEW_URL"
  exit 1
fi

echo "Verifying preview $PREVIEW_URL ..."
curl -fsS "${PREVIEW_URL}/api/config" -o /tmp/preview-config.json
python3 << 'PY'
import json, sys
with open("/tmp/preview-config.json") as f:
    cfg = json.load(f)
rev = cfg.get("bundleRevision")
if not (cfg.get("features") or {}).get("activeGate"):
    print("Preview missing activeGate feature")
    sys.exit(1)
print(f"Preview bundleRevision={rev}")
PY

echo "Promoting $DEPLOYMENT_ID to production ..."
HTTP=$(curl -fsS -o /tmp/promote.json -w "%{http_code}" -X POST \
  "https://api.vercel.com/v10/projects/${PROJECT_ID}/promote/${DEPLOYMENT_ID}?teamId=${TEAM_ID}" \
  -H "Authorization: Bearer ${VERCEL_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{}')
echo "Promote HTTP $HTTP"
cat /tmp/promote.json
if [[ "$HTTP" != "201" && "$HTTP" != "200" && "$HTTP" != "202" ]]; then
  echo "Promote failed (Vercel free tier: 100 deploys/day limit may apply)" >&2
  exit 1
fi

sleep 15
curl -fsS "${PROD_URL}/api/config" -o /tmp/prod-config.json || echo "{}" > /tmp/prod-config.json
echo "Production config:"
cat /tmp/prod-config.json
