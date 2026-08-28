#!/usr/bin/env bash
# Store Vercel deploy hook in production platform_settings (not in git).
# Get hook URL: Vercel → apex-trading-dashboard → Settings → Git → Deploy Hooks (branch: main)
set -euo pipefail

BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"
HOOK_URL="${1:-${VERCEL_DEPLOY_HOOK:-}}"
SECRET="${TRADINGVIEW_WEBHOOK_SECRET:-}"

if [[ -z "$SECRET" && -f "$(dirname "$0")/../.env" ]]; then
  SECRET=$(grep '^TRADINGVIEW_WEBHOOK_SECRET=' "$(dirname "$0")/../.env" | cut -d= -f2- || true)
fi

if [[ -z "$HOOK_URL" ]]; then
  echo "Usage: VERCEL_DEPLOY_HOOK=https://api.vercel.com/v1/integrations/deploy/... $0"
  echo "   or: $0 'https://api.vercel.com/v1/integrations/deploy/...'"
  echo ""
  echo "Find hook: Vercel → apex-trading-dashboard → Settings → Git → Deploy Hooks (main)"
  exit 1
fi

if [[ -z "$SECRET" ]]; then
  echo "Set TRADINGVIEW_WEBHOOK_SECRET" >&2
  exit 1
fi

curl -fsS -X POST "$BACKEND/api/admin/set-vercel-deploy-hook" \
  -H 'Content-Type: application/json' \
  -d "{\"secret\":\"$SECRET\",\"hook_url\":\"$HOOK_URL\"}"

echo ""
echo "Hook stored. Trigger production deploy:"
echo "  curl -X POST \"$BACKEND/api/admin/trigger-vercel-deploy\" -H 'Content-Type: application/json' -d '{\"secret\":\"...\"}'"
