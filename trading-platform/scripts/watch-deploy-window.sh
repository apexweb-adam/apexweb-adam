#!/usr/bin/env bash
# Poll until the CME deploy window opens (4–6h before Sunday reopen).
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

fetch_snapshot() {
  local tmp snap_code status_code
  tmp="${TMPDIR:-/tmp}/apex-deploy-snap.$$"

  snap_code=$(curl -sS -m 12 -o "$tmp" -w "%{http_code}" "$BACKEND/api/deploy/snapshot" 2>/dev/null || echo "000")
  if [[ "$snap_code" == "200" && -s "$tmp" ]]; then
    cat "$tmp"
    rm -f "$tmp"
    return 0
  fi

  # Pre-r358 backends return 404 — fall back once to /api/status deploy block.
  status_code=$(curl -sS -m 45 -o "$tmp" -w "%{http_code}" "$BACKEND/api/status" 2>/dev/null || echo "000")
  if [[ "$status_code" == "200" && -s "$tmp" ]]; then
    if python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$tmp" 2>/dev/null; then
      python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(json.dumps(d.get('deploy') or {}))" "$tmp"
      rm -f "$tmp"
      return 0
    fi
  fi

  rm -f "$tmp"
  echo "{}"
  return 1
}

run_check() {
  SNAPSHOT=$(fetch_snapshot) || SNAPSHOT="{}"
  if [[ "$SNAPSHOT" == "{}" || "$SNAPSHOT" == "" ]]; then
    SNAPSHOT=$(cd "$ROOT/backend" && PYTHONPATH=. python3 -c \
      "from app.engines.deploy_status import build_deploy_snapshot; import json; print(json.dumps(build_deploy_snapshot()))" \
      2>/dev/null || echo "{}")
    if [[ "$SNAPSHOT" != "{}" ]]; then
      echo "○ Using local deploy snapshot (backend /api/status unavailable)"
    fi
  fi
  python3 << PY
import json, sys

payload = json.loads('''$SNAPSHOT''')
# /api/status fallback wraps deploy block only
if "cme_deploy_window" not in payload and payload.get("deploy"):
    payload = payload["deploy"]
window = payload.get("cme_deploy_window")
rev = payload.get("platform_revision")
current = payload.get("platform_revision_current")
expected = payload.get("expected_platform_revision")

print(f"=== Deploy Window Watch — $(date -u '+%Y-%m-%d %H:%M UTC') ===")
print(f"Backend: $BACKEND")
print(f"  platform_revision={rev} expected={expected} current={current}")

bundle = payload.get("expected_dashboard_bundle")
if bundle:
    print(f"  expected_dashboard_bundle={bundle}")
    for key in ("dashboard_bundle_verify_command", "weekend_ops_verify_command"):
        cmd = payload.get(key)
        if cmd:
            print(f"  {cmd}")

if not payload:
    print("✗ Could not reach deploy snapshot or /api/status")
    sys.exit(3)

if current is True:
    print("✓ Production revision current — no deploy window needed")
    sys.exit(0)

if not window:
    mins = payload.get("cme_minutes_until_open")
    if mins is not None:
        print(f"○ CME open in {mins}min — deploy window payload missing (deploy r358+ for /api/deploy/snapshot)")
    else:
        print("○ No deploy window payload — CME timing unknown")
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
    print(f"  bash trading-platform/scripts/verify-dashboard-bundle.sh")
    weekend = payload.get("weekend_ops_verify_command")
    if weekend:
        print(f"  {weekend}")
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
        bash "$ROOT/scripts/verify-dashboard-bundle.sh" || true
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
