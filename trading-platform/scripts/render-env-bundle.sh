#!/usr/bin/env bash
# Output a complete Render environment block ready to paste (secrets from local .env)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/.env"

echo "# === Paste into Render → apex-trading-backend → Environment ==="
echo "PAPER_TRADING_ONLY=true"
echo "INITIAL_BALANCE=100000"
echo "CORS_ORIGINS=https://apex-trading-dashboard-flame.vercel.app,https://apex-trading-dashboard-apexweb-adams-projects.vercel.app"
echo ""
echo "# REQUIRED — replace [PASSWORD] with Supabase DB password:"
echo "DATABASE_URL=postgresql+asyncpg://postgres.zzgmovjapeyauvpdpuqe:[PASSWORD]@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"
echo ""

if [[ -f "$ENV_FILE" ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" =~ ^# ]] && continue
    [[ -z "${line// }" ]] && continue
    key="${line%%=*}"
    case "$key" in
      NEWSAPI_KEY|TWITTER_BEARER_TOKEN|TRADINGVIEW_WEBHOOK_SECRET|POLYMARKET_API_KEY|POLYMARKET_WALLET_ADDRESS|POLYMARKET_DEPOSIT_ADDRESS|POLYMARKET_PROFILE_URL)
        val="${line#*=}"
        [[ -n "$val" ]] && echo "$key=$val"
        ;;
    esac
  done < "$ENV_FILE"
fi

echo "# GitHub repo secret (Settings → Secrets → Actions) for auto-redeploy on backend push:"
echo "# RENDER_DEPLOY_HOOK=<from Render → apex-trading-backend → Settings → Deploy Hook>"
echo ""
echo "# After deploy — Vercel (apex-trading-dashboard):"
echo "BACKEND_URL=https://apex-trading-backend.onrender.com"
echo "BACKEND_WS_URL=wss://apex-trading-backend.onrender.com"
