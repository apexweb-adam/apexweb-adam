#!/usr/bin/env bash
# Store Render deploy hook in production platform_settings (not in git).
# Get hook URL: Render Dashboard → apex-trading-backend → Settings → Deploy Hook
set -euo pipefail

BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"
HOOK_URL="${1:-${RENDER_DEPLOY_HOOK:-}}"
SECRET="${TRADINGVIEW_WEBHOOK_SECRET:-}"

if [[ -z "$SECRET" && -f "$(dirname "$0")/../.env" ]]; then
  SECRET=$(grep '^TRADINGVIEW_WEBHOOK_SECRET=' "$(dirname "$0")/../.env" | cut -d= -f2- || true)
fi

if [[ -z "$HOOK_URL" ]]; then
  echo "Usage: RENDER_DEPLOY_HOOK=https://api.render.com/deploy/srv-...?key=... $0"
  echo "   or: $0 'https://api.render.com/deploy/srv-...?key=...'"
  echo ""
  echo "Find hook: Render Dashboard → apex-trading-backend → Settings → Deploy Hook"
  exit 1
fi

if [[ -z "$SECRET" ]]; then
  echo "Set TRADINGVIEW_WEBHOOK_SECRET" >&2
  exit 1
fi

curl -fsS -X POST "$BACKEND/api/admin/set-deploy-hook" \
  -H 'Content-Type: application/json' \
  -d "{\"secret\":\"$SECRET\",\"hook_url\":\"$HOOK_URL\"}"

echo ""
echo "Hook stored. Trigger redeploy:"
echo "  curl -X POST \"\$RENDER_DEPLOY_HOOK\""
echo "  or POST $BACKEND/api/admin/trigger-deploy with secret + force:true"
