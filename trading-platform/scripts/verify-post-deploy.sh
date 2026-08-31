#!/usr/bin/env bash
# Verify session-open bundle (r337+) is live after Render deploy.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LIB="$ROOT/scripts/lib/deploy_json.py"
# shellcheck source=lib/fetch_json.sh
source "$ROOT/scripts/lib/fetch_json.sh"
BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"
EXPECTED_REVISION="${EXPECTED_PLATFORM_REVISION:-$(grep '^EXPECTED_PLATFORM_REVISION' "$ROOT/backend/app/engines/deploy_status.py" | sed -n 's/.*"\([^"]*\)".*/\1/p')}"

pass=0
fail=0
warn=0

ok() { echo "✓ $*"; pass=$((pass + 1)); }
bad() { echo "✗ $*"; fail=$((fail + 1)); }
note() { echo "○ $*"; warn=$((warn + 1)); }

echo "=== Post-Deploy Session-Open Verification — $(date -u '+%Y-%m-%d %H:%M UTC') ==="
echo "Backend: $BACKEND"
echo "Expected revision: $EXPECTED_REVISION"
echo ""

bash "$ROOT/scripts/ops-gate-summary.sh" || true
echo ""

STATUS=$(fetch_json "$BACKEND/api/status" 60 2)
CHECKLIST=$(fetch_json "$BACKEND/api/gate/cme-reopen-checklist" 60 2)
SNAPSHOT=$(fetch_json "$BACKEND/api/deploy/snapshot" 45 2)

TMP_STATUS=$(mktemp)
TMP_CHECKLIST=$(mktemp)
TMP_SNAPSHOT=$(mktemp)
trap 'rm -f "$TMP_STATUS" "$TMP_CHECKLIST" "$TMP_SNAPSHOT"' EXIT
echo "$STATUS" > "$TMP_STATUS"
echo "$CHECKLIST" > "$TMP_CHECKLIST"
echo "$SNAPSHOT" > "$TMP_SNAPSHOT"

if python3 "$LIB" post-deploy-check \
  --status-file "$TMP_STATUS" \
  --checklist-file "$TMP_CHECKLIST" \
  --snapshot-file "$TMP_SNAPSHOT" \
  --expected "$EXPECTED_REVISION"; then
  ok "Post-deploy session-open bundle live"
else
  bad "Post-deploy verification failed — revision or session-open features missing"
fi

PROD_REV_CHECK=$(echo "$SNAPSHOT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('platform_revision') or '')" 2>/dev/null || echo "")
if [[ -z "$PROD_REV_CHECK" ]]; then
  PROD_REV_CHECK=$(echo "$STATUS" | python3 -c "import json,sys; d=json.load(sys.stdin); print((d.get('deploy') or {}).get('platform_revision') or '')" 2>/dev/null || echo "")
fi
if [[ "$PROD_REV_CHECK" == "$EXPECTED_REVISION" ]]; then
  if curl -fsS -m 20 "$BACKEND/openapi.json" 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if '/api/learning/apply-pending-insights' in (d.get('paths') or {}) else 1)" 2>/dev/null; then
    ok "Learning apply endpoint registered (r380+)"
  else
    note "Learning apply endpoint not in OpenAPI — confirm r380+ revision live"
  fi

  INTEL_SOURCES=$(fetch_json "$BACKEND/api/intelligence/sources" 30 2)
  TMP_SOURCES=$(mktemp)
  trap 'rm -f "$TMP_STATUS" "$TMP_CHECKLIST" "$TMP_SNAPSHOT" "$TMP_SOURCES"' EXIT
  echo "$INTEL_SOURCES" > "$TMP_SOURCES"
  INTEL_STATUS=$(python3 "$LIB" intel-readiness \
    --sources-file "$TMP_SOURCES" \
    --snapshot-file "$TMP_SNAPSHOT" \
    --prod-rev "$PROD_REV_CHECK" \
    --code-rev "$EXPECTED_REVISION" 2>/dev/null || echo "missing")
  if [[ "$INTEL_STATUS" == "ok" ]]; then
    ok "Intel source health fields (r385+)"
  elif [[ "$INTEL_STATUS" == "partial" ]]; then
    note "Intel sources API ready — confirm snapshot r385 fields on production"
  else
    note "Intel source r385 fields missing — confirm revision live"
  fi
fi

if bash "$ROOT/scripts/verify-cme-reopen.sh"; then
  ok "CME reopen preflight still passing"
else
  bad "CME reopen preflight failed after deploy"
fi

if bash "$ROOT/scripts/verify-dashboard-bundle.sh"; then
  :
else
  note "Dashboard bundle check failed (non-blocking)"
fi

bash "$ROOT/scripts/try-promote-vercel-dashboard.sh" || true

CRM_TIME=$(curl -sS -o /dev/null -m 120 -w "%{time_total}" "$BACKEND/crm" 2>/dev/null || echo "")
BASELINE_FILE="$ROOT/.crm-load-baseline"
if [[ -n "$CRM_TIME" ]]; then
  CRM_SEC=$(python3 -c "print(f'{float('$CRM_TIME'):.1f}')")
  BASELINE_SEC=""
  if [[ -f "$BASELINE_FILE" ]]; then
    BASELINE_SEC=$(tr -d '[:space:]' < "$BASELINE_FILE")
  fi
  if python3 -c "import sys; sys.exit(0 if float('$CRM_TIME') < 30 else 1)"; then
    if [[ -n "$BASELINE_SEC" ]]; then
      ok "CRM landing loaded in ${CRM_SEC}s (baseline ${BASELINE_SEC}s — r367-r371 stack)"
    else
      ok "CRM landing loaded in ${CRM_SEC}s"
    fi
  else
    if [[ -n "$BASELINE_SEC" ]]; then
      CRM_NOTE=$(python3 -c "now=float('$CRM_TIME'); base=float('$BASELINE_SEC'); delta=base-now; msg=f'CRM landing {now:.1f}s vs baseline {base:.1f}s ({delta:+.1f}s)'; msg += ' — improved but still >30s' if delta >= 5 else (' — slower than baseline; check cold start' if delta <= -5 else ' — similar to baseline; confirm r369 live'); print(msg)")
      note "$CRM_NOTE"
    else
      note "CRM landing slow (${CRM_SEC}s) — confirm r371 revision live; target <30s after r367-r371 stack"
    fi
  fi
else
  note "CRM landing timing unavailable"
fi

bash "$ROOT/scripts/check-deploy-credentials.sh" || true

REVIEWS=$(fetch_json "$BACKEND/api/reviews?limit=1" 20 2)
if echo "$REVIEWS" | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if isinstance(d,list) and len(d)>0 else 1)" 2>/dev/null; then
  ok "Daily review API has history"
