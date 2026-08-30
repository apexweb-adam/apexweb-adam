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
  REDDIT_CLIENT_ID
  REDDIT_CLIENT_SECRET
  WALLET_TRACKER_USE_DEFAULTS
  WALLET_TRACKER_ADDRESSES
  ETHERSCAN_API_KEY
  HELIUS_API_KEY
  PHANTOM_WALLET_ADDRESSES
  TRADINGVIEW_WEBHOOK_SECRET
  POLYMARKET_API_KEY
  POLYMARKET_WALLET_ADDRESS
  POLYMARKET_DEPOSIT_ADDRESS
  POLYMARKET_PROFILE_URL
  RENDER_DEPLOY_HOOK
  PLATFORM_REVISION
  GITHUB_TOKEN
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
  VALUES[PLATFORM_REVISION]=$(grep '^EXPECTED_PLATFORM_REVISION' "$ROOT/backend/app/engines/deploy_status.py" | sed -n 's/.*"\([^"]*\)".*/\1/p')
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
  http=$(curl -sS -o /tmp/render-deploy-resp.json -w "%{http_code}" -X POST \
    -H "Authorization: Bearer $RENDER_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"clearCache":"clear"}' \
    "https://api.render.com/v1/services/${SERVICE_ID}/deploys" || echo "000")
  if [[ "$http" == "202" && ! -s /tmp/render-deploy-resp.json ]]; then
    echo "deploy queued (HTTP 202 — Render accepted deploy request)"
  elif [[ "$http" =~ ^(200|201|202)$ ]]; then
    python3 -c "
import json,sys
raw=open('/tmp/render-deploy-resp.json').read().strip()
if not raw:
    print('deploy queued (HTTP $http)')
    sys.exit(0)
d=json.loads(raw)
dep=d.get('deploy',d)
print('deploy', dep.get('id','?'), 'status', dep.get('status','?'))
"
  else
    echo "✗ deploy trigger failed (HTTP $http)" >&2
    cat /tmp/render-deploy-resp.json >&2 2>/dev/null || true
    exit 1
  fi
  echo ""
  echo "After deploy completes (~3-5 min):"
  echo "  bash trading-platform/scripts/wait-for-render-deploy.sh --verify"
  echo "  bash trading-platform/scripts/verify-post-deploy.sh"
  echo "  bash trading-platform/scripts/verify-dashboard-bundle.sh"
fi
