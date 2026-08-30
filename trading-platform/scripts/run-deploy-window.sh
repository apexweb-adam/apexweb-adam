#!/usr/bin/env bash
# Full CME deploy-window workflow: preflight → sync env → wait → post-verify.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"

echo "=== CME Deploy Window — $(date -u '+%Y-%m-%d %H:%M UTC') ==="
echo "Backend: $BACKEND"
echo ""

bash "$ROOT/scripts/ops-gate-summary.sh" || true
echo ""

if ! bash "$ROOT/scripts/verify-pre-deploy.sh"; then
  echo ""
  echo "Preflight failed — deploy not started." >&2
  exit 1
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