else
  note "Daily review API empty — learning loop may need first trade day"
fi

if echo "$STATUS" | python3 -c "
import json, sys
status = json.load(sys.stdin)
learning = status.get('learning') or {}
content = status.get('content_study') or {}
intel_count = learning.get('intel_pattern_count') or 0
if intel_count:
    print(f'  intel_pattern_alerts={intel_count}')
    for alert in (learning.get('intel_pattern_alerts') or [])[:3]:
        print(f'    - {alert}')
recent = content.get('recent') or []
if recent:
    missing = [row for row in recent if row.get('source_type') and not row.get('source_label')]
    for row in recent[:3]:
        label = row.get('source_label') or row.get('source_type')
        title = (row.get('title') or '')[:48]
        print(f'  content_study [{label}] {title}')
    sys.exit(1 if missing else 0)
sys.exit(0)
"; then
  ok "Content study highlights include source_label (r125+)"
else
  if echo "$STATUS" | python3 -c "
import json, sys
recent = (json.load(sys.stdin).get('content_study') or {}).get('recent') or []
sys.exit(0 if recent else 1)
" 2>/dev/null; then
    note "Content study rows missing source_label — confirm r125+ revision live"
  elif echo "$STATUS" | python3 -c "
import json, sys
learning = json.load(sys.stdin).get('learning') or {}
sys.exit(0 if (learning.get('intel_pattern_count') or 0) > 0 else 1)
" 2>/dev/null; then
    note "Intel pattern alerts active — strategy gates may have tightened"
  fi
fi

echo ""
echo "Results: $pass passed, $fail failed, $warn notes"
if [[ "$fail" -gt 0 ]]; then
  exit 1
fi

echo ""
echo "Full platform check (optional):"
echo "  bash trading-platform/scripts/verify-platform.sh"
echo ""
echo "After CME open (22:00 UTC):"
echo "  bash trading-platform/scripts/verify-cme-post-open.sh"
