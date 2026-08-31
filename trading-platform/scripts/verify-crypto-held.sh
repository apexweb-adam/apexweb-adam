#!/usr/bin/env bash
# Post-outage verification for crypto held positions (24/7 — no session grace).
# Usage: verify-crypto-held.sh [--watch SECONDS]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/fetch_json.sh
source "$ROOT/scripts/lib/fetch_json.sh"
BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"
CODE_REV="$(grep '^EXPECTED_PLATFORM_REVISION' "$ROOT/backend/app/engines/deploy_status.py" | sed -n 's/.*"\([^"]*\)".*/\1/p')"
WATCH_INTERVAL=""

if [[ "${1:-}" == "--watch" ]]; then
  WATCH_INTERVAL="${2:-90}"
fi

pass=0
fail=0
warn=0

ok() { echo "✓ $*"; pass=$((pass + 1)); }
bad() { echo "✗ $*"; fail=$((fail + 1)); }
note() { echo "○ $*"; warn=$((warn + 1)); }

run_verification() {
  pass=0
  fail=0
  warn=0

  echo "=== Crypto Held-Position Verification — $(date -u '+%Y-%m-%d %H:%M UTC') ==="
  echo "Backend: $BACKEND"
  echo "Expected revision (code): ${CODE_REV:-unknown}"
  echo ""

  if ! check_backend_suspension "$BACKEND"; then
    bad "Backend billing-suspended — crypto held verification unavailable"
    echo ""
    echo "Crypto held: $pass passed, $fail failed, $warn warnings"
    return 2
  fi

  TMP=$(mktemp -d)
  trap 'rm -rf "$TMP"' RETURN
  wake_backend "$BACKEND" 3
  fetch_json "$BACKEND/api/bots/crypto/scan-preview" 120 3 > "$TMP/scan.json"
  fetch_json "$BACKEND/api/status" 120 3 > "$TMP/status.json"
  fetch_json "$BACKEND/api/gate/per-bot" 60 3 > "$TMP/per_bot.json"

  SCAN_FILE="$TMP/scan.json" STATUS_FILE="$TMP/status.json" \
    PER_BOT_FILE="$TMP/per_bot.json" CODE_REV="$CODE_REV" python3 << 'PY'
import json, os, sys
from pathlib import Path

def load(name: str) -> dict:
    path = Path(os.environ[f"{name}_FILE"])
    try:
        return json.loads(path.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError:
        return {}

scan = load("SCAN")
status = load("STATUS")
per_bot = load("PER_BOT")
code_rev = os.environ.get("CODE_REV") or ""

symbols = scan.get("symbols") or []
held = [row["symbol"] for row in symbols if row.get("held")]
would_enter = [row["symbol"] for row in symbols if row.get("would_enter")]

prod_rev = (status.get("deploy") or {}).get("platform_revision")
if prod_rev and code_rev and prod_rev != code_rev:
    print(f"  warn=revision_behind running={prod_rev} expected={code_rev}")

print(f"  crypto_held={held or 'none'} would_enter={would_enter or 'none'}")

outage_events = status.get("platform_outage_events") or []
outage_logged = bool(outage_events)
if outage_logged:
    newest = outage_events[0]
    gap = newest.get("gap_minutes")
    outage_held = [
        row.get("symbol")
        for row in (newest.get("held_open_positions") or [])
        if row.get("bot_type") == "crypto" and row.get("symbol")
    ]
    print(f"  platform_outage_logged gap_min={gap} crypto_held_at_resume={outage_held or 'none'}")

session_events = status.get("session_open_events") or []
recovery_scans = [
    e for e in session_events
    if e.get("event_type") == "outage_recovery_scan" and e.get("bot_type") == "crypto"
]
if recovery_scans:
    latest = recovery_scans[0]
    print(
        f"  outage_recovery_scan symbols={latest.get('symbols')} "
        f"detail={latest.get('detail')}"
    )

crypto_bot = (per_bot.get("bots") or {}).get("crypto") or {}
if crypto_bot:
    print(
        f"  crypto_bot active={crypto_bot.get('active')} "
        f"last_scan={crypto_bot.get('last_scan_at') or crypto_bot.get('last_heartbeat')}"
    )

errors = []
if outage_logged and held and not recovery_scans:
    if prod_rev and code_rev and prod_rev != code_rev:
        print("  warn=deploy_required_for_crypto_outage_recovery")
        errors.append("revision_behind_for_outage_recovery")
    else:
        print("  note=crypto_outage_recovery_pending — held scan expected on post-outage startup")
elif outage_logged and outage_held and not recovery_scans:
    print("  note=crypto_outage_recovery_pending — resume snapshot had crypto held")

if errors:
    print("  errors=" + ",".join(errors))
    sys.exit(1)

if held:
    print("  ok=crypto_held_positions_reported")
elif not outage_logged:
    print("  ok=no_crypto_held_no_outage")
else:
    print("  ok=crypto_outage_recovery_logged_or_clear")
PY

  local py_exit=$?
  if [[ $py_exit -eq 1 ]]; then
    bad "Crypto held verification failed"
  elif [[ $py_exit -eq 0 ]]; then
    ok "Crypto held verification complete"
  fi

  echo ""
  echo "Crypto held: $pass passed, $fail failed, $warn warnings"
  return $((fail > 0 ? 1 : 0))
}

if [[ -n "$WATCH_INTERVAL" ]]; then
  echo "Watching for crypto held recovery (interval ${WATCH_INTERVAL}s)..."
  while true; do
    run_verification || true
    echo ""
    echo "Next check in ${WATCH_INTERVAL}s (Ctrl+C to stop)"
    sleep "$WATCH_INTERVAL"
    echo ""
  done
else
  run_verification
fi
