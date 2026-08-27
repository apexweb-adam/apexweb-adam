#!/usr/bin/env bash
# Print environment variables for Render/Railway (copy-paste into dashboard)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE — copy .env.example and fill in keys." >&2
  exit 1
fi

echo "# Paste these into Render → apex-trading-backend → Environment"
echo "PAPER_TRADING_ONLY=true"
echo "INITIAL_BALANCE=100000"
echo "DATABASE_URL=sqlite+aiosqlite:///./data/trading.db"
echo "CORS_ORIGINS=https://apex-trading-dashboard-flame.vercel.app,https://apex-trading-dashboard-apexweb-adams-projects.vercel.app"

while IFS= read -r line || [[ -n "$line" ]]; do
  [[ "$line" =~ ^# ]] && continue
  [[ -z "${line// }" ]] && continue
  key="${line%%=*}"
  case "$key" in
    NEWSAPI_KEY|TWITTER_BEARER_TOKEN|TRADINGVIEW_WEBHOOK_SECRET|POLYMARKET_WALLET_ADDRESS)
      val="${line#*=}"
      if [[ -n "$val" ]]; then
        echo "$key=$val"
      fi
      ;;
  esac
done < "$ENV_FILE"

echo ""
echo "# After deploy, set on Vercel (apex-trading-dashboard):"
echo "BACKEND_URL=https://YOUR-SERVICE.onrender.com"
echo "BACKEND_WS_URL=wss://YOUR-SERVICE.onrender.com"
echo ""
echo "# Optional GitHub secret for auto-redeploy:"
echo "RENDER_DEPLOY_HOOK=<from Render → Settings → Deploy Hook>"
