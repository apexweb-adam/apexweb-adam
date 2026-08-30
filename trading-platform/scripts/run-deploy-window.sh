#!/usr/bin/env bash
# Full CME deploy-window workflow: preflight → sync env → wait → post-verify.
# Usage: run-deploy-window.sh [--dry-run]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

echo "=== CME Deploy Window — $(date -u '+%Y-%m-%d %H:%M UTC') ==="
echo "Backend: $BACKEND"
if [[ "$DRY_RUN" == "true" ]]; then
  echo "Mode: dry-run (preflight only — no deploy)"
fi
echo ""

bash "$ROOT/scripts/ops-gate-summary.sh" || true
echo ""
bash "$ROOT/scripts/check-fomo-bearer.sh" || true
echo ""

if ! bash "$ROOT/scripts/verify-pre-deploy.sh"; then
  echo ""
  echo "Preflight failed — deploy not started." >&2
  exit 1
fi

if [[ "$DRY_RUN" == "true" ]]; then
  echo ""
  if bash "$ROOT/scripts/verify-cme-reopen.sh"; then
    echo "✓ Dry-run complete — ready for deploy window"
  else
    echo "○ CME preflight has warnings — review before deploy" >&2
    exit 1
  fi
  echo ""
  if [[ -f "$ROOT/.crm-load-baseline" ]]; then
    echo "CRM baseline saved: $(tr -d '[:space:]' < "$ROOT/.crm-load-baseline")s → compare after deploy with verify-post-deploy.sh"
  fi
  echo ""
  echo "When window opens:"
  echo "  bash trading-platform/scripts/run-deploy-window.sh"
  exit 0
fi

echo ""
echo "Starting Render deploy..."
TRIGGER_DEPLOY=true bash "$ROOT/scripts/sync-render-env.sh"

echo ""
if ! bash "$ROOT/scripts/wait-for-render-deploy.sh" --verify; then
  echo ""
  echo "Deploy wait/verify failed — check Render dashboard." >&2
  exit 1
fi

echo ""
if bash "$ROOT/scripts/verify-cme-reopen.sh"; then
  echo "✓ CME reopen preflight still passing after deploy"
else
  echo "○ CME preflight warnings after deploy — review before open" >&2
fi

echo ""
echo "After CME open (22:00 UTC):"
echo "  bash trading-platform/scripts/verify-cme-post-open.sh"
echo ""
echo "Monday before US open (13:30 UTC):"
echo "  bash trading-platform/scripts/verify-us-stocks-open.sh --watch 120"
