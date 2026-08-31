#!/usr/bin/env bash
# Wait for Render billing suspension to clear, then run full platform recovery.
# Usage:
#   recover-render-billing.sh [--wait SECONDS] [--interval SECONDS] [--skip-stocks]
#
# Run after resolving billing in Render dashboard and resuming the service.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/fetch_json.sh
source "$ROOT/scripts/lib/fetch_json.sh"
BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"
MAX_WAIT="${MAX_WAIT:-1800}"
INTERVAL="${INTERVAL:-30}"
SKIP_STOCKS=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --wait)
      MAX_WAIT="${2:-1800}"
      shift 2
      ;;
    --interval)
      INTERVAL="${2:-30}"
      shift 2
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

echo "=== Render Billing Recovery — $(date -u '+%Y-%m-%d %H:%M UTC') ==="
echo "Backend: $BACKEND"
echo "Max wait for resume: ${MAX_WAIT}s (poll every ${INTERVAL}s)"
echo ""

if check_backend_suspension "$BACKEND" 2>/dev/null; then
  echo "Backend is online — proceeding to deploy verification."
else
  echo "Backend billing-suspended. Resolve billing and resume in Render, then wait..."
  echo "Dashboard: ${RENDER_DASHBOARD_URL}"
  echo ""
  deadline=$(( $(date +%s) + MAX_WAIT ))
  while [[ $(date +%s) -lt $deadline ]]; do
    if check_backend_suspension "$BACKEND" 2>/dev/null; then
      echo "Backend resumed at $(date -u '+%H:%M UTC')"
      break
    fi
    echo "  still suspended — next check in ${INTERVAL}s ($(date -u '+%H:%M UTC'))"
    sleep "$INTERVAL"
  done
  if ! check_backend_suspension "$BACKEND" 2>/dev/null; then
    echo "Timed out waiting for billing suspension to clear." >&2
    exit 2
  fi
fi

echo ""
bash "$ROOT/scripts/wait-for-render-deploy.sh" --verify --max-wait "$MAX_WAIT" --interval "$INTERVAL"

echo ""
bash "$ROOT/scripts/verify-platform.sh" || true

DOW="$(date -u +%u)"
HOUR="$(date -u +%H)"
if [[ "$SKIP_STOCKS" == false && "$DOW" == "1" && "$HOUR" -ge 13 && "$HOUR" -le 21 ]]; then
  echo ""
  echo "=== US stocks post-open verification (Monday session) ==="
  bash "$ROOT/scripts/verify-us-stocks-post-open.sh" --watch 120 || true
fi

echo ""
echo "Recovery complete. Check CRM dashboard and gate metrics."
