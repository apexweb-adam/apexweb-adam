#!/usr/bin/env bash
# Warn when fomo.family bearer is expired or polling inactive (non-blocking).
set -euo pipefail

BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"
SNAPSHOT=$(curl -fsS -m 15 "$BACKEND/api/deploy/snapshot" 2>/dev/null || echo "{}")
STATUS=$(curl -fsS -m 20 "$BACKEND/api/status" 2>/dev/null || echo "{}")

SNAPSHOT_JSON="$SNAPSHOT" STATUS_JSON="$STATUS" python3 << 'PY'
import json, os, sys

snap = json.loads(os.environ.get("SNAPSHOT_JSON") or "{}")
status = json.loads(os.environ.get("STATUS_JSON") or "{}")
integrations = status.get("integrations") or {}

configured = snap.get("fomo_bearer_configured")
polling = snap.get("fomo_bearer_polling_active")
mins = snap.get("fomo_bearer_minutes_remaining")
hint = snap.get("fomo_bearer_refresh_hint")

if configured is None:
    configured = integrations.get("fomo_bearer_configured")
if polling is None:
    polling = integrations.get("fomo_bearer_polling_active")
if mins is None:
    mins = integrations.get("fomo_bearer_minutes_remaining")
if not hint:
    hint = integrations.get("fomo_bearer_refresh_hint") or (
        "bash trading-platform/scripts/fomo-set-bearer.sh '<bearer>'"
    )

if not configured:
    print("○ fomo bearer not configured — server-side memecoin poll disabled (webhook/userscript still work)")
    sys.exit(0)

if polling:
    label = f"{mins}min remaining" if mins is not None else "active"
    print(f"✓ fomo bearer polling active ({label})")
    sys.exit(0)

if mins is not None and int(mins) < 0:
    print(f"WARN: fomo bearer expired ({mins}min) — crypto intel source 'fomo' is degraded")
    print(f"  Refresh: {hint}")
    print("  Or: keep fomo.family open with trading-platform/scripts/fomo-family-bridge.user.js")
    sys.exit(0)

print("WARN: fomo bearer configured but polling inactive — memecoin intel may be stale")
print(f"  Refresh: {hint}")
PY
