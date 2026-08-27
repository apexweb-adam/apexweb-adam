#!/usr/bin/env bash
# Detect Cloudflare tunnel URL and update Vercel BACKEND_URL / BACKEND_WS_URL.
# Requires VERCEL_TOKEN (https://vercel.com/account/tokens) and optional:
#   VERCEL_PROJECT=apex-trading-dashboard
#   VERCEL_TEAM=apexweb-adams-projects
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROJECT="${VERCEL_PROJECT:-apex-trading-dashboard}"
TEAM="${VERCEL_TEAM:-apexweb-adams-projects}"

detect_tunnel_url() {
  if [[ -n "${TUNNEL_URL:-}" ]]; then
    echo "${TUNNEL_URL%/}"
    return 0
  fi
  local log
  for log in /tmp/cloudflared.log "$ROOT/.tunnel-url"; do
    if [[ -f "$log" ]]; then
      local url
      url=$(rg -o 'https://[a-z0-9-]+\.trycloudflare\.com' "$log" 2>/dev/null | tail -1 || true)
      if [[ -n "$url" ]]; then
        echo "$url"
        return 0
      fi
    fi
  done
  echo "Could not detect tunnel URL. Set TUNNEL_URL or run cloudflared with log." >&2
  return 1
}

BACKEND_URL="$(detect_tunnel_url)"
WS_URL="${BACKEND_URL/https:\/\//wss://}"

echo "Backend: $BACKEND_URL"
echo "WebSocket: $WS_URL"

# Always update local vercel.json for git-tracked interim deploys
python3 - "$ROOT/vercel.json" "$ROOT/dashboard/vercel.json" "$BACKEND_URL" "$WS_URL" <<'PY'
import json, sys
paths, api, ws = sys.argv[1:-2], sys.argv[-2], sys.argv[-1]
for path in paths:
    try:
        with open(path) as f:
            cfg = json.load(f)
    except FileNotFoundError:
        continue
    cfg.setdefault("env", {})
    cfg["env"]["BACKEND_URL"] = api
    cfg["env"]["BACKEND_WS_URL"] = ws
    with open(path, "w") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
    print(f"Updated {path}")
PY

if [[ -z "${VERCEL_TOKEN:-}" ]]; then
  echo ""
  echo "Set VERCEL_TOKEN to push env vars to Vercel without redeploying from git."
  echo "Manual: Vercel → $PROJECT → Settings → Environment Variables"
  echo "  BACKEND_URL=$BACKEND_URL"
  echo "  BACKEND_WS_URL=$WS_URL"
  exit 0
fi

patch_env() {
  local key="$1" value="$2"
  curl -fsS -X POST "https://api.vercel.com/v10/projects/$PROJECT/env?teamId=$TEAM" \
    -H "Authorization: Bearer $VERCEL_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"key\":\"$key\",\"value\":\"$value\",\"type\":\"encrypted\",\"target\":[\"production\"]}" \
    >/dev/null 2>&1 || \
  curl -fsS -X PATCH "https://api.vercel.com/v1/projects/$PROJECT/env" \
    -H "Authorization: Bearer $VERCEL_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"key\":\"$key\",\"value\":\"$value\",\"target\":[\"production\"]}" \
    >/dev/null 2>&1 || true
  echo "Set Vercel env: $key"
}

patch_env "BACKEND_URL" "$BACKEND_URL"
patch_env "BACKEND_WS_URL" "$WS_URL"

echo ""
echo "Done. Production dashboard should use runtime proxy within ~1 min after redeploy."
