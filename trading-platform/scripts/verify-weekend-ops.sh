#!/usr/bin/env bash
# Weekend operator checklist: deploy snapshot, dashboard bundle, CME preflight.
# Non-blocking on dashboard bundle lag; fails on CME critical checks.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"
CODE_REV="$(grep '^EXPECTED_PLATFORM_REVISION' "$ROOT/backend/app/engines/deploy_status.py" | sed -n 's/.*"\([^"]*\)".*/\1/p')"

echo "=== Weekend Ops Checklist — $(date -u '+%Y-%m-%d %H:%M UTC') ==="
echo "Backend: $BACKEND"
echo "Code target: $CODE_REV"
echo ""

SNAPSHOT=$(curl -fsS -m 15 "$BACKEND/api/deploy/snapshot" 2>/dev/null || echo "{}")
python3 << PY
import json, sys
snap = json.loads('''$SNAPSHOT''')
code_rev = "$CODE_REV"
if not snap:
    print("○ deploy snapshot unavailable")
    if code_rev:
        print(f"  code_target={code_rev}")
    sys.exit(0)
rev = snap.get("platform_revision")
exp = snap.get("expected_platform_revision")
print(f"Platform: {rev} → prod expected {exp} (current={snap.get('platform_revision_current')})")
if code_rev and exp and code_rev != exp:
    print(f"  deploy will advance prod expected {exp} → {code_rev}")
elif code_rev and rev and code_rev != rev:
    print(f"  production behind code: {rev} → {code_rev}")
if snap.get("github_verified") is False:
    print("WARN: GITHUB_TOKEN missing on Render — deploy staleness checks incomplete")
window = snap.get("cme_deploy_window") or {}
if window.get("message"):
    print(f"CME window: {window.get('message')}")
bundle = snap.get("expected_dashboard_bundle")
if bundle:
    print(f"Dashboard bundle target: {bundle}")
for key in ("dashboard_bundle_verify_command", "weekend_ops_verify_command"):
    cmd = snap.get(key)
    if cmd:
        print(f"  {cmd}")
PY

PROFIT=$(curl -fsS -m 20 "$BACKEND/api/profitability" 2>/dev/null || echo "{}")
GATE_NOTE=$(PROFIT_JSON="$PROFIT" python3 << 'PY'
import json, os
data = json.loads(os.environ.get("PROFIT_JSON") or "{}")
if not data:
    raise SystemExit(0)
paused = data.get("paused_bots") or []
day = data.get("verification_day")
remaining = data.get("verification_days_remaining")
wr = data.get("win_rate")
pf = data.get("profit_factor")
trades = data.get("total_trades")
pnl = data.get("total_pnl")
ready = data.get("live_trading_ready")
parts = []
if paused:
    parts.append(f"paused={paused}")
if day is not None:
    parts.append(f"verification day {day}/30 ({remaining}d left)")
if wr is not None and pf is not None:
    parts.append(f"WR={wr:.0%} PF={pf:.2f} trades={trades}")
if pnl is not None:
    parts.append(f"PnL=${pnl:+.2f}")
parts.append(f"live_ready={ready}")
print("Profitability gate: " + "; ".join(parts))
PY
)
if [[ -n "$GATE_NOTE" ]]; then
  echo "$GATE_NOTE"
fi

STATUS=$(curl -fsS -m 45 "$BACKEND/api/status" 2>/dev/null || echo "{}")
INTEG_NOTE=$(STATUS_JSON="$STATUS" python3 << 'PY'
import json, os
data = json.loads(os.environ.get("STATUS_JSON") or "{}")
if not data:
    raise SystemExit(0)
integrations = data.get("integrations") or {}
deploy = data.get("deploy") or {}
lines = []
if deploy.get("vercel_bundle_behind_expected"):
    exp = deploy.get("expected_dashboard_bundle") or "?"
    act = deploy.get("vercel_bundle_revision") or "?"
    lines.append(f"WARN: dashboard bundle behind expected ({act} vs {exp})")
mins = integrations.get("fomo_bearer_minutes_remaining")
polling = integrations.get("fomo_bearer_polling_active")
configured = integrations.get("fomo_bearer_configured")
if configured and not polling:
    if mins is not None and int(mins) < 0:
        lines.append(f"WARN: fomo bearer expired ({mins}min) — refresh via userscript or fomo-set-bearer.sh")
    else:
        lines.append("WARN: fomo bearer polling inactive — intel may be degraded")
hint = integrations.get("fomo_bearer_refresh_hint")
if hint and lines:
    lines.append(f"  {hint}")
for line in lines:
    print(line)
PY
)
if [[ -n "$INTEG_NOTE" ]]; then
  echo "$INTEG_NOTE"
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
    print(f"US stocks: bot paused — Monday auto-entry for {syms} blocked until profitability gate clears (open in {mins}min)")
elif open_ready:
    print(f"US stocks: open_ready={open_ready} (opens in {mins}min)")
PY
)
if [[ -n "$US_NOTE" ]]; then
  echo "$US_NOTE"
fi

CME_CHECKLIST=$(curl -fsS -m 30 "$BACKEND/api/gate/cme-reopen-checklist" 2>/dev/null || echo "{}")
CME_NOTE=$(python3 << PY
import json
data = json.loads('''$CME_CHECKLIST''')
if not data:
    raise SystemExit(0)
open_ready = (data.get("open_ready") or {}).get("symbols") or []
sticky = (data.get("open_ready") or {}).get("sticky_symbols") or []
near = (data.get("near_floor") or {}).get("symbols") or []
auto_entry = (data.get("open_ready") or {}).get("auto_entry_queued")
mins = data.get("minutes_until_open")
parts = [f"CME: open_ready={open_ready or 'none'}"]
if sticky:
    parts.append(f"sticky={sticky}")
if near:
    parts.append(f"near_floor={near}")
parts.append(f"auto_entry={auto_entry}")
if mins is not None:
    parts.append(f"open in {mins}min")
print("; ".join(parts))
PY
)
if [[ -n "$CME_NOTE" ]]; then
  echo "$CME_NOTE"
fi

echo ""
bash "$ROOT/scripts/verify-dashboard-bundle.sh" || true

echo ""
if bash "$ROOT/scripts/watch-deploy-window.sh" --once; then
  rc=0
else
  rc=$?
fi

echo ""
if ! bash "$ROOT/scripts/verify-cme-reopen.sh"; then
  echo ""
  echo "CME preflight failed — fix before deploy window or CME open."
  exit 1
fi

if [[ "$rc" -eq 10 ]]; then
  echo ""
  echo "*** Deploy window is ACTIVE — run:"
  echo "  bash trading-platform/scripts/verify-pre-deploy.sh"
  echo "  TRIGGER_DEPLOY=true bash trading-platform/scripts/sync-render-env.sh"
  echo "  bash trading-platform/scripts/verify-post-deploy.sh"
  exit 10
fi

echo ""
echo "After CME open (22:00 UTC):"
echo "  bash trading-platform/scripts/verify-cme-post-open.sh"
echo ""
echo "Monday before US open (13:30 UTC):"
echo "  bash trading-platform/scripts/verify-us-stocks-open.sh --watch 120"
echo "Monday after US open:"
echo "  bash trading-platform/scripts/verify-us-stocks-post-open.sh"
