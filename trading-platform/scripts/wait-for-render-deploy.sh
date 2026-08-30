#!/usr/bin/env bash
# Poll Render backend until PLATFORM_REVISION matches code target (or snapshot reports current).
# Usage:
#   wait-for-render-deploy.sh [--max-wait SECONDS] [--interval SECONDS] [--verify]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"
EXPECTED_REVISION="${EXPECTED_PLATFORM_REVISION:-$(grep '^EXPECTED_PLATFORM_REVISION' "$ROOT/backend/app/engines/deploy_status.py" | sed -n 's/.*"\([^"]*\)".*/\1/p')}"
MAX_WAIT="${MAX_WAIT:-600}"
INTERVAL="${INTERVAL:-30}"
VERIFY=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --max-wait)
      MAX_WAIT="${2:-600}"
      shift 2
      ;;
    --interval)
      INTERVAL="${2:-30}"
      shift 2
      ;;
    --verify)
      VERIFY=true
      shift
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

echo "=== Wait for Render Deploy — $(date -u '+%Y-%m-%d %H:%M UTC') ==="
echo "Backend: $BACKEND"
echo "Target revision: $EXPECTED_REVISION"
echo "Max wait: ${MAX_WAIT}s (poll every ${INTERVAL}s)"
echo ""

deadline=$(( $(date +%s) + MAX_WAIT ))
attempt=0

while [[ $(date +%s) -lt $deadline ]]; do
  attempt=$((attempt + 1))
  SNAPSHOT=$(curl -fsS -m 20 "$BACKEND/api/deploy/snapshot" 2>/dev/null || echo "{}")
  set +e
  READY=$(SNAPSHOT="$SNAPSHOT" EXPECTED="$EXPECTED_REVISION" python3 << 'PY'
import json, os, sys
snap = json.loads(os.environ.get("SNAPSHOT") or "{}")
expected = os.environ.get("EXPECTED") or ""
rev = snap.get("platform_revision") or "?"
current = snap.get("platform_revision_current")
print(f"revision={rev} current={current}")
if current is True:
    sys.exit(0)
if expected and rev == expected:
    sys.exit(0)
sys.exit(1)
PY
  )
  rc=$?
  set -e
  echo "[$attempt] $READY"
  if [[ $rc -eq 0 ]]; then
    echo ""
    echo "✓ Production revision live ($EXPECTED_REVISION)"
    if [[ "$VERIFY" == "true" ]]; then
      echo ""
      bash "$ROOT/scripts/verify-post-deploy.sh"
      bash "$ROOT/scripts/verify-dashboard-bundle.sh" || true
    fi
    exit 0
  fi
  remaining=$((deadline - $(date +%s)))
  if [[ $remaining -le 0 ]]; then
    break
  fi
  sleep_for=$INTERVAL
  if [[ $remaining -lt $sleep_for ]]; then
    sleep_for=$remaining
  fi
  sleep "$sleep_for"
done

echo ""
echo "✗ Timed out after ${MAX_WAIT}s — revision still not $EXPECTED_REVISION"
echo "  Check Render dashboard for deploy status, then rerun:"
echo "  bash trading-platform/scripts/wait-for-render-deploy.sh --verify"
exit 1
