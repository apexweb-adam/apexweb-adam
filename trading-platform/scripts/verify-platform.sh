#!/usr/bin/env bash
# End-to-end production platform verification (CRM, backend, gate, intel, bots).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/fetch_json.sh
source "$ROOT/scripts/lib/fetch_json.sh"
BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"
DASHBOARD="${DASHBOARD_URL:-https://apex-trading-dashboard-flame.vercel.app}"
FLAME="${FLAME_URL:-https://apex-trading-dashboard-flame.vercel.app}"
GIT_MAIN="https://apex-trading-dashboard-git-main-apexweb-adams-projects.vercel.app"
EXPECTED_BUNDLE="${EXPECTED_DASHBOARD_BUNDLE:-$(grep '^EXPECTED_DASHBOARD_BUNDLE' "$ROOT/backend/app/engines/deploy_status.py" | sed -n 's/.*"\([^"]*\)".*/\1/p')}"
CODE_REV="$(grep '^EXPECTED_PLATFORM_REVISION' "$ROOT/backend/app/engines/deploy_status.py" | sed -n 's/.*"\([^"]*\)".*/\1/p')"

pass=0
fail=0
warn=0

ok() { echo "✓ $*"; pass=$((pass + 1)); }
bad() { echo "✗ $*"; fail=$((fail + 1)); }
note() { echo "○ $*"; warn=$((warn + 1)); }

echo "=== Apex Trading Platform — Production Verification ==="
echo "Backend:   $BACKEND"
echo "Dashboard: $DASHBOARD"
echo "Code target: $CODE_REV · bundle $EXPECTED_BUNDLE"
echo ""

if ! check_backend_suspension "$BACKEND"; then
  bad "Render backend billing-suspended — all platform checks blocked"
  echo ""
  bash "$ROOT/scripts/print-outage-status.sh" 2>/dev/null | tail -n +8 || true
  echo ""
  echo "=== Summary: $pass passed, $fail failed, $warn warnings ==="
  exit 2
fi

bash "$ROOT/scripts/ops-gate-summary.sh" || true
echo ""

# Backend health
if curl -fsS -m 30 "$BACKEND/api/health" >/dev/null 2>&1; then
  ok "Backend /api/health"
else
  bad "Backend /api/health unreachable"
fi

# Status + gate
STATUS=$(fetch_json "$BACKEND/api/status" 60 2)
if echo "$STATUS" | python3 -c "
import json, sys
d = json.load(sys.stdin)
if not d.get('platform'):
    sys.exit(1)
g = d.get('profitability_gate') or {}
s = d.get('stats') or {}
dep = d.get('deploy') or {}
print(f\"  paper_only={d.get('paper_trading_only')} bots={s.get('bots_active')} intel={s.get('intelligence_items')}\")
print(f\"  gate_wr={g.get('win_rate')} trades={g.get('total_trades')} paused={g.get('paused_bots')}\")
print(f\"  deploy={str(dep.get('git_commit',''))[:12]} revision={dep.get('platform_revision')} stale={dep.get('is_stale')}\")
bs = (d.get('bot_sessions') or {}).get('stocks_futures') or {}
if bs.get('minutes_until_open') is not None and bs['minutes_until_open'] <= 90:
    print(f\"  stocks_prep_window=True open_in={bs.get('minutes_until_open')}min mode={bs.get('mode')}\")
if d.get('paper_trading_only') is True:
    sys.exit(0)
sys.exit(1)
"; then
  ok "Backend /api/status (paper trading, gate stats)"
else
  bad "Backend /api/status invalid or unavailable"
fi

# Platform outage recovery (billing suspension gaps)
if echo "$STATUS" | python3 -c "
import json, sys
d = json.load(sys.stdin)
events = d.get('platform_outage_events') or []
if events:
    newest = events[0]
    gap = newest.get('gap_minutes')
    us = newest.get('us_open_ready_symbols') or []
    print(f'  outage_events={len(events)} newest_gap_min={gap} us_queued={us or \"none\"}')
us_checklist = (d.get('session_open_checklists') or {}).get('us_stocks') or {}
outage = us_checklist.get('platform_outage_recovery') or {}
if outage.get('window_active'):
    print(f'  outage_recovery_window=true grace_min={outage.get(\"grace_minutes_remaining\")}')
elif outage.get('logged'):
    print('  outage_recovery_logged=true window=expired')
sys.exit(0)
"; then
  note "Platform outage state (see above if billing gap logged)"
else
  note "Platform outage state unavailable"
fi

# Database persistence (Supabase required on Render)
if echo "$STATUS" | python3 -c "
import json, sys
d = json.load(sys.stdin)
db = d.get('database') or {}
if db.get('persistent') is True:
    print(f\"  engine={db.get('engine')} persistent=True\")
    sys.exit(0)
on_render = 'onrender.com' in sys.argv[1]
if on_render:
    print('  engine=sqlite ephemeral — gate data resets each deploy; set DATABASE_URL on Render')
    sys.exit(1)
print(f\"  engine={db.get('engine')} (local dev OK)\")
sys.exit(0)
" "$BACKEND"; then
  ok "Database persistence"
else
  bad "Database not persistent on production (set Supabase DATABASE_URL)"
fi

# Intel sources
INTEL_RAW=$(fetch_json "$BACKEND/api/intelligence/sources" 30 2)
SRC_COUNT=$(echo "$INTEL_RAW" | python3 -c "
import json,sys
raw=json.load(sys.stdin)
sources=raw.get('sources', raw) if isinstance(raw, dict) else raw
print(len(sources) if isinstance(sources, list) else 0)
" 2>/dev/null || echo "0")
if [[ "$SRC_COUNT" -ge 8 ]]; then
  ok "Intelligence sources ($SRC_COUNT active)"
else
  bad "Intelligence sources ($SRC_COUNT — expected ≥8)"
fi

echo "$INTEL_RAW" | python3 -c "
import json,sys
raw=json.load(sys.stdin)
sources=raw.get('sources', raw) if isinstance(raw, dict) else raw
if not isinstance(sources, list):
    sys.exit(0)
by={s.get('source'): s for s in sources if isinstance(s, dict)}
x=by.get('x') or {}
tv=by.get('tradingview') or {}
if x.get('collection_mode'):
    print(f'  x_intel={x.get(\"collection_mode\")} status={x.get(\"status\")}')
if tv.get('scoring_excludes_synthetic'):
    print(
        f'  tradingview webhook_24h={tv.get(\"webhook_items_24h\")} '
        f'synthetic_24h={tv.get(\"synthetic_items_24h\")}'
    )
" 2>/dev/null || true

# Verification snapshots
VH=$(curl -s -o /dev/null -w "%{http_code}" -m 20 "$BACKEND/api/verification/history?limit=1")
if [[ "$VH" == "200" ]]; then
  ok "Verification history endpoint"
else
  bad "Verification history HTTP $VH"
fi

# Per-bot graduation gate
PER_BOT=$(fetch_json "$BACKEND/api/gate/per-bot" 30 2)
if echo "$PER_BOT" | python3 -c "
import json, sys
d = json.load(sys.stdin)
bots = d.get('bots') or {}
if len(bots) < 4:
    sys.exit(1)
ready = [b for b, s in bots.items() if s.get('graduation_ready')]
paused = [b for b, s in bots.items() if s.get('paused')]
print(f\"  bots={len(bots)} paused={paused} graduation_ready={ready or 'none'}\")
"; then
  ok "Per-bot graduation gate (/api/gate/per-bot)"
else
  bad "Per-bot gate endpoint missing or incomplete"
fi

# Scan preview diagnostics (paused bot entry blockers)
SCAN_PREVIEW=$(fetch_json "$BACKEND/api/bots/commodities/scan-preview" 45 2)
if echo "$SCAN_PREVIEW" | python3 -c "
import json, sys
d = json.load(sys.stdin)
if d.get('bot_type') != 'commodities':
    sys.exit(1)
if 'symbols' not in d or not isinstance(d['symbols'], list):
    sys.exit(1)
print(f\"  shadow={d.get('shadow_mode')} nudge={d.get('graduation_nudge')} symbols={len(d['symbols'])}\")
"; then
  ok "Commodities scan-preview (/api/bots/commodities/scan-preview)"
else
  bad "Scan-preview endpoint missing or invalid (deploy r95+)"
fi

# CME reopen prep (weekend / pre-open)
PREP=$(fetch_json "$BACKEND/api/gate/prep-status" 45 2)
if echo "$PREP" | python3 -c "
import json, sys
prep = json.load(sys.stdin)
comm = prep.get('commodities') or {}
cme = (prep.get('next_session_events') or {}).get('cme_reopen') or {}
mins = comm.get('minutes_until_open') or cme.get('minutes_until_open')
phase = comm.get('prep_phase') or cme.get('prep_phase')
open_ready = comm.get('open_ready_symbols') or cme.get('open_ready_symbols') or []
auto_entry = comm.get('auto_entry_queued') or cme.get('auto_entry_queued')
if mins is None:
    sys.exit(1)
print(f\"  cme_phase={phase} open_in={mins}min open_ready={open_ready} auto_entry={auto_entry}\")
"; then
  ok "CME prep-status (phase, open-ready queue)"
else
  note "CME prep-status unavailable (run verify-cme-reopen.sh)"
fi

CME_CHECK=$(fetch_json "$BACKEND/api/gate/cme-reopen-checklist" 60 2)
if [[ -n "$CME_CHECK" && "$CME_CHECK" != "{}" ]]; then
  if echo "$CME_CHECK" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(f\"  cme_checklist_ready={d.get('ready')} phase={d.get('phase')}\")
"; then
    ok "CME reopen checklist API"
  else
    note "CME checklist API returned invalid JSON"
  fi
else
  note "CME checklist API unavailable until r344+ deploy"
fi

US_CHECK=$(curl -fsS -m 45 "$BACKEND/api/gate/us-stocks-open-checklist" 2>/dev/null || echo "")
if [[ -n "$US_CHECK" && "$US_CHECK" != "{}" ]]; then
  ok "US stocks open checklist API"
else
  note "US stocks checklist API unavailable until r345+ deploy"
fi

# CRM landing
CRM=$(curl -fsS -m 120 "$BACKEND/crm" 2>/dev/null || echo "")
if echo "$CRM" | grep -q "Apex Trading CRM"; then
  ok "Backend /crm landing page"
  if echo "$CRM" | grep -q "Graduation"; then
    ok "CRM per-bot graduation table"
  else
    note "CRM missing per-bot graduation table (deploy r76+)"
  fi
else
  note "Backend /crm legacy or missing (deploy r76+ for full landing)"
fi

# Pick best live CRM — git-main r27 when -flame bundle is stale
FLAME_CFG=$(fetch_json "$FLAME/api/config" 30 2)
DASHBOARD="$FLAME"
export FLAME_CFG_JSON="$FLAME_CFG"
export EXPECTED_BUNDLE GIT_MAIN="$GIT_MAIN" FLAME_URL="$FLAME"
if python3 << 'PY'
import json, os

flame_cfg = json.loads(os.environ.get("FLAME_CFG_JSON") or "{}")
rev = flame_cfg.get("bundleRevision", "")
expected = os.environ.get("EXPECTED_BUNDLE", "")
git_main = os.environ.get("GIT_MAIN", "")
flame_url = os.environ.get("FLAME_URL", "")
if rev != expected or not (flame_cfg.get("features") or {}).get("activeGate"):
    print(f"  flame bundle={rev!r} — using git-main verified preview")
    with open("/tmp/apex-dashboard-url.txt", "w", encoding="utf-8") as out:
        out.write(git_main)
else:
    with open("/tmp/apex-dashboard-url.txt", "w", encoding="utf-8") as out:
        out.write(flame_url)
PY
then
  :
else
  note "Dashboard config parse failed — using flame URL"
fi
if [[ -f /tmp/apex-dashboard-url.txt ]]; then
  DASHBOARD=$(cat /tmp/apex-dashboard-url.txt)
fi
echo "CRM URL:   $DASHBOARD"
echo ""

# Dashboard bundle (shared verifier)
if bash "$ROOT/scripts/verify-dashboard-bundle.sh"; then
  ok "Dashboard bundle ($EXPECTED_BUNDLE)"
else
  note "Dashboard bundle behind — non-blocking for backend deploy"
fi

# Dashboard proxy config (legacy check for activeGate on selected URL)
DCFG=$(fetch_json "$DASHBOARD/api/config" 30 2)
echo "$DCFG" | python3 -c "
import json, sys
d = json.load(sys.stdin)
rev = d.get('bundleRevision', '?')
print(f\"  selected_dashboard bundle={rev} api={str(d.get('apiUrl','?'))[:50]}\")
" 2>/dev/null || note "Dashboard /api/config unavailable"

# Native active-gate on verified preview (not available on stale -flame alone)
if [[ "$DASHBOARD" == *"git-main"* ]]; then
  NAT=$(curl -s -o /dev/null -w "%{http_code}" -m 20 "$DASHBOARD/api/active-gate" 2>/dev/null || echo "000")
  if [[ "$NAT" == "200" ]]; then
    ok "Dashboard native /api/active-gate (git-main r27)"
  else
    note "Native active-gate HTTP $NAT on $DASHBOARD"
  fi
fi

PROXY=$(fetch_json "$DASHBOARD/api/backend/status" 60 2)
if echo "$PROXY" | python3 -c "
import json, sys
d = json.load(sys.stdin)
g = d.get('profitability_gate') or {}
if g.get('win_rate') is not None and d.get('paper_trading_only') is True:
    print(f\"  proxy_wr={g.get('win_rate')} paused={g.get('paused_bots')}\")
    sys.exit(0)
sys.exit(1)
"; then
  ok "Dashboard proxy → backend status (real-time CRM)"
else
  bad "Dashboard proxy failed"
fi

# Active gate via proxy
AG=$(curl -s -o /dev/null -w "%{http_code}" -m 20 "$DASHBOARD/api/backend/active-gate" 2>/dev/null || echo "000")
if [[ "$AG" == "200" ]]; then
  ok "Dashboard /api/backend/active-gate"
else
  note "Active gate proxy HTTP $AG"
fi

# TradingView webhook configured (reuse STATUS from earlier — /api/status is slow on cold start)
if echo "$STATUS" | python3 -c "
import json,sys
i=json.load(sys.stdin).get('integrations') or {}
raise SystemExit(0 if i.get('tradingview_webhook') else 1)
" 2>/dev/null; then
  ok "TradingView webhook configured"
else
  note "TradingView webhook not configured on prod"
fi

# Learning loop + content study (post-mortems, strategy adaptation)
if echo "$STATUS" | python3 -c "
import json, sys
learning = json.load(sys.stdin).get('learning') or {}
analyses = learning.get('trade_analyses') or 0
reviews = learning.get('daily_reviews') or 0
applied = learning.get('insights_applied') or 0
pending = learning.get('insights_pending') or 0
if analyses > 0 and reviews > 0:
    intel_count = learning.get('intel_pattern_count') or 0
    print(
        f'  learning analyses={analyses} reviews={reviews} '
        f'insights_applied={applied} pending={pending} intel_pattern_alerts={intel_count}'
    )
    sys.exit(0)
sys.exit(1)
"; then
  ok "Learning loop active (trade analyses + daily reviews)"
  if echo "$STATUS" | python3 -c "
import json, sys
learning = json.load(sys.stdin).get('learning') or {}
alerts = learning.get('intel_pattern_alerts') or []
if alerts:
    print('  intel_pattern_alerts:')
    for alert in alerts[:5]:
        print(f'    - {alert}')
    sys.exit(0)
sys.exit(1)
"; then
    note "Intel-driven loss patterns detected — confirmation gates may tighten"
  fi
  if echo "$STATUS" | python3 -c "
import json, sys
applied = (json.load(sys.stdin).get('learning') or {}).get('insights_applied') or 0
sys.exit(0 if applied > 0 else 1)
"; then
    ok "Content study insights applied to strategy"
  else
    note "Content study insights not applied yet — hourly job or POST /api/admin/run-content-study"
  fi
  if echo "$STATUS" | python3 -c "
import json, sys
recent = (json.load(sys.stdin).get('content_study') or {}).get('recent') or []
labeled = [row for row in recent if row.get('source_label')]
if labeled:
    print('  content_study_recent:')
    for row in labeled[:5]:
        applied = 'applied' if row.get('applied') else 'pending'
        print(f\"    - [{row.get('source_label')}] {row.get('title', '')[:56]} ({applied})\")
    sys.exit(0)
sys.exit(1)
"; then
    note "Content study highlights (labeled sources above)"
  fi
else
  note "Learning loop sparse — confirm trades and daily review scheduler"
fi

# Deploy credentials (snapshot — r370+)
SNAPSHOT=$(fetch_json "$BACKEND/api/deploy/snapshot" 45 2)
CRED_OUT=$(echo "$SNAPSHOT" | python3 -c "
import json, sys
d = json.load(sys.stdin)
ready = d.get('deploy_credentials_ready')
warnings = d.get('deploy_credentials_warnings') or []
nudges = d.get('deploy_credentials_nudges') or []
if ready is True:
    if nudges:
        for item in nudges:
            print(f'  nudge: {item}')
    else:
        print('  no blocking issues')
    sys.exit(0)
if warnings:
    for item in warnings:
        print(f'  - {item}')
    sys.exit(2)
if d.get('github_token_configured') is False:
    print('  nudge: GITHUB_TOKEN missing (pre-r390 snapshot)')
    sys.exit(3)
sys.exit(1)
" 2>&1) || CRED_RC=$?
CRED_RC=${CRED_RC:-0}
if [[ "$CRED_RC" -eq 0 ]]; then
  echo "$CRED_OUT"
  ok "Deploy credentials ready"
elif [[ "$CRED_RC" -eq 2 ]]; then
  echo "$CRED_OUT"
  note "Deploy credentials blocked — run check-deploy-credentials.sh before deploy"
elif [[ "$CRED_RC" -eq 3 ]]; then
  echo "$CRED_OUT"
  ok "Deploy credentials ready (GITHUB_TOKEN nudge on pre-r390 prod)"
else
  note "Deploy credentials unknown (snapshot pre-r370)"
fi

# Deploy revision — compare code target to production
REV=$(echo "$STATUS" | python3 -c "import json,sys; print(json.load(sys.stdin).get('deploy',{}).get('platform_revision',''))" 2>/dev/null || echo "")
EXP=$(echo "$STATUS" | python3 -c "import json,sys; print(json.load(sys.stdin).get('deploy',{}).get('expected_platform_revision',''))" 2>/dev/null || echo "")
if [[ -n "$REV" && "$REV" == "$CODE_REV" ]]; then
  ok "Production revision current ($REV)"
elif [[ -n "$REV" ]]; then
  note "Production revision behind code ($REV → $CODE_REV) — deploy tonight"
else
  note "Production revision unknown"
fi

DEPLOYED=$(echo "$STATUS" | python3 -c "import json,sys; print(json.load(sys.stdin).get('deploy',{}).get('git_commit','')[:12])" 2>/dev/null || echo "")
MAIN=$(curl -fsS -m 15 "https://api.github.com/repos/apexweb-adam/apexweb-adam/git/ref/heads/main" 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin)['object']['sha'][:12])" 2>/dev/null || echo "")
if [[ -n "$DEPLOYED" && -n "$MAIN" && "$DEPLOYED" == "$MAIN" ]]; then
  ok "Render git commit matches main ($DEPLOYED)"
elif [[ -n "$DEPLOYED" ]]; then
  note "Render git commit ${DEPLOYED} vs main ${MAIN:-?}"
fi

echo ""
echo "--- CRM learning loop ---"
bash "$ROOT/scripts/verify-crm-learning.sh" || true

echo ""
echo "Results: $pass passed, $fail failed, $warn notes"
if [[ "$fail" -gt 0 ]]; then
  exit 1
fi
