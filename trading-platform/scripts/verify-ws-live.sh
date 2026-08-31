#!/usr/bin/env bash
# Verify WebSocket live CRM payload (paper_trading_only, integrations, learning).
# Usage: verify-ws-live.sh [--strict]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/fetch_json.sh
source "$ROOT/scripts/lib/fetch_json.sh"
BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"
WS_URL="${BACKEND_WS_URL:-${BACKEND/https:\/\//wss://}/api/ws}"
STRICT=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --strict)
      STRICT=true
      shift
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

pass=0
fail=0
warn=0

ok() { echo "✓ $*"; pass=$((pass + 1)); }
bad() { echo "✗ $*"; fail=$((fail + 1)); }
note() { echo "○ $*"; warn=$((warn + 1)); }

echo "=== WebSocket Live CRM Verification — $(date -u '+%Y-%m-%d %H:%M UTC') ==="
echo "Backend: $BACKEND"
echo "WebSocket: $WS_URL"
echo ""

if ! check_backend_suspension "$BACKEND"; then
  bad "Backend billing-suspended — WebSocket live checks blocked"
  exit 1
fi

wake_backend "$BACKEND" 2

export WS_URL
WS_RC=0
WS_OUT=$(python3 << 'PY' 2>&1) || WS_RC=$?
import asyncio
import json
import os
import sys

try:
    import websockets
except ImportError:
    print("missing_websockets_package")
    sys.exit(5)

url = os.environ["WS_URL"]


async def probe():
    async with websockets.connect(url, open_timeout=45, close_timeout=5) as ws:
        raw = await asyncio.wait_for(ws.recv(), timeout=90)
        return json.loads(raw)


try:
    payload = asyncio.run(probe())
except Exception as exc:
    print(f"ws_connect_failed={exc}")
    sys.exit(1)

if payload.get("type") != "update":
    print(f"unexpected_type={payload.get('type')}")
    sys.exit(2)

if payload.get("paper_trading_only") is not True:
    print(f"paper_trading_only={payload.get('paper_trading_only')}")
    sys.exit(3)

integrations = payload.get("integrations") or {}
for key in (
    "newsapi",
    "reddit_oauth",
    "x_intel_collection_mode",
    "polymarket_market_scanner",
    "tradingview_webhook",
):
    if key not in integrations:
        print(f"missing_integration={key}")
        sys.exit(4)

learning = payload.get("learning") or {}
if "intel_pattern_alerts" not in learning:
    print("missing_learning_intel_pattern_alerts")
    sys.exit(6)

content_study = payload.get("content_study") or {}
if "recent" not in content_study:
    print("missing_content_study_recent")
    sys.exit(9)

sources = payload.get("intel_sources") or []
source_names = {row.get("source") for row in sources if isinstance(row, dict)}
for required in ("political", "youtube", "tiktok", "newsapi", "x", "reddit"):
    if required not in source_names:
        print(f"missing_intel_source={required}")
        sys.exit(7)

bots = payload.get("bots") or []
bot_types = {row.get("bot_type") for row in bots if isinstance(row, dict)}
for required in ("crypto", "stocks_futures", "commodities"):
    if required not in bot_types:
        print(f"missing_core_bot={required}")
        sys.exit(8)

print(
    f"ws_update paper_only=True integrations={len(integrations)} "
    f"intel_sources={len(sources)} bots={len(bots)} "
    f"learning_analyses={learning.get('trade_analyses', 0)} "
    f"content_study_recent={len(content_study.get('recent') or [])}"
)
sys.exit(0)
PY

case "$WS_RC" in
  0)
    echo "$WS_OUT"
    ok "WebSocket live payload (paper_trading_only, integrations, core bots, intel sources)"
    ;;
  1)
    echo "$WS_OUT"
    bad "WebSocket connect or first message failed"
    ;;
  2)
    echo "$WS_OUT"
    bad "WebSocket payload missing type=update"
    ;;
  3)
    echo "$WS_OUT"
    bad "WebSocket payload paper_trading_only is not true"
    ;;
  4)
    echo "$WS_OUT"
    bad "WebSocket integrations missing required fields (r132+)"
    ;;
  5)
    note "websockets package missing — pip install websockets in CI image"
    ;;
  6)
    echo "$WS_OUT"
    bad "WebSocket learning block missing intel_pattern_alerts"
    ;;
  7)
    echo "$WS_OUT"
    bad "WebSocket intel_sources missing political/youtube/tiktok (r133+)"
    ;;
  8)
    echo "$WS_OUT"
    bad "WebSocket bots missing core three-market bots"
    ;;
  9)
    echo "$WS_OUT"
    bad "WebSocket content_study block missing recent highlights (r137+)"
    ;;
  *)
    echo "$WS_OUT"
    note "WebSocket verification inconclusive (exit $WS_RC)"
    ;;
esac

echo ""
echo "Results: $pass passed, $fail failed, $warn notes"
if [[ "$fail" -gt 0 ]]; then
  if [[ "$STRICT" == "true" ]]; then
    exit 1
  fi
  note "Re-run with --strict to fail on blockers"
fi
