#!/usr/bin/env bash
# Poll until the CME deploy window opens (4–6h before Sunday reopen).
# Usage:
#   watch-deploy-window.sh [--interval SECONDS] [--once]
#   watch-deploy-window.sh --deploy   # run verify-pre-deploy + sync-render-env when window opens
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/fetch_json.sh
source "$ROOT/scripts/lib/fetch_json.sh"
BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"
CODE_REV="$(grep '^EXPECTED_PLATFORM_REVISION' "$ROOT/backend/app/engines/deploy_status.py" | sed -n 's/.*"\([^"]*\)".*/\1/p')"
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
  local snap status deploy
  snap=$(fetch_json "$BACKEND/api/deploy/snapshot" 45 2 || echo "")
  if [[ -n "$snap" && "$snap" != "{}" ]]; then
    echo "$snap"
    return 0
  fi

  status=$(fetch_json "$BACKEND/api/status" 60 2 || echo "")
  if [[ -n "$status" && "$status" != "{}" ]]; then
    deploy=$(echo "$status" | python3 -c "import json,sys; d=json.load(sys.stdin); print(json.dumps(d.get('deploy') or {}))" 2>/dev/null || echo "{}")
    if [[ -n "$deploy" && "$deploy" != "{}" ]]; then
      echo "$deploy"
      return 0
    fi
  fi

  if deploy=$(cd "$ROOT/backend" && PYTHONPATH=. python3 -c \
    "from app.engines.deploy_status import build_deploy_snapshot; import json; print(json.dumps(build_deploy_snapshot()))" \
    2>/dev/null); then
    if [[ -n "$deploy" && "$deploy" != "{}" ]]; then
      echo "○ Using local deploy snapshot (backend unavailable)" >&2
      echo "$deploy"
      return 0
    fi
  fi

  echo "{}"
  return 1
}

run_check() {
  local snapshot
  snapshot=$(fetch_snapshot || echo "{}")
  SNAPSHOT_JSON="$snapshot" CODE_REV="$CODE_REV" BACKEND="$BACKEND" python3 << 'PY'
import json, os, sys
from datetime import datetime, timezone

payload = json.loads(os.environ.get("SNAPSHOT_JSON") or "{}")
code_rev = os.environ.get("CODE_REV") or "?"
backend = os.environ.get("BACKEND") or ""

now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
print(f"=== Deploy Window Watch — {now} ===")
print(f"Backend: {backend}")
print(f"  code_target={code_rev}")

window = payload.get("cme_deploy_window")
rev = payload.get("platform_revision")
current = payload.get("platform_revision_current")
expected = payload.get("expected_platform_revision")

print(f"  platform_revision={rev} expected={expected} current={current}")
if expected and code_rev and expected != code_rev:
    print(f"  deploy will advance prod expected {expected} → {code_rev}")

x_mode = payload.get("x_intel_collection_mode")
if x_mode:
    print(f"  x_intel_collection_mode={x_mode}")

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
    mins = payload.get("cme_minutes_until_open")
    if mins is not None:
        print(f"  cme_open_in={mins}min")
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
    ready = payload.get("deploy_credentials_ready")
    warnings = payload.get("deploy_credentials_warnings") or []
    if ready is False:
        print("  credentials=ACTION REQUIRED (run check-deploy-credentials.sh --strict before deploy)")
        for item in warnings:
            print(f"    - {item}")
    elif ready is True:
        print("  credentials=ready")
    nudge = payload.get("fomo_bearer_nudge_message")
    if nudge:
        print(f"  fomo_nudge={nudge}")
    print("")
    print("*** DEPLOY WINDOW ACTIVE ***")
    run_all = payload.get("run_deploy_window_command") or window.get("run_deploy_window_command")
    if run_all:
        print(f"  {run_all}")
    else:
        print(f"  {window.get('verify_command', 'bash trading-platform/scripts/verify-pre-deploy.sh')}")
        print(f"  {window.get('deploy_command', 'TRIGGER_DEPLOY=true bash trading-platform/scripts/sync-render-env.sh')}")
        wait_cmd = payload.get("wait_for_deploy_command") or window.get("wait_for_deploy_command")
        if wait_cmd:
            print(f"  {wait_cmd}")
    print(f"  bash trading-platform/scripts/verify-dashboard-bundle.sh")
    weekend = payload.get("weekend_ops_verify_command")
    if weekend:
        print(f"  {weekend}")
    sys.exit(10)

sys.exit(0)
PY
}

print_cme_prep() {
  local cme
  cme=$(fetch_json "$BACKEND/api/gate/cme-reopen-checklist" 60 2 || echo "{}")
  echo "$cme" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if not data:
    raise SystemExit(0)
open_ready = data.get('open_ready') or {}
open_syms = open_ready.get('symbols') or []
sticky = open_ready.get('sticky_symbols') or []
near = (data.get('near_floor') or {}).get('symbols') or []
auto_entry = open_ready.get('auto_entry_queued')
mins = data.get('minutes_until_open')
parts = [f'CME prep: open_ready={open_syms or \"none\"}']
if sticky:
    parts.append(f'sticky={sticky}')
if near:
    parts.append(f'near_floor={near}')
parts.append(f'auto_entry={auto_entry}')
if mins is not None:
    parts.append(f'open_in={mins}min')
print('  ' + ' '.join(parts))
for row in (data.get('near_floor') or {}).get('details') or []:
    sym = row.get('symbol')
    gap = row.get('gap_to_floor')
    comp = row.get('composite')
    if sym and gap is not None:
        print(f'    near_floor {sym}: composite={comp} need +{gap}')
" 2>/dev/null || true
}

while true; do
  run_check
  rc=$?
  if [[ $rc -eq 0 ]]; then
    print_cme_prep
  fi
  if [[ $rc -eq 10 ]]; then
    if [[ "$AUTO_DEPLOY" == "true" ]]; then
      echo ""
      if ! bash "$ROOT/scripts/check-deploy-credentials.sh" --strict; then
        echo "Auto-deploy blocked — refresh credentials before deploy window run." >&2
        exit 1
      fi
      echo "Auto-deploy enabled — running full deploy window workflow..."
      if ! bash "$ROOT/scripts/run-deploy-window.sh"; then
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
