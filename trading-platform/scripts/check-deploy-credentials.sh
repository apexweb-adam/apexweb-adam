#!/usr/bin/env bash
# Unified deploy credential check: fomo bearer + GITHUB_TOKEN (non-blocking by default).
# Usage: check-deploy-credentials.sh [--strict]  # --strict exits 1 when not ready
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
STRICT=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --strict)
      STRICT=true
      shift
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

SNAPSHOT=$(curl -fsS -m 15 "$BACKEND/api/deploy/snapshot" 2>/dev/null || echo "{}")
STRICT_FLAG="$STRICT" SNAPSHOT_JSON="$SNAPSHOT" ENV_FILE="$ENV_FILE" python3 << 'PY'
import json, os, sys

strict = os.environ.get("STRICT_FLAG") == "true"
snap = json.loads(os.environ.get("SNAPSHOT_JSON") or "{}")
env_file = os.environ.get("ENV_FILE") or ""

warnings = list(snap.get("deploy_credentials_warnings") or [])
ready = snap.get("deploy_credentials_ready")

if ready is None:
    if snap.get("github_token_configured") is False:
        warnings.append("GITHUB_TOKEN missing on Render")
    if snap.get("fomo_bearer_configured") and snap.get("fomo_bearer_polling_active") is False:
        mins = snap.get("fomo_bearer_minutes_remaining")
        label = f"{mins}min" if mins is not None else "expired"
        warnings.append(f"fomo bearer expired ({label})")
    ready = len(warnings) == 0

print("=== Deploy credentials ===")
if snap.get("fomo_bearer_configured") is not None:
    mins = snap.get("fomo_bearer_minutes_remaining")
    tier = snap.get("fomo_bearer_nudge_tier")
    nudge = snap.get("fomo_bearer_nudge_message")
    print(
        f"fomo: configured={snap.get('fomo_bearer_configured')} "
        f"polling={snap.get('fomo_bearer_polling_active')} mins={mins}"
    )
    if nudge:
        print(f"  nudge ({tier}): {nudge}")
else:
    print("fomo: (snapshot pre-r371 — run check-fomo-bearer.sh)")

if snap.get("github_token_configured") is not None:
    print(f"github: token_configured={snap.get('github_token_configured')}")
else:
    print("github: (snapshot pre-r370 — run check-github-token.sh)")

if env_file and os.path.isfile(env_file):
    has_github = False
    with open(env_file, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("GITHUB_TOKEN=") and line.strip() != "GITHUB_TOKEN=":
                has_github = True
                break
    if has_github:
        print("local .env: GITHUB_TOKEN present")
    else:
        print("local .env: GITHUB_TOKEN missing — sync-render-env.sh will not push it")
        if "GITHUB_TOKEN missing" not in " ".join(warnings):
            warnings.append("GITHUB_TOKEN missing from local .env")
        ready = False
else:
    print("local .env: not found")

if ready:
    print("✓ Deploy credentials OK")
else:
    print("")
    print("ACTION REQUIRED before deploy:")
    for item in warnings:
        print(f"  - {item}")
    hint = snap.get("fomo_bearer_refresh_hint")
    if hint and any("fomo" in w for w in warnings):
        print(f"  fomo refresh: {hint}")
    if any("GITHUB" in w for w in warnings):
        print("  github: add GITHUB_TOKEN to .env then bash trading-platform/scripts/sync-render-env.sh")
    if strict:
        sys.exit(1)
PY
CRED_EXIT=$?

# Backward compat when production is pre-r371/r370 snapshot fields.
if ! echo "$SNAPSHOT" | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('fomo_bearer_configured') is not None else 1)" 2>/dev/null; then
  echo ""
  bash "$ROOT/scripts/check-fomo-bearer.sh" || true
fi
if ! echo "$SNAPSHOT" | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('github_token_configured') is not None else 1)" 2>/dev/null; then
  bash "$ROOT/scripts/check-github-token.sh" || true
fi

exit "$CRED_EXIT"
