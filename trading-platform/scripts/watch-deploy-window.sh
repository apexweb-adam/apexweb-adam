#!/usr/bin/env bash
# Poll /api/status until the CME deploy window opens (4–6h before Sunday reopen).
# Usage:
#   watch-deploy-window.sh [--interval SECONDS] [--once]
#   watch-deploy-window.sh --deploy   # run verify-pre-deploy + sync-render-env when window opens
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"
INTERVAL="${WATCH_INTERVAL:-300}"
ONCE=false
AUTO_DEPLOY=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --interval)
      INTERVAL="${2:-300}"
      shift 2
      ;;
    --once)
      ONCE=true
      shift
      ;;
    --deploy)
      AUTO_DEPLOY=true
      shift
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

run_check() {
  STATUS=$(curl -fsS -m 90 "$BACKEND/api/status" 2>/dev/null || echo "{}")
  python3 << PY
import json, sys

status = json.loads('''$STATUS''')
deploy = status.get("deploy") or {}
window = deploy.get("cme_deploy_window")
rev = deploy.get("platform_revision")
current = deploy.get("platform_revision_current")

print(f"=== Deploy Window Watch — $(date -u '+%Y-%m-%d %H:%M UTC') ===")
print(f"Backend: $BACKEND")
print(f"  platform_revision={rev} current={current}")

if current is True:
    print("✓ Production revision current — no deploy window needed")
    sys.exit(0)

if not window:
    print("○ No deploy window payload — CME timing unknown or revision check skipped")
    sys.exit(0)

print(f"  {window.get('message', '')}")
if window.get("window_opens_at_utc"):
    print(f"  opens_utc={window.get('window_opens_at_utc')}")
if window.get("window_closes_at_utc"):
    print(f"  closes_utc={window.get('window_closes_at_utc')}")

if window.get("window_closed"):
    print("✗ Deploy window closed — deploy manually before CME open if still behind")
    sys.exit(2)

if window.get("in_window"):
    print("")
    print("*** DEPLOY WINDOW ACTIVE — run preflight then deploy ***")
    print(f"  {window.get('verify_command', 'bash trading-platform/scripts/verify-pre-deploy.sh')}")
    print(f"  {window.get('deploy_command', 'TRIGGER_DEPLOY=true bash trading-platform/scripts/sync-render-env.sh')}")
    print(f"  bash trading-platform/scripts/verify-post-deploy.sh")
    sys.exit(10)

sys.exit(0)
PY
}

while true; do
  run_check
  rc=$?
  if [[ $rc -eq 10 ]]; then
    if [[ "$AUTO_DEPLOY" == "true" ]]; then
      echo ""
      echo "Auto-deploy enabled — running preflight..."
      if bash "$ROOT/scripts/verify-pre-deploy.sh"; then
        TRIGGER_DEPLOY=true bash "$ROOT/scripts/sync-render-env.sh"
        bash "$ROOT/scripts/verify-post-deploy.sh" || true
      else
        echo "Preflight failed — deploy not triggered" >&2
        exit 1
      fi
    fi
    exit 0
  fi
  if [[ $rc -eq 2 ]]; then
    exit 1
  fi
  if [[ "$ONCE" == "true" ]]; then
    exit 0
  fi
  echo ""
  echo "Next check in ${INTERVAL}s (Ctrl+C to stop)"
  sleep "$INTERVAL"
done
