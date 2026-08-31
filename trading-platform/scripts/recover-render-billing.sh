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
    CODE_REV="$EXPECTED_REVISION" python3 - << 'PY' 2>/dev/null || true
import os
from datetime import datetime, timezone
now = datetime.now(timezone.utc)
if now.isoweekday() != 1:
    raise SystemExit(0)
open_at = now.replace(hour=13, minute=30, second=0, microsecond=0)
ext_left = max(0, int((open_at.timestamp() + 270 * 60 - now.timestamp()) // 60))
if ext_left > 0:
    tag = "URGENT" if ext_left <= 30 else "active"
    rev = os.environ.get("CODE_REV") or "?"
    print(f"    grace_remaining_min={ext_left} urgency={tag} deploy_target={rev}")
PY
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

echo ""
echo "=== Platform outage recovery state ==="
STATUS_JSON=$(fetch_json "$BACKEND/api/status" 60 2)
echo "$STATUS_JSON" | CODE_REV="$EXPECTED_REVISION" python3 << 'PY'
import json, os, sys
from datetime import datetime, timezone

data = json.load(sys.stdin)
code_rev = os.environ.get("CODE_REV") or "?"
outage_events = data.get("platform_outage_events") or []
if outage_events:
    newest = outage_events[0]
    gap = newest.get("gap_minutes")
    us = newest.get("us_open_ready_symbols") or []
    cme = newest.get("cme_open_ready_symbols") or []
    held = newest.get("held_open_positions") or []
    print(
        f"  platform_outage_events={len(outage_events)} "
        f"newest_gap_min={gap} us_queued={us or 'none'} cme_queued={cme or 'none'}"
    )
    if held:
        held_summary = ", ".join(
            f"{row.get('symbol')}({row.get('bot_type')})" for row in held[:6]
        )
        extra = f" +{len(held) - 6} more" if len(held) > 6 else ""
        print(f"  outage_held_at_resume={held_summary}{extra}")
    print("  note=startup force-refreshes held-position TV when outage gap logged")
else:
    print("  platform_outage_events=none (no gap logged yet or first heartbeat pending)")

us_checklist = (data.get("session_open_checklists") or {}).get("us_stocks") or {}
outage = us_checklist.get("platform_outage_recovery") or {}
if outage.get("logged"):
    print("  platform_outage_recovery_logged=true")
if outage.get("window_active"):
    print(
        f"  platform_outage_recovery_window=true "
        f"grace_remaining_min={outage.get('grace_minutes_remaining')}"
    )
elif outage.get("logged"):
    print("  platform_outage_recovery_window=expired")

deploy = data.get("deploy") or {}
prod_rev = deploy.get("platform_revision")
if prod_rev and code_rev != "?" and prod_rev != code_rev:
    print(f"  warn=revision_behind running={prod_rev} expected={code_rev}")
elif prod_rev:
    print(f"  deploy_revision={prod_rev}")

bots = (data.get("stats") or {}).get("bots") or {}
open_positions = data.get("open_positions") or []
commodities_held = [
    p.get("symbol")
    for p in open_positions
    if isinstance(p, dict) and p.get("bot_type") == "commodities"
]
crypto_held = [
    p.get("symbol")
    for p in open_positions
    if isinstance(p, dict) and p.get("bot_type") == "crypto"
]
if commodities_held:
    print(f"  commodities_open_positions={commodities_held}")
elif bots.get("commodities", {}).get("active"):
    print("  commodities_bot=active (no open positions reported)")
if crypto_held:
    print(f"  crypto_open_positions={crypto_held}")
elif bots.get("crypto", {}).get("active"):
    print("  crypto_bot=active (no open positions reported)")

now = datetime.now(timezone.utc)
if now.isoweekday() == 1:
    open_at = now.replace(hour=13, minute=30, second=0, microsecond=0)
    ext_left = max(0, int((open_at.timestamp() + 270 * 60 - now.timestamp()) // 60))
    if ext_left > 0:
        print(f"  platform_outage_grace_remaining_min={ext_left}")
    else:
        print("  platform_outage_grace=expired")
PY

DOW="$(date -u +%u)"
HOUR="$(date -u +%H)"
if [[ "$SKIP_STOCKS" == false && "$DOW" == "1" && "$HOUR" -ge 13 && "$HOUR" -le 21 ]]; then
  echo ""
  echo "=== US stocks scan preview (outage catch-up) ==="
  fetch_json "$BACKEND/api/bots/stocks_futures/scan-preview" 120 3 > /tmp/stocks-scan.json 2>/dev/null || true
  if [[ -f /tmp/stocks-scan.json ]]; then
    python3 - << 'PY'
import json
from pathlib import Path
data = json.loads(Path("/tmp/stocks-scan.json").read_text(encoding="utf-8") or "{}")
held = data.get("held_symbols") or []
open_ready = data.get("open_ready_candidates") or []
would_enter = [row.get("symbol") for row in (data.get("symbols") or []) if row.get("would_enter")]
print(f"  stocks held={held or 'none'} open_ready_candidates={open_ready or 'none'}")
if would_enter:
    print(f"  would_enter={would_enter}")
imminent = data.get("stocks_open_imminent_scan")
if imminent:
    print(f"  stocks_open_imminent_scan={imminent}")
PY
  fi
  echo ""
  echo "=== US stocks post-open verification (Monday session) ==="
  bash "$ROOT/scripts/verify-us-stocks-post-open.sh" --watch 120 || true
fi

if [[ "$SKIP_STOCKS" == false && "$DOW" -ge 1 && "$DOW" -le 5 ]]; then
  echo ""
  echo "=== Commodities scan preview (CME weekday session) ==="
  fetch_json "$BACKEND/api/bots/commodities/scan-preview" 120 3 > /tmp/commodities-scan.json 2>/dev/null || true
  fetch_json "$BACKEND/api/gate/cme-reopen-checklist" 90 3 > /tmp/cme-checklist.json 2>/dev/null || true
  if [[ -f /tmp/commodities-scan.json ]]; then
    python3 - << 'PY'
import json
from pathlib import Path
data = json.loads(Path("/tmp/commodities-scan.json").read_text(encoding="utf-8") or "{}")
symbols = data.get("symbols") or []
held = [row["symbol"] for row in symbols if row.get("held")]
open_ready = [row["symbol"] for row in symbols if row.get("would_enter")]
print(f"  commodities symbols={len(symbols)} held={held or 'none'} would_enter={open_ready or 'none'}")
cme_path = Path("/tmp/cme-checklist.json")
if cme_path.is_file():
    cme = json.loads(cme_path.read_text(encoding="utf-8") or "{}")
    outage = cme.get("platform_outage_recovery") or {}
    if outage.get("window_active"):
        print(f"  cme_platform_outage_recovery grace_remaining_min={outage.get('grace_minutes_remaining')}")
PY
  fi
  echo ""
  echo "=== CME post-open verification (weekday session) ==="
  bash "$ROOT/scripts/verify-cme-post-open.sh" --watch 90 || true
fi

echo ""
echo "=== Crypto scan preview (24/7 held-position check) ==="
fetch_json "$BACKEND/api/bots/crypto/scan-preview" 120 3 > /tmp/crypto-scan.json 2>/dev/null || true
if [[ -f /tmp/crypto-scan.json ]]; then
  python3 - << 'PY'
import json
from pathlib import Path
data = json.loads(Path("/tmp/crypto-scan.json").read_text(encoding="utf-8") or "{}")
symbols = data.get("symbols") or []
held = [row["symbol"] for row in symbols if row.get("held")]
would_enter = [row["symbol"] for row in symbols if row.get("would_enter")]
print(f"  crypto symbols={len(symbols)} held={held or 'none'} would_enter={would_enter or 'none'}")
PY
fi

echo ""
echo "Recovery complete. Check CRM dashboard and gate metrics."
DOW="$(date -u +%u)"
HOUR="$(date -u +%H)"
if [[ "$DOW" == "1" && "$HOUR" -ge 13 && "$HOUR" -le 18 ]]; then
  echo ""
  echo "Note: stocks burst-recovery runs within 60 min of US open (13:30 UTC)."
  echo "Platform-outage recovery extends to 270 min when open-ready symbols were queued (e.g. AAPL)."
  echo "Crypto + commodities held positions get immediate post-outage scans on startup (r461+)."
  echo "Check us-stocks-open-checklist for has_burst_scan / has_auto_entry."
fi
