#!/usr/bin/env bash
# Resilient JSON fetch for deploy scripts (Render cold-start tolerant).
# Usage: source "$(dirname "$0")/lib/fetch_json.sh"
#   body=$(fetch_json "$BACKEND/api/deploy/snapshot" 45 3)
#
# Always returns exit 0 so callers using `set -e` do not abort on empty bodies;
# inspect the returned JSON instead.

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
