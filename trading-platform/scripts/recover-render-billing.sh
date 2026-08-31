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

EXPECTED_REVISION="$(grep '^EXPECTED_PLATFORM_REVISION' "$ROOT/backend/app/engines/deploy_status.py" | sed -n 's/.*"\([^"]*\)".*/\1/p')"
wake_backend "$BACKEND" 3
RUNNING_REV="$(production_platform_revision "$BACKEND")"
echo "Production revision: ${RUNNING_REV:-unknown} (target $EXPECTED_REVISION)"

if [[ -n "$EXPECTED_REVISION" ]] && production_revision_behind "$BACKEND" "$EXPECTED_REVISION"; then
  echo ""
  echo "=== Trigger deploy (billing recovery — revision behind main) ==="
  if trigger_render_deploy; then
    echo "Waiting for deploy to reach $EXPECTED_REVISION..."
  else
    echo "Manual deploy required: Render dashboard → Manual Deploy → latest main"
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

if [[ "$SKIP_STOCKS" == false && "$DOW" -ge 1 && "$DOW" -le 5 ]]; then
  echo ""
  echo "=== Commodities scan preview (CME weekday session) ==="
  fetch_json "$BACKEND/api/bots/commodities/scan-preview" 120 3 > /tmp/commodities-scan.json 2>/dev/null || true
  if [[ -f /tmp/commodities-scan.json ]]; then
    python3 - << 'PY'
import json
from pathlib import Path
data = json.loads(Path("/tmp/commodities-scan.json").read_text(encoding="utf-8") or "{}")
symbols = data.get("symbols") or []
held = [row["symbol"] for row in symbols if row.get("held")]
open_ready = [row["symbol"] for row in symbols if row.get("would_enter")]
print(f"  commodities symbols={len(symbols)} held={held or 'none'} would_enter={open_ready or 'none'}")
PY
  fi
fi

echo ""
echo "Recovery complete. Check CRM dashboard and gate metrics."
DOW="$(date -u +%u)"
HOUR="$(date -u +%H)"
if [[ "$DOW" == "1" && "$HOUR" -ge 13 && "$HOUR" -le 18 ]]; then
  echo ""
  echo "Note: stocks burst-recovery runs within 60 min of US open (13:30 UTC)."
  echo "Platform-outage recovery extends to 270 min when open-ready symbols were queued (e.g. AAPL)."
  echo "Check us-stocks-open-checklist for has_burst_scan / has_auto_entry."
fi
