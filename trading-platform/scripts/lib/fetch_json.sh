#!/usr/bin/env bash
# Resilient JSON fetch for deploy scripts (Render cold-start tolerant).
# Usage: source "$(dirname "$0")/lib/fetch_json.sh"
#   body=$(fetch_json "$BACKEND/api/deploy/snapshot" 45 2)

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
      sleep 2
    fi
  done

  echo "{}"
  return 1
}
