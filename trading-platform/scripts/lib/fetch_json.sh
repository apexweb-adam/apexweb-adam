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
      echo "  After restore: bash trading-platform/scripts/wait-for-render-deploy.sh --verify"
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
