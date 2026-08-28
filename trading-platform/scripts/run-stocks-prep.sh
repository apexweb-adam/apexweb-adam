#!/usr/bin/env bash
# Trigger pre-US-session TradingView signal refresh on production.
set -euo pipefail

BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"
SECRET="${TRADINGVIEW_WEBHOOK_SECRET:-}"

if [[ -z "$SECRET" && -f "$(dirname "$0")/../.env" ]]; then
  SECRET=$(grep -E '^TRADINGVIEW_WEBHOOK_SECRET=' "$(dirname "$0")/../.env" | cut -d= -f2-)
fi

if [[ -z "$SECRET" ]]; then
  echo "Set TRADINGVIEW_WEBHOOK_SECRET or pass via trading-platform/.env" >&2
  exit 1
fi

echo "Backend: $BACKEND"
curl -fsS -X POST "$BACKEND/api/admin/run-stocks-prep" \
  -H 'Content-Type: application/json' \
  -d "{\"secret\":\"$SECRET\"}" | python3 -m json.tool
