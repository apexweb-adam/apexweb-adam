#!/usr/bin/env bash
# Pre-deploy gate for session-open bundle (r337+). Run before TRIGGER_DEPLOY.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"
EXPECTED_REVISION="${EXPECTED_PLATFORM_REVISION:-$(grep '^EXPECTED_PLATFORM_REVISION' "$ROOT/backend/app/engines/deploy_status.py" | sed -n 's/.*"\([^"]*\)".*/\1/p')}"
MIN_HOURS_BEFORE_CME="${MIN_HOURS_BEFORE_CME:-4}"
MAX_HOURS_BEFORE_CME="${MAX_HOURS_BEFORE_CME:-6}"

pass=0
fail=0
warn=0

ok() { echo "✓ $*"; pass=$((pass + 1)); }
bad() { echo "✗ $*"; fail=$((fail + 1)); }
note() { echo "○ $*"; warn=$((warn + 1)); }

echo "=== Session-Open Deploy Preflight — $(date -u '+%Y-%m-%d %H:%M UTC') ==="
echo "Expected revision: $EXPECTED_REVISION"
echo ""

bash "$ROOT/scripts/ops-gate-summary.sh" || true
echo ""

PREP=$(curl -fsS -m 45 "$BACKEND/api/gate/prep-status" 2>/dev/null || echo "{}")
CME_MINS=$(python3 << PY
import json
prep = json.loads('''$PREP''')
comm = prep.get("commodities") or {}
cme = (prep.get("next_session_events") or {}).get("cme_reopen") or {}
mins = comm.get("minutes_until_open") or cme.get("minutes_until_open")
print(mins if mins is not None else "")
PY
)

if [[ -n "$CME_MINS" ]]; then
  MIN_MINS=$((MIN_HOURS_BEFORE_CME * 60))
  MAX_MINS=$((MAX_HOURS_BEFORE_CME * 60))
  if [[ "$CME_MINS" -gt "$MAX_MINS" ]]; then
    note "CME open in ${CME_MINS}min — deploy window is ${MIN_HOURS_BEFORE_CME}-${MAX_HOURS_BEFORE_CME}h before open"
    note "Wait until ~$((CME_MINS - MAX_MINS))min from now for ideal timing"
  elif [[ "$CME_MINS" -lt "$MIN_MINS" ]]; then
    bad "CME open in ${CME_MINS}min — too close to open for safe deploy rotation"
  else
    ok "Deploy timing within ${MIN_HOURS_BEFORE_CME}-${MAX_HOURS_BEFORE_CME}h window (${CME_MINS}min to CME)"
  fi
  python3 << PY
import json
from datetime import datetime, timedelta
prep = json.loads('''$PREP''')
comm = prep.get("commodities") or {}
cme = (prep.get("next_session_events") or {}).get("cme_reopen") or {}
mins = comm.get("minutes_until_open") or cme.get("minutes_until_open")
if mins is None:
    raise SystemExit(0)
mins = int(mins)
start = int("$MAX_HOURS_BEFORE_CME") * 60
end = int("$MIN_HOURS_BEFORE_CME") * 60
now = datetime.utcnow()
opens = now + timedelta(minutes=max(0, mins - start))
closes = now + timedelta(minutes=max(0, mins - end))
print(f"  deploy_window_opens_utc={opens.strftime('%Y-%m-%d %H:%M')}")
print(f"  deploy_window_closes_utc={closes.strftime('%Y-%m-%d %H:%M')}")
PY
fi

CODE_REV=$(grep '^EXPECTED_PLATFORM_REVISION' "$ROOT/backend/app/engines/deploy_status.py" | sed -n 's/.*"\([^"]*\)".*/\1/p')
if [[ "$CODE_REV" == "$EXPECTED_REVISION" ]]; then
  ok "Code revision matches ($CODE_REV)"
else
  bad "Code revision mismatch: file=$CODE_REV expected=$EXPECTED_REVISION"
fi

if bash "$ROOT/scripts/verify-cme-reopen.sh"; then
  ok "CME reopen preflight"
else
  bad "CME reopen preflight failed"
fi

if bash "$ROOT/scripts/verify-dashboard-bundle.sh"; then
  :
else
  note "Dashboard bundle check failed (non-blocking)"
fi

US_CHECKLIST=$(curl -fsS -m 30 "$BACKEND/api/gate/us-stocks-open-checklist" 2>/dev/null || echo "{}")
US_NOTE=$(python3 << PY
import json
data = json.loads('''$US_CHECKLIST''')
if not data:
    raise SystemExit(0)
checks = {c.get("id"): c for c in data.get("checks") or []}
stocks = checks.get("stocks_active") or {}
open_ready = (data.get("open_ready") or {}).get("symbols") or []
mins = data.get("minutes_until_open")
if stocks.get("status") == "fail":
    syms = ", ".join(open_ready) if open_ready else "none"
    print(f"Stocks bot paused — Monday auto-entry for {syms} blocked until gate clears (US open in {mins}min)")
elif open_ready:
    print(f"US stocks open-ready queued: {', '.join(open_ready)} (opens in {mins}min)")
PY
)
if [[ -n "$US_NOTE" ]]; then
  if echo "$US_NOTE" | grep -q "paused"; then
    note "$US_NOTE"
  else
    ok "$US_NOTE"
  fi
fi

PROD_REV=$(curl -fsS -m 15 "$BACKEND/api/deploy/snapshot" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('platform_revision') or '')" 2>/dev/null || echo "")
if [[ -z "$PROD_REV" ]]; then
  PROD_REV=$(curl -fsS -m 45 "$BACKEND/api/status" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print((d.get('deploy') or {}).get('platform_revision') or '?')" 2>/dev/null || echo "?")
fi
echo "  production_revision=$PROD_REV code_revision=$CODE_REV"
if [[ "$PROD_REV" == "$CODE_REV" ]]; then
  note "Production already on target revision — deploy may be unnecessary"
  if bash "$ROOT/scripts/verify-post-deploy.sh"; then
    ok "Post-deploy session-open contract verified on production"
  else
    bad "Production on target revision but session-open contract failed"
  fi
else
  ok "Production behind code ($PROD_REV → $CODE_REV)"
  note "Post-deploy contract (cme_deploy_window, sticky_symbols) will verify after deploy"
fi

CRM_TIME=$(curl -sS -o /dev/null -m 120 -w "%{time_total}" "$BACKEND/crm" 2>/dev/null || echo "")
if [[ -n "$CRM_TIME" ]]; then
  CRM_SEC=$(python3 -c "print(f'{float('$CRM_TIME'):.1f}')")
  echo "$CRM_SEC" > "$ROOT/.crm-load-baseline"
  note "CRM landing baseline ${CRM_SEC}s saved (target <30s after r367-r369 deploy)"
fi

echo ""
echo "Results: $pass passed, $fail failed, $warn notes"
if [[ "$fail" -gt 0 ]]; then
  exit 1
fi

echo ""
echo "Deploy when ready:"
echo "  bash trading-platform/scripts/run-deploy-window.sh"
echo "  # or:"
echo "  TRIGGER_DEPLOY=true bash trading-platform/scripts/sync-render-env.sh"
echo "  bash trading-platform/scripts/wait-for-render-deploy.sh --verify"
echo ""
echo "Monday US open (if stocks still paused, auto-entry stays blocked by design):"
echo "  bash trading-platform/scripts/verify-us-stocks-open.sh --watch 120"
echo ""
echo "Watch deploy window (opens ~4-6h before CME):"
echo "  bash trading-platform/scripts/watch-deploy-window.sh --once"
