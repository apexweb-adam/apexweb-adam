#!/usr/bin/env bash
# Verify platform is ready for permanent Render + Supabase production deploy
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== Apex Trading Platform — Deploy Readiness ==="
echo ""

FAIL=0

check() {
  local name="$1"
  local ok="$2"
  if [[ "$ok" == "1" ]]; then
    echo "✓ $name"
  else
    echo "✗ $name"
    FAIL=1
  fi
}

# render.yaml — no disk (free tier)
if rg -q '^\s*disk:' render.yaml 2>/dev/null || rg -q '^\s*disk:' trading-platform/render.yaml 2>/dev/null; then
  check "render.yaml has no disk block" 0
else
  check "render.yaml has no disk block (Render free tier)" 1
fi

check "render.yaml exists at repo root" "$([[ -f render.yaml ]] && echo 1 || echo 0)"
check "Supabase setup doc exists" "$([[ -f SUPABASE_SETUP.md ]] && echo 1 || echo 0)"
check "Backend Dockerfile exists" "$([[ -f backend/Dockerfile ]] && echo 1 || echo 0)"

# Local backend health (optional)
if curl -sf http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
  STATUS=$(curl -sf http://127.0.0.1:8000/api/status)
  INTEL=$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('intelligence',{}).get('active_sources',0))")
  TOTAL=$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('intelligence',{}).get('total_sources',0))")
  PERSIST=$(echo "$STATUS" | python3 -c "import sys,json; print(1 if json.load(sys.stdin).get('database',{}).get('persistent') else 0)")
  check "Local backend /api/health" 1
  check "Intelligence sources $INTEL/$TOTAL" "$([[ "$INTEL" == "$TOTAL" && "$TOTAL" -gt 0 ]] && echo 1 || echo 0)"
  BOTS=$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('stats',{}).get('bots_active',0))")
  check "4 trading bots active" "$([[ "$BOTS" == "4" ]] && echo 1 || echo 0)"
  REVIEWS=$(curl -sf http://127.0.0.1:8000/api/reviews?limit=1 2>/dev/null | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo 0)
  check "Daily review / learning loop" "$([[ "$REVIEWS" -gt 0 ]] && echo 1 || echo 0)"
  if [[ "$PERSIST" == "1" ]]; then
    check "Database persistent (Supabase)" 1
  else
    echo "○ Database is SQLite (local dev OK — set Supabase DATABASE_URL on Render)"
  fi
else
  echo "○ Local backend not running (skip runtime checks)"
fi

# Render backend (permanent)
RENDER="https://apex-trading-backend.onrender.com"

# Production dashboard — prefer backend canonical URL, else r21 verified preview
DASH="${VERIFIED_DASHBOARD_URL:-}"
if [[ -z "$DASH" ]]; then
  DASH=$(curl -sf "$RENDER/api/dashboard-url" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('recommended_url',''))" 2>/dev/null || true)
fi
if [[ -z "$DASH" ]]; then
  DASH="https://apex-trading-dashboard-73nruanbo-apexweb-adams-projects.vercel.app"
fi
LEGACY_DASH="https://apex-trading-dashboard-flame.vercel.app"
if curl -sf "$DASH/api/backend/health" >/dev/null 2>&1; then
  check "Production dashboard API proxy ($DASH)" 1
else
  check "Production dashboard API proxy" 0
fi

CODE=$(curl -s -o /dev/null -w "%{http_code}" "$RENDER/api/health" 2>/dev/null || echo "000")
if [[ "$CODE" == "200" ]]; then
  check "Render backend live ($RENDER)" 1
  VERIFY_HIST=$(curl -s -o /dev/null -w "%{http_code}" "$RENDER/api/verification/history" 2>/dev/null || echo "000")
  if [[ "$VERIFY_HIST" == "200" ]]; then
    check "Verification snapshot endpoint live" 1
  else
    echo "○ Verification history HTTP $VERIFY_HIST — deploy latest for 30-day audit trail"
  fi
  ADMIN_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$RENDER/api/admin/apply-risk-migrations" \
    -H "Content-Type: application/json" -d '{"secret":""}' 2>/dev/null || echo "000")
  if [[ "$ADMIN_CODE" == "200" || "$ADMIN_CODE" == "422" ]]; then
    check "Render backend has latest admin migrate endpoint" 1
  else
    echo "○ Render may be on stale build (admin endpoint HTTP $ADMIN_CODE) — trigger manual deploy"
  fi
  RESET_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$RENDER/api/admin/reset-paper-trading" \
    -H "Content-Type: application/json" -d '{"secret":""}' 2>/dev/null || echo "000")
  if [[ "$RESET_CODE" == "200" || "$RESET_CODE" == "422" || "$RESET_CODE" == "404" ]]; then
    if [[ "$RESET_CODE" == "404" ]]; then
      echo "○ Render missing reset endpoint (HTTP 404) — deploy latest for clean verification reset"
    else
      check "Render backend has admin reset-paper-trading endpoint" 1
    fi
  else
    echo "○ Render reset endpoint HTTP $RESET_CODE — trigger manual deploy"
  fi
  STATUS_JSON=$(curl -sf "$RENDER/api/status" 2>/dev/null || echo "{}")
  REMOTE_COMMIT=$(echo "$STATUS_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('deploy',{}).get('git_commit') or '')" 2>/dev/null || true)
  LOCAL_COMMIT=$(git -C "$(dirname "$0")/.." rev-parse --short HEAD 2>/dev/null || git rev-parse --short HEAD 2>/dev/null || echo "")
  if [[ -n "$REMOTE_COMMIT" && -n "$LOCAL_COMMIT" ]]; then
    if [[ "$REMOTE_COMMIT" == "$LOCAL_COMMIT" || "$REMOTE_COMMIT" == "${LOCAL_COMMIT:0:7}"* ]]; then
      check "Render git commit matches repo ($REMOTE_COMMIT)" 1
    else
      echo "○ Render commit $REMOTE_COMMIT ≠ local $LOCAL_COMMIT — redeploy recommended"
    fi
  fi
else
  echo "✗ Render backend not deployed yet (HTTP $CODE)"
  echo "  → https://render.com/deploy?repo=https://github.com/apexweb-adam/apexweb-adam"
  FAIL=1
fi

echo ""
if [[ "$FAIL" -eq 0 ]]; then
  echo "All checks passed."
else
  echo "Some checks failed — see SUPABASE_SETUP.md and RENDER_DEPLOY.md"
  exit 1
fi
