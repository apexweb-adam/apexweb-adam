#!/usr/bin/env bash
# After Render deploy: print Vercel env vars and optionally update vercel.json
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 https://your-service.onrender.com" >&2
  exit 1
fi

BACKEND_URL="${1%/}"
WS_URL="${BACKEND_URL/https:\/\//wss://}"

echo ""
echo "=== Vercel Environment Variables ==="
echo "BACKEND_URL=$BACKEND_URL"
echo "BACKEND_WS_URL=$WS_URL"
echo ""
echo "Vercel → apex-trading-dashboard → Settings → Environment Variables"
echo "Add both vars for Production, then redeploy (or wait for next push)."
echo ""
echo "=== TradingView Webhook ==="
echo "$BACKEND_URL/api/webhooks/tradingview"
echo ""
echo "=== Health check ==="
curl -fsS "$BACKEND_URL/api/health" && echo
