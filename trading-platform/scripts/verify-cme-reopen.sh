#!/usr/bin/env bash
# Preflight checks before CME Sunday reopen (22:00 UTC) and Monday US open.
set -euo pipefail

BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"
EXPECTED_REVISION="${EXPECTED_PLATFORM_REVISION:-2026-08-29-r339}"

pass=0
fail=0
warn=0

ok() { echo "✓ $*"; pass=$((pass + 1)); }
bad() { echo "✗ $*"; fail=$((fail + 1)); }
note() { echo "○ $*"; warn=$((warn + 1)); }

echo "=== CME Reopen Preflight — $(date -u '+%Y-%m-%d %H:%M UTC') ==="
echo "Backend: $BACKEND"
echo "Expected revision (code): $EXPECTED_REVISION"
echo ""

PREP=$(curl -fsS -m 45 "$BACKEND/api/gate/prep-status" 2>/dev/null || echo "{}")
STATUS=$(curl -fsS -m 90 "$BACKEND/api/status" 2>/dev/null || echo "{}")

python3 << PY
import json, sys

prep = json.loads('''$PREP''')
status = json.loads('''$STATUS''')
dep = (status.get("deploy") or {})
rev = dep.get("platform_revision") or "?"
expected = "$EXPECTED_REVISION"
current = dep.get("platform_revision_current")

print(f"  platform_revision={rev} current={current} expected={expected}")
if rev != expected:
    print(f"  deploy_note=Render behind code — run TRIGGER_DEPLOY=true bash trading-platform/scripts/sync-render-env.sh")
else:
    print(f"  deploy_note=revision matches expected")

comm = prep.get("commodities") or {}
cme = (prep.get("next_session_events") or {}).get("cme_reopen") or (status.get("next_session_events") or {}).get("cme_reopen") or {}
mins = comm.get("minutes_until_open") or cme.get("minutes_until_open")
phase = comm.get("prep_phase") or cme.get("prep_phase")
open_ready = comm.get("open_ready_symbols") or cme.get("open_ready_symbols") or []
auto_entry = comm.get("auto_entry_queued") or cme.get("auto_entry_queued")
floor = comm.get("composite_floor") or cme.get("composite_floor")
details = comm.get("open_ready_details") or cme.get("open_ready_details") or []

print(f"  cme_phase={phase} minutes_until_open={mins}")
print(f"  auto_entry_queued={auto_entry} composite_floor={floor}")
print(f"  open_ready={open_ready}")

for row in details:
    sym = row.get("symbol")
    comp = row.get("composite")
    blockers = row.get("blockers") or []
    ready = row.get("monday_gate_skip_ready")
    print(f"    {sym}: composite={comp} gate_skip_ready={ready} blockers={blockers}")

us = prep.get("stocks_futures") or {}
us_evt = (prep.get("next_session_events") or {}).get("us_stocks_open") or {}
us_mins = us.get("minutes_until_open") or us_evt.get("minutes_until_open")
us_ready = us.get("open_ready_symbols") or us_evt.get("open_ready_symbols") or []
print(f"  us_stocks_minutes_until_open={us_mins} open_ready={us_ready}")

events = status.get("session_open_events") or []
queue_events = [e for e in events if e.get("event_type") in ("queue_add", "prep_phase", "burst_scan", "auto_entry")]
print(f"  session_open_events={len(events)} recent_actionable={len(queue_events[:5])}")
for e in queue_events[:5]:
    print(f"    {e.get('event_type')} {e.get('bot_type')} {e.get('symbols')} {str(e.get('detail') or '')[:60]}")

fomo = (status.get("integrations") or {})
if fomo.get("fomo_bearer_configured"):
    active = fomo.get("fomo_bearer_polling_active")
    mins_left = fomo.get("fomo_bearer_minutes_remaining")
    print(f"  fomo_bearer polling_active={active} minutes_remaining={mins_left}")

# Exit codes for shell checks
errors = []
if not comm and not cme:
    errors.append("missing_cme_prep")
if mins is None:
    errors.append("missing_minutes_until_open")
if phase not in ("extended", "imminent", "wake", "open"):
    errors.append("unexpected_prep_phase")
if not open_ready and mins is not None and mins < 120:
    note = "no open_ready symbols within 2h of CME — auto-entry may not fire"
    print(f"  warn={note}")
if auto_entry is not True and open_ready:
    errors.append("auto_entry_not_queued_despite_open_ready")

gate = (status.get("per_bot_gate") or {}).get("commodities") or {}
if gate.get("paused") is True:
    errors.append("commodities_bot_paused")

if errors:
    print("  errors=" + ",".join(errors))
    sys.exit(1)
sys.exit(0)
PY

if [[ $? -eq 0 ]]; then
  ok "CME prep-status looks ready for reopen"
else
  bad "CME prep-status failed preflight (see details above)"
fi

# Health + bots running
if curl -fsS -m 20 "$BACKEND/api/health" >/dev/null 2>&1; then
  ok "Backend health"
else
  bad "Backend health unreachable"
fi

python3 << PY
import json, sys
d = json.loads('''$STATUS''')
bots = d.get("bots") or []
running = [b.get("bot_type") for b in bots if b.get("status") == "running"]
if len(running) >= 3:
    print(f"  running={running}")
    sys.exit(0)
print(f"  running={running}")
sys.exit(1)
PY
if [[ $? -eq 0 ]]; then
  ok "Bots running"
else
  bad "Not all bots running"
fi

echo ""
echo "Results: $pass passed, $fail failed, $warn notes"
if [[ "$fail" -gt 0 ]]; then
  echo ""
  echo "Deploy r337+ before CME if revision is behind:"
  echo "  TRIGGER_DEPLOY=true bash trading-platform/scripts/sync-render-env.sh"
  exit 1
fi
