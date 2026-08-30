#!/usr/bin/env bash
# One-screen operator summary before/after deploy window actions.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"
CODE_REV="$(grep '^EXPECTED_PLATFORM_REVISION' "$ROOT/backend/app/engines/deploy_status.py" | sed -n 's/.*"\([^"]*\)".*/\1/p')"

SNAPSHOT=$(curl -fsS -m 20 "$BACKEND/api/deploy/snapshot" 2>/dev/null || echo "{}")
CME=$(curl -fsS -m 45 "$BACKEND/api/gate/cme-reopen-checklist" 2>/dev/null || echo "{}")
BASELINE=""
if [[ -f "$ROOT/.crm-load-baseline" ]]; then
  BASELINE=$(tr -d '[:space:]' < "$ROOT/.crm-load-baseline")
fi

CODE_REV="$CODE_REV" BASELINE="$BASELINE" SNAPSHOT_JSON="$SNAPSHOT" CME_JSON="$CME" python3 << 'PY'
import json, os

code_rev = os.environ.get("CODE_REV") or "?"
baseline = os.environ.get("BASELINE") or ""
snap = json.loads(os.environ.get("SNAPSHOT_JSON") or "{}")
cme = json.loads(os.environ.get("CME_JSON") or "{}")

print("=== Deploy Window Operator Summary ===")
prod_rev = snap.get("platform_revision") or "?"
exp_rev = snap.get("expected_platform_revision") or code_rev
print(f"Code target: {code_rev}")
print(f"Production: {prod_rev} (snapshot expected {exp_rev})")
if prod_rev != code_rev:
    print(f"  → deploy advances {prod_rev} → {code_rev}")

window = snap.get("cme_deploy_window") or {}
if window.get("message"):
    label = "ACTIVE" if window.get("in_window") else "pending"
    print(f"CME deploy window ({label}): {window.get('message')}")

open_ready = (cme.get("open_ready") or {}).get("symbols") or []
auto_entry = (cme.get("open_ready") or {}).get("auto_entry_queued")
mins = cme.get("minutes_until_open")
if open_ready or mins is not None:
    print(
        f"CME reopen: open_ready={open_ready or 'none'} "
        f"auto_entry={auto_entry} open_in={mins}min"
    )

ready = snap.get("deploy_credentials_ready")
warnings = snap.get("deploy_credentials_warnings") or []
if ready is True:
    print("Credentials: ready")
elif warnings:
    print("Credentials: ACTION REQUIRED")
    for item in warnings:
        print(f"  - {item}")
else:
    print("Credentials: check bash trading-platform/scripts/check-deploy-credentials.sh")

if baseline:
    print(f"CRM baseline: {baseline}s (target <30s after deploy)")

print("")
print("Deploy:")
print("  bash trading-platform/scripts/run-deploy-window.sh")
print("After CME open (22:00 UTC):")
print("  bash trading-platform/scripts/verify-cme-post-open.sh")
print("Monday US open (13:30 UTC):")
print("  bash trading-platform/scripts/verify-us-stocks-open.sh --watch 120")
PY
