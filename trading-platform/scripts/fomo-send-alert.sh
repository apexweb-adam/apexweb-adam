#!/usr/bin/env bash
# Manually forward a fomo.family-style trader alert to Apex (tune traders/symbols).
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

export FOMO_SECRET="$SECRET"
export FOMO_SYMBOL="${1:-WIF}"
export FOMO_ACTION="${2:-buy}"
export FOMO_TRADER="${3:-manual_trader}"
export FOMO_RANK="${4:-10}"
export FOMO_USD="${5:-2500}"
export FOMO_CHAIN="${6:-solana}"
export FOMO_MESSAGE="${7:-Manual fomo alert for tuning}"
export FOMO_BACKEND="$BACKEND"

payload=$(python3 - <<'PY'
import json
import os

print(json.dumps({
  "secret": os.environ["FOMO_SECRET"],
  "event_type": "trade",
  "symbol": os.environ["FOMO_SYMBOL"],
  "action": os.environ["FOMO_ACTION"],
  "trader_name": os.environ["FOMO_TRADER"],
  "trader_rank": int(os.environ["FOMO_RANK"]),
  "trader_pnl_pct": 120.0,
  "chain": os.environ["FOMO_CHAIN"],
  "amount_usd": float(os.environ["FOMO_USD"]),
  "message": os.environ["FOMO_MESSAGE"],
}))
PY
)

echo "POST $BACKEND/api/webhooks/fomo"
echo "$payload" | python3 -m json.tool
curl -fsS -X POST "$BACKEND/api/webhooks/fomo" \
  -H 'Content-Type: application/json' \
  -d "$payload" | python3 -m json.tool
