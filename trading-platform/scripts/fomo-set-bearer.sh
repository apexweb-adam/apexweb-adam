#!/usr/bin/env bash
# Store fomo.family bearer token on production for server-side trade polling.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"
SECRET="${TRADINGVIEW_WEBHOOK_SECRET:-}"
BEARER="${1:-${FOMO_BEARER_TOKEN:-}}"

if [[ -z "$SECRET" && -f "$ROOT/.env" ]]; then
  SECRET=$(grep '^TRADINGVIEW_WEBHOOK_SECRET=' "$ROOT/.env" | cut -d= -f2-)
fi

if [[ -z "$SECRET" ]]; then
  echo "Set TRADINGVIEW_WEBHOOK_SECRET" >&2
  exit 1
fi

if [[ -z "$BEARER" ]]; then
  echo "Usage: FOMO_BEARER_TOKEN=eyJ... $0" >&2
  echo "   or: $0 'eyJ...'" >&2
  echo "Get bearer: fomo.family → DevTools → Network → any prod-api.fomo.family request → Authorization: Bearer ..." >&2
  exit 1
fi

curl -fsS -X POST "$BACKEND/api/admin/set-fomo-bearer" \
  -H 'Content-Type: application/json' \
  -d "{\"secret\":\"$SECRET\",\"bearer_token\":\"$BEARER\"}" | python3 -m json.tool

echo ""
python3 << 'PY' "$BEARER"
import base64, json, sys
from datetime import datetime, timezone
token = sys.argv[1]
parts = token.split(".")
if len(parts) >= 2:
    payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        exp = payload.get("exp")
        if exp:
            expires = datetime.fromtimestamp(exp, tz=timezone.utc)
            mins = int((expires - datetime.now(timezone.utc)).total_seconds() // 60)
            print(f"Bearer expires: {expires.isoformat()} ({mins} min remaining)")
    except Exception:
        pass
PY

echo ""
echo "Trigger immediate poll:"
echo "  curl -X POST $BACKEND/api/admin/poll-fomo-trades -H 'Content-Type: application/json' -d '{\"secret\":\"<secret>\"}'"
