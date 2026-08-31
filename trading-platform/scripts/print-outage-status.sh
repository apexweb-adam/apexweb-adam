#!/usr/bin/env bash
# One-shot billing outage / recovery status for ops.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/fetch_json.sh
source "$ROOT/scripts/lib/fetch_json.sh"

BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"
CODE_REV="$(grep '^EXPECTED_PLATFORM_REVISION' "$ROOT/backend/app/engines/deploy_status.py" | sed -n 's/.*"\([^"]*\)".*/\1/p')"
DASH_REV="$(grep '^EXPECTED_DASHBOARD_BUNDLE' "$ROOT/backend/app/engines/deploy_status.py" | sed -n 's/.*"\([^"]*\)".*/\1/p')"

echo "=== Platform Outage Status — $(date -u '+%Y-%m-%d %H:%M UTC') ==="
echo "Backend: $BACKEND"
echo "Target revision: ${CODE_REV:-?} · dashboard bundle: ${DASH_REV:-?}"
echo "Render dashboard: ${RENDER_DASHBOARD_URL}"
echo ""

if check_backend_suspension "$BACKEND" 2>/dev/null; then
  echo "Backend: ONLINE"
  wake_backend "$BACKEND" 2
  RUNNING="$(production_platform_revision "$BACKEND")"
  echo "Production revision: ${RUNNING:-unknown}"
  if [[ -n "$CODE_REV" ]] && production_revision_behind "$BACKEND" "$CODE_REV"; then
    echo "Deploy: BEHIND — run bash trading-platform/scripts/recover-render-billing.sh"
  else
    echo "Deploy: current (or settling)"
  fi
  SNAPSHOT=$(fetch_json "$BACKEND/api/deploy/snapshot" 60 2)
  SNAPSHOT="$SNAPSHOT" python3 << 'PY'
import json, os
snap = json.loads(os.environ.get("SNAPSHOT") or "{}")
gate = snap.get("gate") or {}
print(f"Gate: trades={gate.get('total_trades')} WR={gate.get('win_rate')} ready={gate.get('live_trading_ready')}")
PY
  CHECKLIST=$(fetch_json "$BACKEND/api/gate/us-stocks-open-checklist" 90 2)
  STATUS=$(fetch_json "$BACKEND/api/status" 60 2)
  CHECKLIST="$CHECKLIST" STATUS="$STATUS" python3 << 'PY'
import json, os
d = json.loads(os.environ.get("CHECKLIST") or "{}")
status = json.loads(os.environ.get("STATUS") or "{}")
outage = d.get("platform_outage_recovery") or {}
orx = d.get("open_ready") or {}
events = d.get("session_open_events") or {}
print(f"US stocks: phase={d.get('phase')} open_ready={orx.get('symbols')} burst={events.get('has_burst_scan')} auto_entry={events.get('has_auto_entry')}")
if outage.get("window_active"):
    print(f"  platform_outage_recovery: window_active grace_remaining_min={outage.get('grace_minutes_remaining')}")
if outage.get("logged"):
    print("  platform_outage_recovery: logged")
outage_events = status.get("platform_outage_events") or []
if outage_events:
    print(f"Platform outage events logged: {len(outage_events)} (newest gap {outage_events[0].get('gap_minutes')}m)")
PY
  exit 0
fi

echo "Backend: BILLING-SUSPENDED (503)"
echo ""
echo "Recovery steps:"
echo "  1. Fix billing + resume service in Render dashboard"
echo "  2. bash trading-platform/scripts/recover-render-billing.sh"
echo ""

python3 << 'PY'
from datetime import datetime, timezone

now = datetime.now(timezone.utc)
dow = now.isoweekday()  # 1=Monday
print(f"Day: weekday={dow} (1=Mon)")

if dow == 1:
    open_at = now.replace(hour=13, minute=30, second=0, microsecond=0)
    standard_grace_end = open_at.timestamp() + 60 * 60
    extended_grace_end = open_at.timestamp() + 270 * 60
    now_ts = now.timestamp()
    if now_ts < open_at.timestamp():
        mins_until = int((open_at.timestamp() - now_ts) // 60)
        print(f"US cash open in ~{mins_until} min (13:30 UTC)")
    else:
        since_open = int((now_ts - open_at.timestamp()) // 60)
        ext_left = max(0, int((extended_grace_end - now_ts) // 60))
        print(f"US cash open was {since_open} min ago")
        print(f"Standard burst grace (60 min): {'EXPIRED' if since_open > 60 else f'{60 - since_open} min left'}")
        print(f"Platform outage grace (270 min): {'EXPIRED' if ext_left == 0 else f'{ext_left} min left (~{ext_left // 60}h {ext_left % 60}m)'}")
        if ext_left > 0:
            print("Queued AAPL catch-up still possible if prep state preserved and r453 deploys on resume")
        else:
            print("Platform outage grace expired — only normal scan intervals after resume")
else:
    print("Not Monday — US stocks outage grace window N/A today")
PY

echo ""
echo "Automated recovery: GitHub workflow render-billing-recovery (every 15 min when online)"
