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
