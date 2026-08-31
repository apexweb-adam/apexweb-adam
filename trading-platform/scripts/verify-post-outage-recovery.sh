#!/usr/bin/env bash
# Run all post-outage recovery verifiers (US stocks, CME, crypto).
# Usage:
#   verify-post-outage-recovery.sh [--watch SECONDS] [--once] [--skip-stocks]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/fetch_json.sh
source "$ROOT/scripts/lib/fetch_json.sh"
BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"
WATCH_INTERVAL=""
ONCE=false
SKIP_STOCKS=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --watch)
      WATCH_INTERVAL="${2:-120}"
      shift 2
      ;;
    --once)
      ONCE=true
      shift
      ;;
    --skip-stocks)
      SKIP_STOCKS=true
      shift
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

watch_args() {
  if [[ "$ONCE" == true ]]; then
    return 0
  fi
  if [[ -n "$WATCH_INTERVAL" ]]; then
    echo "--watch" "$WATCH_INTERVAL"
  fi
}

echo "=== Post-Outage Recovery Verification — $(date -u '+%Y-%m-%d %H:%M UTC') ==="
echo "Backend: $BACKEND"
echo ""

if ! check_backend_suspension "$BACKEND"; then
  echo "Backend billing-suspended — post-outage verification unavailable"
  echo "Fix billing at: ${RENDER_DASHBOARD_URL:-https://dashboard.render.com/web/srv-da848ms9v7es739k38jg}"
  CATCHUP_LEFT="$(python3 - << 'PY' 2>/dev/null || true
from datetime import datetime, timezone
now = datetime.now(timezone.utc)
if now.isoweekday() != 1 or now.hour < 13 or now.hour >= 21:
    raise SystemExit(0)
session_end = now.replace(hour=21, minute=0, second=0, microsecond=0)
catchup_left = max(0, int((session_end.timestamp() - now.timestamp()) // 60))
if catchup_left > 0:
    print(catchup_left)
PY
  )"
  if [[ -n "$CATCHUP_LEFT" && "$CATCHUP_LEFT" -gt 0 && "$CATCHUP_LEFT" -le 30 ]]; then
    echo "URGENT: ${CATCHUP_LEFT} min until US cash close — resume billing to run outage_recovery_scan"
  elif python3 - << 'PY' 2>/dev/null | grep -q closed; then
from datetime import datetime, timezone
now = datetime.now(timezone.utc)
if now.isoweekday() == 1 and now.hour >= 21:
    print("closed")
PY
    echo "US cash session closed — resume billing for commodities/crypto held scan + Tue open prep"
  fi
  echo ""
  bash "$ROOT/scripts/print-outage-status.sh" 2>/dev/null | tail -n +2 || true
  exit 2
fi

echo ""

DOW="$(date -u +%u)"
HOUR="$(date -u +%H)"
failures=0

if [[ "$SKIP_STOCKS" == false && "$DOW" == "1" && "$HOUR" -ge 13 && "$HOUR" -le 21 ]]; then
  echo "--- US stocks ---"
  if ! bash "$ROOT/scripts/verify-us-stocks-post-open.sh" $(watch_args); then
    failures=$((failures + 1))
  fi
  echo ""
fi

if [[ "$DOW" -ge 1 && "$DOW" -le 5 ]]; then
  echo "--- CME / commodities ---"
  if ! bash "$ROOT/scripts/verify-cme-post-open.sh" $(watch_args); then
    failures=$((failures + 1))
  fi
  echo ""
fi

echo "--- Crypto 24/7 ---"
if ! bash "$ROOT/scripts/verify-crypto-held.sh" $(watch_args); then
  failures=$((failures + 1))
fi

echo ""
if [[ "$failures" -gt 0 ]]; then
  echo "Post-outage recovery: $failures verifier(s) failed"
  exit 1
fi
echo "Post-outage recovery: all verifiers passed"

STATUS=$(fetch_json "$BACKEND/api/status" 60 2)
STATUS="$STATUS" python3 << 'PY'
import json, os
status = json.loads(os.environ.get("STATUS") or "{}")
learning = status.get("learning") or {}
content = status.get("content_study") or {}
intel_count = learning.get("intel_pattern_count") or 0
if learning:
    print(
        f"Learning loop: analyses={learning.get('trade_analyses')} "
        f"reviews={learning.get('daily_reviews')} "
        f"insights_applied={learning.get('insights_applied')} "
        f"intel_pattern_alerts={intel_count}"
    )
    for alert in (learning.get("intel_pattern_alerts") or [])[:3]:
        print(f"  intel_alert={alert}")
if content.get("recent"):
    print(
        f"Content study: applied={content.get('insights_applied') or 0} "
        f"recent={len(content.get('recent') or [])}"
    )
    for row in (content.get("recent") or [])[:3]:
        label = row.get("source_label") or row.get("source_type") or "unknown"
        title = (row.get("title") or "")[:48]
        state = "applied" if row.get("applied") else "pending"
        print(f"  content_study [{label}] {title} ({state})")
PY
