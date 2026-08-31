#!/usr/bin/env bash
# Verify learning loop + content study visibility (API, CRM landing, source labels).
# Usage: verify-crm-learning.sh [--strict]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/fetch_json.sh
source "$ROOT/scripts/lib/fetch_json.sh"
BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"
STRICT=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --strict)
      STRICT=true
      shift
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

pass=0
fail=0
warn=0

ok() { echo "✓ $*"; pass=$((pass + 1)); }
bad() { echo "✗ $*"; fail=$((fail + 1)); }
note() { echo "○ $*"; warn=$((warn + 1)); }

echo "=== CRM Learning Loop Verification — $(date -u '+%Y-%m-%d %H:%M UTC') ==="
echo "Backend: $BACKEND"
echo ""

if ! check_backend_suspension "$BACKEND"; then
  bad "Backend billing-suspended — learning loop offline until billing resume"
  echo ""
  echo "Recovery:"
  echo "  bash trading-platform/scripts/recover-render-billing.sh"
  exit 1
fi

wake_backend "$BACKEND" 2
STATUS=$(fetch_json "$BACKEND/api/status" 60 2)
INSIGHTS=$(fetch_json "$BACKEND/api/insights?limit=5" 30 2)
REVIEWS=$(fetch_json "$BACKEND/api/reviews?limit=1" 30 2)
CRM_CODE=$(curl -sS -o /dev/null -m 120 -w "%{http_code}" "$BACKEND/crm" 2>/dev/null || echo "000")

if echo "$STATUS" | python3 -c "import json,sys; json.load(sys.stdin)" 2>/dev/null; then
  ok "Backend /api/status reachable"
else
  bad "Backend /api/status invalid or empty"
fi

STATUS_JSON="$STATUS" python3 << 'PY'
import json, os, sys

data = json.loads(os.environ.get("STATUS_JSON") or "{}")
learning = data.get("learning") or {}
content = data.get("content_study") or {}

if not learning and not content:
    print("missing_learning_blocks")
    sys.exit(1)

analyses = learning.get("trade_analyses") or 0
reviews = learning.get("daily_reviews") or 0
applied = learning.get("insights_applied") or 0
pending = learning.get("insights_pending") or 0
intel_count = learning.get("intel_pattern_count") or 0

print(
    f"learning analyses={analyses} reviews={reviews} "
    f"insights_applied={applied} pending={pending} "
    f"intel_pattern_alerts={intel_count}"
)
for alert in (learning.get("intel_pattern_alerts") or [])[:5]:
    print(f"  intel_alert={alert}")

recent = content.get("recent") or []
if recent:
    print(f"content_study applied={content.get('insights_applied') or 0} recent={len(recent)}")
    missing = [row for row in recent if row.get("source_type") and not row.get("source_label")]
    for row in recent[:5]:
        label = row.get("source_label") or row.get("source_type") or "unknown"
        title = (row.get("title") or "")[:48]
        state = "applied" if row.get("applied") else "pending"
        print(f"  content_study [{label}] {title} ({state})")
    if missing:
        print("missing_source_label")
        sys.exit(2)
sys.exit(0)
PY
LEARNING_RC=$?

case "$LEARNING_RC" in
  0)
    ok "Learning + content study blocks present on /api/status"
    ;;
  1)
    bad "Learning blocks missing from /api/status — confirm r125+ revision"
    ;;
  2)
    bad "Content study rows missing source_label — confirm r125+ revision"
    ;;
  *)
    note "Learning state unavailable"
    ;;
esac

if echo "$INSIGHTS" | python3 -c "
import json, sys
rows = json.load(sys.stdin)
if not isinstance(rows, list):
    sys.exit(1)
if not rows:
    sys.exit(2)
missing = [r for r in rows if r.get('source_type') and not r.get('source_label')]
sys.exit(3 if missing else 0)
" 2>/dev/null; then
  ok "/api/insights returns source_label on insights"
else
  INSIGHTS_RC=$?
  if [[ "$INSIGHTS_RC" == "2" ]]; then
    note "/api/insights empty — learning loop may need first trade day"
  elif [[ "$INSIGHTS_RC" == "3" ]]; then
    bad "/api/insights missing source_label — confirm serialize_learning_insight live"
  else
    note "/api/insights unavailable"
  fi
fi

if echo "$REVIEWS" | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if isinstance(d,list) and len(d)>0 else 1)" 2>/dev/null; then
  ok "Daily review API has history"
else
  note "Daily review API empty — run daily review cron or run-daily-review-now.sh"
fi

if [[ "$CRM_CODE" == "200" ]]; then
  CRM_BODY=$(curl -fsS -m 120 "$BACKEND/crm" 2>/dev/null || echo "")
  if echo "$CRM_BODY" | grep -q "Today's learning loop"; then
    ok "CRM landing shows learning loop section"
  else
    note "CRM landing missing learning section — may be empty for today"
  fi
  if echo "$CRM_BODY" | grep -q "Content study"; then
    ok "CRM landing shows content study section"
  else
    note "CRM landing missing content study section"
  fi
else
  note "CRM landing HTTP $CRM_CODE"
fi

echo ""
echo "Results: $pass passed, $fail failed, $warn notes"
if [[ "$fail" -gt 0 ]]; then
  if [[ "$STRICT" == "true" ]]; then
    exit 1
  fi
  note "Re-run with --strict to fail on blockers"
fi

echo ""
echo "Manual triggers:"
echo "  bash trading-platform/scripts/run-daily-review-now.sh"
echo "  curl -X POST $BACKEND/api/admin/run-content-study"
