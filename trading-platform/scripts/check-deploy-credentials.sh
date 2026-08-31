#!/usr/bin/env bash
# Unified deploy credential check: fomo bearer (blocking) + GITHUB_TOKEN (nudge).
# Usage: check-deploy-credentials.sh [--strict]  # --strict exits 1 when blockers remain
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/fetch_json.sh
source "$ROOT/scripts/lib/fetch_json.sh"
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

SNAPSHOT=$(fetch_json "$BACKEND/api/deploy/snapshot" 45 2)
CODE_REV="$(grep '^EXPECTED_PLATFORM_REVISION' "$ROOT/backend/app/engines/deploy_status.py" | sed -n 's/.*"\([^"]*\)".*/\1/p')"
STRICT_FLAG="$STRICT" SNAPSHOT_JSON="$SNAPSHOT" ENV_FILE="$ENV_FILE" CODE_REV="$CODE_REV" python3 << 'PY'
import json, os, sys

strict = os.environ.get("STRICT_FLAG") == "true"
snap = json.loads(os.environ.get("SNAPSHOT_JSON") or "{}")
env_file = os.environ.get("ENV_FILE") or ""
code_rev = os.environ.get("CODE_REV") or ""

warnings = list(snap.get("deploy_credentials_warnings") or [])
nudges = list(snap.get("deploy_credentials_nudges") or [])

# Normalize pre-r390 snapshots: GITHUB_TOKEN is advisory, not deploy-blocking.
if any("GITHUB_TOKEN" in w for w in warnings):
    warnings = [w for w in warnings if "GITHUB_TOKEN" not in w]
    fallback = "GITHUB_TOKEN missing on Render — deploy staleness checks incomplete"
    if fallback not in nudges:
        nudges.append(fallback)

if snap.get("deploy_credentials_ready") is None:
    if snap.get("fomo_bearer_configured") and snap.get("fomo_bearer_polling_active") is False:
        mins = snap.get("fomo_bearer_minutes_remaining")
        label = f"{mins}min" if mins is not None else "expired"
        warnings.append(f"fomo bearer expired ({label})")

if snap.get("github_token_configured") is False:
    fallback = "GITHUB_TOKEN missing on Render — deploy staleness checks incomplete"
    if fallback not in nudges:
        nudges.append(fallback)

ready = len(warnings) == 0

print("=== Deploy credentials ===")
prod_rev = snap.get("platform_revision") or "?"
if code_rev:
    print(f"revision: production={prod_rev} code_target={code_rev}")
    if prod_rev != code_rev:
        print(f"  → deploy advances {prod_rev} → {code_rev}")
x_mode = snap.get("x_intel_collection_mode")
if x_mode:
    print(f"X intel (production): {x_mode}")
elif code_rev and prod_rev != code_rev:
    print("X intel: google_news_rss activates after deploy (r384+)")

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

learning = snap.get("learning") or {}
content = snap.get("content_study") or {}
if learning:
    print(
        f"learning: analyses={learning.get('trade_analyses')} "
        f"reviews={learning.get('daily_reviews')} "
        f"pending_insights={learning.get('insights_pending')} "
        f"intel_pattern_alerts={learning.get('intel_pattern_count') or 0}"
    )
    for alert in (learning.get("intel_pattern_alerts") or [])[:3]:
        print(f"  intel_alert={alert}")
if content.get("recent") or content.get("insights_applied"):
    print(
        f"content_study: applied={content.get('insights_applied') or 0} "
        f"recent={len(content.get('recent') or [])}"
    )
    for row in (content.get("recent") or [])[:3]:
        label = row.get("source_label") or row.get("source_type") or "unknown"
        title = (row.get("title") or "")[:48]
        state = "applied" if row.get("applied") else "pending"
        print(f"  content_study [{label}] {title} ({state})")

if env_file and os.path.isfile(env_file):
    has_github = False
    local_rev = None
    with open(env_file, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("GITHUB_TOKEN=") and line.strip() != "GITHUB_TOKEN=":
                has_github = True
            if line.startswith("PLATFORM_REVISION="):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                if val:
                    local_rev = val
    if local_rev and code_rev and local_rev != code_rev:
        print(f"local .env: PLATFORM_REVISION={local_rev} (code expects {code_rev})")
        warnings.append(f"local PLATFORM_REVISION stale ({local_rev} vs {code_rev})")
        ready = False
    elif local_rev and code_rev:
        print(f"local .env: PLATFORM_REVISION={local_rev}")
    if has_github:
        print("local .env: GITHUB_TOKEN present")
    else:
        print("local .env: GITHUB_TOKEN missing — optional for deploy; enables staleness checks")
        nudge = "GITHUB_TOKEN missing from local .env"
        if nudge not in nudges:
            nudges.append(nudge)
else:
    print("local .env: not found")

if ready:
    print("✓ Deploy credentials OK (no blocking issues)")
    if nudges:
        print("Nudges (non-blocking):")
        for item in nudges:
            print(f"  ○ {item}")
else:
    print("")
    print("ACTION REQUIRED before deploy:")
    for item in warnings:
        print(f"  - {item}")
    hint = snap.get("fomo_bearer_refresh_hint")
    if hint and any("fomo" in w for w in warnings):
        print(f"  fomo refresh: {hint}")
    if nudges:
        print("Nudges (non-blocking):")
        for item in nudges:
            print(f"  ○ {item}")
    if strict:
        sys.exit(1)
PY
CRED_EXIT=$?

if ! echo "$SNAPSHOT" | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('fomo_bearer_configured') is not None else 1)" 2>/dev/null; then
  echo ""
  bash "$ROOT/scripts/check-fomo-bearer.sh" || true
fi
if ! echo "$SNAPSHOT" | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('github_token_configured') is not None else 1)" 2>/dev/null; then
  bash "$ROOT/scripts/check-github-token.sh" || true
fi

exit "$CRED_EXIT"
