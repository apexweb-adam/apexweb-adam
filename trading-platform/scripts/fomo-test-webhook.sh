#!/usr/bin/env bash
# Smoke-test the production fomo webhook via admin test endpoint.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"
SECRET="${TRADINGVIEW_WEBHOOK_SECRET:-}"

if [[ -z "$SECRET" && -f "$ROOT/.env" ]]; then
  SECRET=$(grep -E '^TRADINGVIEW_WEBHOOK_SECRET=' "$ROOT/.env" | cut -d= -f2-)
fi

if [[ -z "$SECRET" ]]; then
  echo "Set TRADINGVIEW_WEBHOOK_SECRET or add it to trading-platform/.env" >&2
  exit 1
fi

SYMBOL="${1:-WIF}"
ACTION="${2:-buy}"
TRADER_RANK="${3:-3}"

curl -fsS -X POST "$BACKEND/api/admin/test-fomo-webhook" \
  -H 'Content-Type: application/json' \
  -d "{\"secret\":\"$SECRET\",\"symbol\":\"$SYMBOL\",\"action\":\"$ACTION\",\"trader_rank\":$TRADER_RANK}" \
  | python3 -m json.tool
