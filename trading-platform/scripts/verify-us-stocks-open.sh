#!/usr/bin/env bash
# Preflight checks before Monday US stocks open (13:30 UTC).
# Usage: verify-us-stocks-open.sh [--watch SECONDS]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/fetch_json.sh
source "$ROOT/scripts/lib/fetch_json.sh"
BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"
EXPECTED_REVISION="${EXPECTED_PLATFORM_REVISION:-$(grep '^EXPECTED_PLATFORM_REVISION' "$ROOT/backend/app/engines/deploy_status.py" | sed -n 's/.*"\([^"]*\)".*/\1/p')}"
WATCH_INTERVAL=""

if [[ "${1:-}" == "--watch" ]]; then
  WATCH_INTERVAL="${2:-120}"
fi

pass=0
fail=0
warn=0

ok() { echo "✓ $*"; pass=$((pass + 1)); }
bad() { echo "✗ $*"; fail=$((fail + 1)); }
note() { echo "○ $*"; warn=$((warn + 1)); }

run_preflight() {
  pass=0
  fail=0
  warn=0

  echo "=== US Stocks Open Preflight — $(date -u '+%Y-%m-%d %H:%M UTC') ==="
  echo "Backend: $BACKEND"
  echo "Expected revision (code): $EXPECTED_REVISION"
  echo ""

  if ! check_backend_suspension "$BACKEND"; then
    bad "Backend billing-suspended — AAPL auto-entry cannot fire until Render is restored"
    echo ""
    echo "Preflight: $pass passed, $fail failed, $warn warnings"
    return 2
  fi

  bash "$ROOT/scripts/ops-gate-summary.sh" || true
  echo ""

  wake_backend "$BACKEND" 3

  TMP=$(mktemp -d)
  trap 'rm -rf "$TMP"' RETURN
  CHECKLIST=$(fetch_json "$BACKEND/api/gate/us-stocks-open-checklist" 120 3)
  if [[ -z "$CHECKLIST" || "$CHECKLIST" == "{}" ]]; then
    wake_backend "$BACKEND" 2
    CHECKLIST=$(fetch_json "$BACKEND/api/gate/us-stocks-open-checklist" 120 3)
  fi
  echo "$CHECKLIST" > "$TMP/checklist.json"

  fetch_json "$BACKEND/api/bots/stocks_futures/scan-preview" 120 3 > "$TMP/scan.json" || echo "{}" > "$TMP/scan.json"

  if [[ -n "$CHECKLIST" && "$CHECKLIST" != "{}" ]]; then
    CHECKLIST_FILE="$TMP/checklist.json" python3 << 'PY'
import json, os, sys
from pathlib import Path

data = json.loads(Path(os.environ["CHECKLIST_FILE"]).read_text(encoding="utf-8"))
deploy = data.get("deploy") or {}
open_ready = data.get("open_ready") or {}
near = data.get("near_floor") or {}
print(f"  checklist_phase={data.get('phase')} ready={data.get('ready')}")
print(f"  platform_revision={deploy.get('platform_revision')} current={deploy.get('platform_revision_current')}")
print(f"  prep_phase={data.get('prep_phase')} minutes_until_open={data.get('minutes_until_open')}")
print(f"  auto_entry_queued={open_ready.get('auto_entry_queued')} composite_floor={open_ready.get('composite_floor')}")
print(f"  open_ready={open_ready.get('symbols')}")
sticky = open_ready.get("sticky_symbols") or []
if sticky:
    print(f"  sticky_queue={sticky} (release_margin={open_ready.get('release_margin')})")
print(f"  near_floor={near.get('symbols')}")
for row in near.get("details") or []:
    sym = row.get("symbol")
    comp = row.get("composite")
    gap = row.get("gap_to_floor")
    gap_label = f" need +{gap}" if gap is not None else ""
    print(f"    near_floor {sym}: composite={comp}{gap_label}")
for row in open_ready.get("details") or []:
    sym = row.get("symbol")
    comp = row.get("composite")
    blockers = row.get("blockers") or []
    sticky_flag = " sticky" if row.get("sticky_queue") else ""
    print(f"    {sym}: composite={comp}{sticky_flag} blockers={blockers}")
for row in data.get("checks") or []:
    print(f"  check {row.get('id')}={row.get('status')}: {row.get('message')}")
critical_fail = [c for c in (data.get("checks") or []) if c.get("critical") and c.get("status") == "fail"]
if critical_fail:
    print("  errors=" + ",".join(c["id"] for c in critical_fail))
    sys.exit(1)
sys.exit(0)
PY
    if [[ $? -eq 0 ]]; then
      ok "US stocks open checklist passed"
    else
      bad "US stocks open checklist failed"
    fi

    SCAN_FILE="$TMP/scan.json" python3 << 'PY'
import json, os
from pathlib import Path

path = Path(os.environ.get("SCAN_FILE", ""))
if not path.is_file():
    raise SystemExit(0)
try:
    scan = json.loads(path.read_text(encoding="utf-8") or "{}")
except json.JSONDecodeError:
    raise SystemExit(0)
print(
    f"  scan.imminent_scan={scan.get('stocks_open_imminent_scan')} "
    f"fast_scan={scan.get('stocks_gate_fast_scan_active')}"
)
print(
    f"  scan.trade_count_gap={scan.get('stocks_trade_count_gap')} "
    f"open_ready_candidates={scan.get('open_ready_candidates')}"
)
minutes = scan.get("session", {}).get("minutes_until_open")
if minutes is not None and minutes <= 30 and not scan.get("stocks_open_imminent_scan"):
    print("  warn=imminent_scan_expected (T-30 min window)")
PY
  else
    note "Checklist endpoint unavailable — using prep-status fallback"
    PREP=$(fetch_json "$BACKEND/api/gate/prep-status" 45 2 || echo "{}")
    echo "$PREP" | python3 -c "
import json, sys
prep = json.load(sys.stdin)
stocks = prep.get('stocks_futures') or {}
us = (prep.get('next_session_events') or {}).get('us_stocks_open') or {}
open_ready = stocks.get('open_ready_symbols') or us.get('open_ready_symbols') or []
auto_entry = stocks.get('auto_entry_queued') or us.get('auto_entry_queued')
print(f\"  minutes_until_open={stocks.get('minutes_until_open') or us.get('minutes_until_open')}\")
print(f\"  auto_entry_queued={auto_entry} open_ready={open_ready}\")
sys.exit(0 if auto_entry or not open_ready else 1)
"
    if [[ $? -eq 0 ]]; then
      ok "US stocks prep-status looks ready"
    else
      bad "US stocks prep-status failed"
    fi
  fi

  if curl -fsS -m 20 "$BACKEND/api/health" >/dev/null 2>&1; then
    ok "Backend health"
  else
    bad "Backend health unreachable"
  fi

  fetch_json "$BACKEND/api/status" 120 3 > "$TMP/status.json"
  CHECKLIST_FILE="$TMP/checklist.json" STATUS_FILE="$TMP/status.json" python3 << 'PY'
import json, os, sys
from pathlib import Path

def load(name: str) -> dict:
    path = Path(os.environ[f"{name}_FILE"])
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError:
        return {}

status = load("STATUS")
checklist = load("CHECKLIST")
status_unreachable = not status
deploy = status.get("deploy") or {}
checklist_deploy = checklist.get("deploy") or {}
rev_current = deploy.get("platform_revision_current")
if rev_current is None and status_unreachable:
    rev_current = checklist_deploy.get("platform_revision_current")
errors = []
notes = []

if status_unreachable:
    notes.append("status_endpoint_unreachable")

summaries = status.get("session_open_checklists") or {}
if not summaries.get("us_stocks_open"):
    if status_unreachable and checklist.get("ready") is True:
        notes.append("us_stocks_open_summary_missing")
    else:
        (errors if rev_current is True else notes).append("us_stocks_open_summary_missing")
else:
    us = summaries["us_stocks_open"]
    print(
        f"  status.session_open_checklists.us_stocks_open "
        f"ready={us.get('ready')} open_ready={us.get('open_ready_symbols')}"
    )
    composites = us.get("open_ready_composites") or {}
    if composites:
        print(f"  open_ready_composites={composites}")

open_ready = checklist.get("open_ready") or {}
if checklist and "sticky_symbols" not in open_ready:
    (errors if rev_current is True else notes).append("sticky_symbols_field_missing")

for note in notes:
    print(f"  note={note} (expected until revision deploy)")
if errors:
    print("  errors=" + ",".join(errors))
    sys.exit(1)
sys.exit(0)
PY
  if [[ $? -eq 0 ]]; then
    ok "US stocks status contract"
  else
    bad "US stocks status contract failed"
  fi

  echo ""
  echo "Results: $pass passed, $fail failed, $warn notes"
  [[ "$fail" -eq 0 ]]
  echo ""
  echo "After US stocks open (13:30 UTC Mon):"
  echo "  bash trading-platform/scripts/verify-us-stocks-post-open.sh --watch 120"
}

if [[ -n "$WATCH_INTERVAL" ]]; then
  while true; do
    run_preflight || true
    echo ""
    echo "Watching — next check in ${WATCH_INTERVAL}s (Ctrl+C to stop)"
    sleep "$WATCH_INTERVAL"
    echo ""
  done
else
  run_preflight
fi
