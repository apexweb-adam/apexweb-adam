#!/usr/bin/env bash
# Store axiom.trade session token on production for optional server-side feed polling.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"
SECRET="${TRADINGVIEW_WEBHOOK_SECRET:-}"
SESSION="${1:-${AXIOM_SESSION_TOKEN:-}}"

if [[ -z "$SECRET" && -f "$ROOT/.env" ]]; then
  SECRET=$(grep '^TRADINGVIEW_WEBHOOK_SECRET=' "$ROOT/.env" | cut -d= -f2-)
fi

if [[ -z "$SECRET" ]]; then
  echo "Set TRADINGVIEW_WEBHOOK_SECRET" >&2
  exit 1
fi

if [[ -z "$SESSION" ]]; then
  echo "Usage: AXIOM_SESSION_TOKEN=... $0" >&2
  echo "   or: $0 '<session_token>'" >&2
  echo "Get token: axiom.trade → DevTools → Network → Authorization header on API calls" >&2
  echo "Easier: install Tampermonkey userscript from $BACKEND/api/axiom/userscript (auto-syncs while tab open)" >&2
  exit 1
fi

curl -fsS -X POST "$BACKEND/api/admin/set-axiom-session" \
  -H 'Content-Type: application/json' \
  -d "{\"secret\":\"$SECRET\",\"session_token\":\"$SESSION\"}" | python3 -m json.tool

echo ""
echo "Trigger immediate poll:"
echo "  curl -X POST $BACKEND/api/admin/poll-axiom-feed -H 'Content-Type: application/json' -d '{\"secret\":\"<secret>\"}'"
