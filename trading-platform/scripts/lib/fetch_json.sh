#!/usr/bin/env bash
# Resilient JSON fetch for deploy scripts (Render cold-start tolerant).
# Usage: source "$(dirname "$0")/lib/fetch_json.sh"
#   body=$(fetch_json "$BACKEND/api/deploy/snapshot" 45 3)
#
# Always returns exit 0 so callers using `set -e` do not abort on empty bodies;
# inspect the returned JSON instead.

RENDER_SERVICE_ID="${RENDER_SERVICE_ID:-srv-da848ms9v7es739k38jg}"
RENDER_DASHBOARD_URL="${RENDER_DASHBOARD_URL:-https://dashboard.render.com/web/srv-da848ms9v7es739k38jg}"

# Detect Render billing suspension (503 HTML) or API-reported suspenders.
# Prints actionable recovery steps to stderr; returns 0 when online, 1 when suspended.
check_backend_suspension() {
  local base="${1%/}"
  local health_url="$base/api/health"
  local body http_code

  body=$(curl -sS -m 20 -w "\n%{http_code}" "$health_url" 2>/dev/null || true)
  http_code="${body##*$'\n'}"
  body="${body%$'\n'*}"

  local is_suspended=false
  local suspenders=""

  if [[ "$http_code" == "503" && "$body" == *"Service Suspended"* ]]; then
    is_suspended=true
    suspenders="billing"
  fi

  if [[ -n "${RENDER_API_KEY:-}" ]]; then
    local api_json suspended api_suspenders
    api_json=$(curl -sS -m 15 \
      -H "Authorization: Bearer $RENDER_API_KEY" \
      "https://api.render.com/v1/services/${RENDER_SERVICE_ID}" 2>/dev/null || true)
    suspended=$(echo "$api_json" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('suspended',''))" 2>/dev/null || true)
    api_suspenders=$(echo "$api_json" | python3 -c "import json,sys; d=json.load(sys.stdin); print(','.join(d.get('suspenders') or []))" 2>/dev/null || true)
    if [[ "$suspended" == "suspended" ]]; then
      is_suspended=true
      suspenders="${api_suspenders:-suspended}"
    fi
  fi

  if [[ "$is_suspended" != true ]]; then
    return 0
  fi

  if [[ "$suspenders" == *"billing"* ]]; then
    {
      echo "✗ Render backend suspended by billing — API resume/deploy will not work."
      echo "  Dashboard: $RENDER_DASHBOARD_URL"
      echo "  Fix: add a payment method and/or upgrade from free tier, then resume the service."
      echo "  After restore: bash trading-platform/scripts/recover-render-billing.sh"
    } >&2
  else
    {
      echo "✗ Backend service suspended on Render (suspenders: ${suspenders:-unknown})."
      echo "  Dashboard: $RENDER_DASHBOARD_URL"
      echo "  Resume the service in Render, then re-run this script."
    } >&2
  fi
  return 1
}

# Exit 2 when backend is billing-suspended; safe to call before fetch_json loops.
require_backend_online() {
  local base="${1%/}"
  if ! check_backend_suspension "$base"; then
    exit 2
  fi
}

wake_backend() {
  local base="${1%/}"
  local attempts="${2:-3}"
  local attempt url body

  for ((attempt = 1; attempt <= attempts; attempt++)); do
    for url in \
      "$base/api/gate/prep-status" \
      "$base/api/health" \
      "$base/api/deploy/snapshot"; do
      body=$(curl -fsS -m 20 "$url" 2>/dev/null || true)
      if [[ -n "$body" && "$body" != "{}" ]]; then
        return 0
      fi
    done
    if [[ "$attempt" -lt "$attempts" ]]; then
      sleep $((attempt * 2))
    fi
  done

  return 0
}

fetch_json() {
  local url="$1"
  local timeout="${2:-45}"
  local attempts="${3:-2}"
  local attempt body

  for ((attempt = 1; attempt <= attempts; attempt++)); do
    body=$(curl -fsS -m "$timeout" "$url" 2>/dev/null || true)
    if [[ -n "$body" && "$body" != "{}" ]]; then
      echo "$body"
      return 0
    fi
    if [[ "$attempt" -lt "$attempts" ]]; then
      sleep $((attempt * 2))
    fi
  done

  echo "{}"
  return 0
}

# Print production platform_revision from deploy snapshot (empty if unknown).
production_platform_revision() {
  local base="${1%/}"
  local snapshot
  snapshot=$(fetch_json "$base/api/deploy/snapshot" 60 3)
  SNAPSHOT="$snapshot" python3 << 'PY'
import json, os
snap = json.loads(os.environ.get("SNAPSHOT") or "{}")
print(snap.get("platform_revision") or "")
PY
}

# Return 0 when production revision is behind EXPECTED_PLATFORM_REVISION in code.
production_revision_behind() {
  local base="${1%/}"
  local expected="${2:-}"
  if [[ -z "$expected" ]]; then
    return 1
  fi
  local snapshot
  snapshot=$(fetch_json "$base/api/deploy/snapshot" 60 3)
  SNAPSHOT="$snapshot" EXPECTED="$expected" python3 << 'PY'
import json, os, sys
snap = json.loads(os.environ.get("SNAPSHOT") or "{}")
expected = os.environ.get("EXPECTED") or ""
rev = snap.get("platform_revision") or ""
if snap.get("platform_revision_current") is True or rev == expected:
    sys.exit(1)
sys.exit(0)
PY
}

# Trigger Render deploy via API or deploy hook. Returns 0 on success.
trigger_render_deploy() {
  if [[ -n "${RENDER_API_KEY:-}" ]]; then
    local http
    http=$(curl -sS -o /tmp/render-deploy-resp.json -w "%{http_code}" -X POST \
      -H "Authorization: Bearer $RENDER_API_KEY" \
      -H "Content-Type: application/json" \
      -d '{"clearCache":"clear"}' \
      "https://api.render.com/v1/services/${RENDER_SERVICE_ID}/deploys" 2>/dev/null || echo "000")
    if [[ "$http" =~ ^(200|201|202)$ ]]; then
      echo "✓ Render deploy triggered via API (HTTP $http)"
      return 0
    fi
    echo "✗ Render deploy API failed (HTTP $http)" >&2
    [[ -f /tmp/render-deploy-resp.json ]] && cat /tmp/render-deploy-resp.json >&2 || true
    return 1
  fi
  if [[ -n "${RENDER_DEPLOY_HOOK:-}" ]]; then
    curl -fsS -X POST "$RENDER_DEPLOY_HOOK" >/dev/null
    echo "✓ Render deploy triggered via deploy hook"
    return 0
  fi
  echo "○ No RENDER_API_KEY or RENDER_DEPLOY_HOOK — cannot auto-trigger deploy" >&2
  return 1
}
