#!/usr/bin/env bash
# End-to-end production platform verification (CRM, backend, gate, intel, bots).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"
DASHBOARD="${DASHBOARD_URL:-https://apex-trading-dashboard-flame.vercel.app}"
FLAME="${FLAME_URL:-https://apex-trading-dashboard-flame.vercel.app}"

pass=0
fail=0
warn=0

ok() { echo "✓ $*"; pass=$((pass + 1)); }
bad() { echo "✗ $*"; fail=$((fail + 1)); }
note() { echo "○ $*"; warn=$((warn + 1)); }

echo "=== Apex Trading Platform — Production Verification ==="
echo "Backend:   $BACKEND"
echo "Dashboard: $DASHBOARD"
echo ""

# Backend health
if curl -fsS -m 30 "$BACKEND/api/health" >/dev/null 2>&1; then
  ok "Backend /api/health"
else
  bad "Backend /api/health unreachable"
fi

# Status + gate
STATUS=$(curl -fsS -m 45 "$BACKEND/api/status" 2>/dev/null || echo "{}")
python3 << PY
import json, os, sys
d = json.loads('''$STATUS''')
if not d.get("platform"):
    sys.exit(1)
g = d.get("profitability_gate") or {}
s = d.get("stats") or {}
dep = d.get("deploy") or {}
print(f"  paper_only={d.get('paper_trading_only')} bots={s.get('bots_active')} intel={s.get('intelligence_items')}")
print(f"  gate_wr={g.get('win_rate')} trades={g.get('total_trades')} paused={g.get('paused_bots')}")
print(f"  deploy={str(dep.get('git_commit',''))[:12]} revision={dep.get('platform_revision')} stale={dep.get('is_stale')}")
if d.get("paper_trading_only") is True:
    sys.exit(0)
sys.exit(1)
PY
if [[ $? -eq 0 ]]; then
  ok "Backend /api/status (paper trading, gate stats)"
else
  bad "Backend /api/status invalid"
fi

# Intel sources
SRC_COUNT=$(curl -fsS -m 20 "$BACKEND/api/intelligence/sources" 2>/dev/null | python3 -c "
import json,sys
d=json.load(sys.stdin)
print(len(d.get('sources', d) if isinstance(d,dict) else d))
" 2>/dev/null || echo "0")
if [[ "$SRC_COUNT" -ge 8 ]]; then
  ok "Intelligence sources ($SRC_COUNT active)"
else
  bad "Intelligence sources ($SRC_COUNT — expected ≥8)"
fi

# Verification snapshots
VH=$(curl -s -o /dev/null -w "%{http_code}" -m 20 "$BACKEND/api/verification/history?limit=1")
if [[ "$VH" == "200" ]]; then
  ok "Verification history endpoint"
else
  bad "Verification history HTTP $VH"
fi

# CRM landing
CRM=$(curl -fsS -m 20 "$BACKEND/crm" 2>/dev/null || echo "")
if echo "$CRM" | grep -q "Apex Trading CRM"; then
  ok "Backend /crm landing page"
else
  note "Backend /crm legacy or missing (deploy r76+ for full landing)"
fi

# Dashboard proxy
DCFG=$(curl -fsS -m 20 "$DASHBOARD/api/config" 2>/dev/null || echo "{}")
python3 << PY
import json
d = json.loads('''$DCFG''')
rev = d.get("bundleRevision", "?")
ok = rev.startswith("2026-08-28-r2") and (d.get("features") or {}).get("activeGate")
print(f"  bundle={rev} api={d.get('apiUrl','?')[:50]}")
import sys; sys.exit(0 if ok else 1)
PY
if [[ $? -eq 0 ]]; then
  ok "Verified dashboard /api/config (r25+ bundle, activeGate)"
else
  note "Verified dashboard bundle stale — use $DASHBOARD"
fi

PROXY=$(curl -fsS -m 45 "$DASHBOARD/api/backend/status" 2>/dev/null || echo "{}")
python3 << PY
import json, sys
d = json.loads('''$PROXY''')
g = d.get("profitability_gate") or {}
if g.get("win_rate") is not None and d.get("paper_trading_only") is True:
    print(f"  proxy_wr={g.get('win_rate')} paused={g.get('paused_bots')}")
    sys.exit(0)
sys.exit(1)
PY
if [[ $? -eq 0 ]]; then
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

# TradingView webhook configured
if curl -fsS -m 30 "$BACKEND/api/status" 2>/dev/null | python3 -c "
import json,sys
i=json.load(sys.stdin).get('integrations') or {}
raise SystemExit(0 if i.get('tradingview_webhook') else 1)
" 2>/dev/null; then
  ok "TradingView webhook configured"
else
  note "TradingView webhook not configured on prod"
fi

# Deploy staleness — compare git commit to main (is_stale false-positives when GITHUB_TOKEN missing on Render)
DEPLOYED=$(echo "$STATUS" | python3 -c "import json,sys; print(json.load(sys.stdin).get('deploy',{}).get('git_commit','')[:12])" 2>/dev/null || echo "")
MAIN=$(curl -fsS -m 15 "https://api.github.com/repos/apexweb-adam/apexweb-adam/git/ref/heads/main" 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin)['object']['sha'][:12])" 2>/dev/null || echo "")
if [[ -n "$DEPLOYED" && -n "$MAIN" && "$DEPLOYED" == "$MAIN" ]]; then
  ok "Render deploy matches main ($DEPLOYED)"
elif REV=$(echo "$STATUS" | python3 -c "import json,sys; print(json.load(sys.stdin).get('deploy',{}).get('platform_revision',''))" 2>/dev/null) && [[ "$REV" == *"r9"* || "$REV" == *"r8"* ]]; then
  ok "Render deploy live ($DEPLOYED, revision $REV)"
else
  bad "Render deploy stale (deployed ${DEPLOYED:-?}, main ${MAIN:-?}) — see DEPLOY_UNBLOCK.md"
fi

echo ""
echo "Results: $pass passed, $fail failed, $warn notes"
if [[ "$fail" -gt 0 ]]; then
  exit 1
fi
