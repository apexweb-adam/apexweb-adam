#!/usr/bin/env bash
# One-screen operator summary before/after deploy window actions.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIB="$ROOT/scripts/lib/deploy_json.py"
# shellcheck source=lib/fetch_json.sh
source "$ROOT/scripts/lib/fetch_json.sh"
BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"
CODE_REV="$(grep '^EXPECTED_PLATFORM_REVISION' "$ROOT/backend/app/engines/deploy_status.py" | sed -n 's/.*"\([^"]*\)".*/\1/p')"

SNAPSHOT=$(fetch_json "$BACKEND/api/deploy/snapshot" 45 2)
CME=$(fetch_json "$BACKEND/api/gate/cme-reopen-checklist" 60 2)
US_CHECKLIST=$(fetch_json "$BACKEND/api/gate/us-stocks-open-checklist" 45 2)
INTEL_SOURCES=$(fetch_json "$BACKEND/api/intelligence/sources" 30 2)
PREP_STATUS=$(fetch_json "$BACKEND/api/gate/prep-status" 45 2)
BASELINE=""
if [[ -f "$ROOT/.crm-load-baseline" ]]; then
  BASELINE=$(tr -d '[:space:]' < "$ROOT/.crm-load-baseline")
fi

CODE_REV="$CODE_REV" BASELINE="$BASELINE" SNAPSHOT_JSON="$SNAPSHOT" CME_JSON="$CME" US_JSON="$US_CHECKLIST" INTEL_JSON="$INTEL_SOURCES" PREP_JSON="$PREP_STATUS" LIB="$LIB" python3 << 'PY'
import json, os, subprocess, sys
from pathlib import Path

code_rev = os.environ.get("CODE_REV") or "?"
baseline = os.environ.get("BASELINE") or ""
snap = json.loads(os.environ.get("SNAPSHOT_JSON") or "{}")
cme = json.loads(os.environ.get("CME_JSON") or "{}")
us = json.loads(os.environ.get("US_JSON") or "{}")
prep = json.loads(os.environ.get("PREP_JSON") or "{}")
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

open_ready_block = cme.get("open_ready") or {}
open_ready = open_ready_block.get("symbols") or []
sticky = open_ready_block.get("sticky_symbols") or []
auto_entry = open_ready_block.get("auto_entry_queued")
release_margin = open_ready_block.get("release_margin")
mins = cme.get("minutes_until_open")
near_block = cme.get("near_floor") or {}
near_symbols = near_block.get("symbols") or []
if open_ready or sticky or near_symbols or mins is not None:
    parts = [f"CME reopen: open_ready={open_ready or 'none'}"]
    if sticky:
        parts.append(f"sticky={sticky}")
    if near_symbols:
        parts.append(f"near_floor={near_symbols}")
    parts.append(f"auto_entry={auto_entry}")
    if release_margin is not None:
        parts.append(f"release_margin={release_margin}")
    if mins is not None:
        parts.append(f"open_in={mins}min")
    print(" ".join(parts))
    for row in near_block.get("details") or []:
        sym = row.get("symbol")
        comp = row.get("composite")
        gap = row.get("gap_to_floor")
        if sym and gap is not None:
            print(f"  near_floor {sym}: composite={comp} need +{gap}")
    for row in open_ready_block.get("details") or []:
        sym = row.get("symbol")
        comp = row.get("composite")
        blockers = row.get("blockers") or []
        sticky_flag = " sticky" if row.get("sticky_queue") else ""
        if sym:
            print(f"  open_ready {sym}: composite={comp}{sticky_flag} blockers={blockers}")
    if near_symbols and not open_ready and auto_entry is False:
        print(
            "  warn: near_floor without open_ready — queue dropped; "
            "confirm 6h prep watch is refreshing TV signals"
        )

comm_prep = prep.get("commodities") or {}
if comm_prep.get("prep_active"):
    window = comm_prep.get("prep_window_minutes")
    phase = comm_prep.get("prep_phase")
    label = f"prep_active phase={phase}"
    if window is not None:
        hours = int(window) // 60
        label += f" window={hours}h" if hours >= 1 else f" window={window}min"
    if comm_prep.get("gate_reopen_imminent"):
        label += " fast_scan=5s"
    print(f"CME prep watch: {label}")

if us:
    checks = {c.get("id"): c for c in us.get("checks") or []}
    stocks = checks.get("stocks_active") or {}
    us_open = (us.get("open_ready") or {}).get("symbols") or []
    us_sticky = (us.get("open_ready") or {}).get("sticky_symbols") or []
    us_mins = us.get("minutes_until_open")
    if stocks.get("status") == "fail":
        syms = ", ".join(us_open) if us_open else "none"
        print(
            f"US stocks: bot paused — Monday auto-entry for {syms} "
            f"blocked until profitability gate clears "
            f"(open in {us_mins}min)"
        )
    elif us_open or us_sticky:
        parts = [f"US stocks: open_ready={us_open or 'none'}"]
        if us_sticky:
            parts.append(f"sticky={us_sticky}")
        if us_mins is not None:
            parts.append(f"open_in={us_mins}min")
        print(" ".join(parts))

ready = snap.get("deploy_credentials_ready")
warnings = snap.get("deploy_credentials_warnings") or []
nudges = snap.get("deploy_credentials_nudges") or []
nudge = snap.get("fomo_bearer_nudge_message")
nudge_tier = snap.get("fomo_bearer_nudge_tier")
if ready is True:
    print("Credentials: ready")
    for item in nudges:
        print(f"  nudge: {item}")
    if nudge and nudge_tier in ("60", "15"):
        print(f"  note: {nudge}")
elif warnings:
    print("Credentials: ACTION REQUIRED")
    for item in warnings:
        print(f"  - {item}")
    for item in nudges:
        print(f"  nudge: {item}")
    if nudge and nudge_tier == "expired":
        print(f"  note: {nudge}")
else:
    print("Credentials: check bash trading-platform/scripts/check-deploy-credentials.sh")
    for item in nudges:
        print(f"  nudge: {item}")
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
print("  bash trading-platform/scripts/verify-cme-post-open.sh --watch 120")
print("Monday US open (13:30 UTC):")
print("  bash trading-platform/scripts/verify-us-stocks-open.sh --watch 120")
PY
