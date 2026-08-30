#!/usr/bin/env bash
# One-screen operator summary before/after deploy window actions.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIB="$ROOT/scripts/lib/deploy_json.py"
BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"
CODE_REV="$(grep '^EXPECTED_PLATFORM_REVISION' "$ROOT/backend/app/engines/deploy_status.py" | sed -n 's/.*"\([^"]*\)".*/\1/p')"

SNAPSHOT=$(curl -fsS -m 20 "$BACKEND/api/deploy/snapshot" 2>/dev/null || echo "{}")
CME=$(curl -fsS -m 45 "$BACKEND/api/gate/cme-reopen-checklist" 2>/dev/null || echo "{}")
INTEL_SOURCES=$(curl -fsS -m 25 "$BACKEND/api/intelligence/sources" 2>/dev/null || echo "[]")
BASELINE=""
if [[ -f "$ROOT/.crm-load-baseline" ]]; then
  BASELINE=$(tr -d '[:space:]' < "$ROOT/.crm-load-baseline")
fi

CODE_REV="$CODE_REV" BASELINE="$BASELINE" SNAPSHOT_JSON="$SNAPSHOT" CME_JSON="$CME" INTEL_JSON="$INTEL_SOURCES" LIB="$LIB" python3 << 'PY'
import json, os, subprocess, sys
from pathlib import Path

code_rev = os.environ.get("CODE_REV") or "?"
baseline = os.environ.get("BASELINE") or ""
snap = json.loads(os.environ.get("SNAPSHOT_JSON") or "{}")
cme = json.loads(os.environ.get("CME_JSON") or "{}")
intel_raw = os.environ.get("INTEL_JSON") or "[]"
lib = os.environ.get("LIB") or ""

print("=== Deploy Window Operator Summary ===")
prod_rev = snap.get("platform_revision") or "?"
snap_expected = snap.get("expected_platform_revision")
print(f"Code target: {code_rev}")
print(f"Production: {prod_rev}")
if prod_rev != code_rev:
    print(f"  → deploy advances {prod_rev} → {code_rev}")
if snap_expected and snap_expected != code_rev:
    print(f"  note: production snapshot still expects {snap_expected} until deploy")

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
nudge = snap.get("fomo_bearer_nudge_message")
nudge_tier = snap.get("fomo_bearer_nudge_tier")
if ready is True:
    print("Credentials: ready")
    if nudge and nudge_tier in ("60", "15"):
        print(f"  note: {nudge}")
elif warnings:
    print("Credentials: ACTION REQUIRED")
    for item in warnings:
        print(f"  - {item}")
    if nudge and nudge_tier == "expired":
        print(f"  note: {nudge}")
else:
    print("Credentials: check bash trading-platform/scripts/check-deploy-credentials.sh")
    if nudge:
        print(f"  note: {nudge}")

x_mode = snap.get("x_intel_collection_mode")
if x_mode:
    print(f"X intel (snapshot): {x_mode}")
elif lib and Path(lib).is_file():
    tmp_sources = Path("/tmp") / f"apex-intel-sources-{os.getpid()}.json"
    tmp_snap = Path("/tmp") / f"apex-intel-snap-{os.getpid()}.json"
    tmp_sources.write_text(intel_raw, encoding="utf-8")
    tmp_snap.write_text(json.dumps(snap), encoding="utf-8")
    try:
        proc = subprocess.run(
            [
                sys.executable,
                lib,
                "intel-readiness",
                "--sources-file",
                str(tmp_sources),
                "--snapshot-file",
                str(tmp_snap),
                "--prod-rev",
                str(prod_rev),
                "--code-rev",
                code_rev,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        intel_status = (proc.stdout or "").strip() or "missing"
    finally:
        tmp_sources.unlink(missing_ok=True)
        tmp_snap.unlink(missing_ok=True)
    if intel_status == "ok":
        print("Intel: source health + snapshot fields live (r385+)")
    elif intel_status == "partial":
        print("Intel: sources API ready — snapshot r385 fields after deploy")
    else:
        print("Intel: r385 fields pending — confirm after deploy")

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
