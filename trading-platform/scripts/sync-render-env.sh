#!/usr/bin/env bash
# Push environment variables from local .env (and optional DATABASE_URL) to Render via API.
# Requires RENDER_API_KEY in env or Cursor secrets.
set -euo pipefail

SERVICE_ID="${RENDER_SERVICE_ID:-srv-da848ms9v7es739k38jg}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"

if [[ -z "${RENDER_API_KEY:-}" ]]; then
  echo "Set RENDER_API_KEY (Cursor secrets or export)" >&2
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE" >&2
  exit 1
fi

# Keys synced from .env; DATABASE_URL can also come from env for CI/secrets injection.
SYNC_KEYS=(
  DATABASE_URL
  PAPER_TRADING_ONLY
  INITIAL_BALANCE
  CORS_ORIGINS
  NEWSAPI_KEY
  TWITTER_BEARER_TOKEN
  TRADINGVIEW_WEBHOOK_SECRET
  POLYMARKET_API_KEY
  POLYMARKET_WALLET_ADDRESS
  POLYMARKET_DEPOSIT_ADDRESS
  POLYMARKET_PROFILE_URL
  RENDER_DEPLOY_HOOK
  PLATFORM_REVISION
)

declare -A VALUES=()
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ "$line" =~ ^# ]] && continue
  [[ -z "${line// }" ]] && continue
  key="${line%%=*}"
  val="${line#*=}"
  VALUES["$key"]="$val"
done < "$ENV_FILE"

# DATABASE_URL override from environment (preferred for secrets not in .env)
if [[ -n "${DATABASE_URL:-}" ]]; then
  VALUES["DATABASE_URL"]="$DATABASE_URL"
fi

if [[ -z "${VALUES[DATABASE_URL]:-}" ]] || [[ "${VALUES[DATABASE_URL]}" == *"sqlite"* ]]; then
  echo "::warning::DATABASE_URL missing or still sqlite — set Supabase URI before deploy:"
  echo "  export DATABASE_URL='postgresql+asyncpg://postgres.zzgmovjapeyauvpdpuqe:PASSWORD@aws-0-eu-west-1.pooler.supabase.com:5432/postgres'"
  echo "See SUPABASE_SETUP.md"
fi

# Default CORS for production (always include git-main verified preview)
PRODUCTION_CORS="https://apex-trading-dashboard-flame.vercel.app,https://apex-trading-dashboard-git-main-apexweb-adams-projects.vercel.app,https://apex-trading-dashboard-apexweb-adams-projects.vercel.app"
if [[ -n "${VALUES[CORS_ORIGINS]:-}" ]]; then
  VALUES[CORS_ORIGINS]="${VALUES[CORS_ORIGINS]},${PRODUCTION_CORS}"
  # dedupe comma-separated origins
  VALUES[CORS_ORIGINS]=$(python3 -c "
import sys
seen=set(); out=[]
for o in sys.argv[1].split(','):
    o=o.strip()
    if o and o not in seen:
        seen.add(o); out.append(o)
print(','.join(out))
" "${VALUES[CORS_ORIGINS]}")
else
  VALUES[CORS_ORIGINS]="$PRODUCTION_CORS"
fi

if [[ -z "${VALUES[PLATFORM_REVISION]:-}" ]]; then
  VALUES[PLATFORM_REVISION]="2026-08-28-r108"
fi

synced=0
skipped=0
for key in "${SYNC_KEYS[@]}"; do
  val="${VALUES[$key]:-}"
  if [[ -z "$val" ]]; then
    ((skipped++)) || true
    continue
  fi
  if [[ "$key" == "DATABASE_URL" && "$val" == *"sqlite"* ]]; then
    echo "skip $key (sqlite — not for Render)"
    ((skipped++)) || true
    continue
  fi
  http=$(curl -sS -o /tmp/render-env-resp.json -w "%{http_code}" -X PUT \
    -H "Authorization: Bearer $RENDER_API_KEY" \
    -H "Content-Type: application/json" \
    -d "$(python3 -c "import json,sys; print(json.dumps({'value': sys.argv[1]}))" "$val")" \
    "https://api.render.com/v1/services/${SERVICE_ID}/env-vars/${key}" || echo "000")
  if [[ "$http" =~ ^(200|201)$ ]]; then
    echo "✓ $key"
    ((synced++)) || true
  else
    echo "✗ $key (HTTP $http)" >&2
    cat /tmp/render-env-resp.json >&2 2>/dev/null || true
    exit 1
  fi
done

echo ""
echo "Synced $synced keys ($skipped skipped)"

if [[ "${TRIGGER_DEPLOY:-false}" == "true" ]]; then
  echo "Triggering Render deploy..."
  curl -fsS -X POST \
    -H "Authorization: Bearer $RENDER_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"clearCache":"clear"}' \
    "https://api.render.com/v1/services/${SERVICE_ID}/deploys" | python3 -c "
import json,sys
d=json.load(sys.stdin)
dep=d.get('deploy',d)
print('deploy', dep.get('id','?'), 'status', dep.get('status','?'))
"
fi
