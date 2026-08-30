#!/usr/bin/env bash
# Warn when GITHUB_TOKEN is missing locally or on Render (non-blocking).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"

SNAPSHOT=$(curl -fsS -m 15 "$BACKEND/api/deploy/snapshot" 2>/dev/null || echo "{}")
SNAPSHOT_JSON="$SNAPSHOT" python3 << 'PY'
import json, os, sys

snap = json.loads(os.environ.get("SNAPSHOT_JSON") or "{}")
configured = snap.get("github_token_configured")
verified = snap.get("github_verified")
if configured is False or verified is False:
    print("WARN: GITHUB_TOKEN missing on Render — deploy staleness checks incomplete")
    print("  Add GITHUB_TOKEN to trading-platform/.env then:")
    print("  bash trading-platform/scripts/sync-render-env.sh")
elif configured is True:
    print("✓ Render GITHUB_TOKEN configured (deploy staleness checks available)")
elif not snap:
    print("○ Could not read deploy snapshot — GITHUB_TOKEN status unknown")
PY

if [[ -f "$ENV_FILE" ]]; then
  if grep -q '^GITHUB_TOKEN=' "$ENV_FILE" 2>/dev/null; then
    echo "✓ Local .env has GITHUB_TOKEN (will sync to Render)"
  else
    echo "WARN: GITHUB_TOKEN missing from $ENV_FILE — sync-render-env.sh will not push it"
  fi
else
  echo "○ Local .env not found — export GITHUB_TOKEN before sync-render-env.sh"
fi
