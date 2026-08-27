# Permanent Backend Deploy (Render + Supabase)

24/7 paper-trading bots with **Supabase Postgres** persistence (Render free tier has **no disk**).

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/apexweb-adam/apexweb-adam)

## Quick deploy

1. **Blueprint** → branch `main` → `render.yaml` at repo root  
   If you see `disks are not supported for free tier` — pull latest `main` (disk block removed).

2. **Environment variables** (Render → apex-trading-backend → Environment):

   | Variable | Source |
   |----------|--------|
   | `DATABASE_URL` | [Supabase pooler URI](SUPABASE_SETUP.md) — **required** |
   | `NEWSAPI_KEY`, `TWITTER_BEARER_TOKEN`, etc. | `./scripts/export-render-env.sh` |
   | `POLYMARKET_API_KEY`, `POLYMARKET_WALLET_ADDRESS`, `POLYMARKET_DEPOSIT_ADDRESS` | Your `.env` |

3. Deploy (~3–5 min first build). URL: `https://apex-trading-backend.onrender.com`

4. **Wire Vercel dashboard:**
   ```bash
   ./trading-platform/scripts/post-render-deploy.sh https://apex-trading-backend.onrender.com
   ```
   Set `BACKEND_URL` + `BACKEND_WS_URL` on Vercel → redeploy.

5. **Verify:**
   ```bash
   ./trading-platform/scripts/verify-deploy-ready.sh
   curl https://apex-trading-backend.onrender.com/api/status
   ```

## Supabase tables

Already migrated on project `apexweb` (`zzgmovjapeyauvpdpuqe`): portfolios, trades, positions, intelligence_items, bot_states, etc.

## Optional automation

- GitHub secret `RENDER_DEPLOY_HOOK` — auto-redeploy on backend pushes (`Deploy Backend to Render`, `render-keep-alive`)
- GitHub secret `RENDER_API_KEY` — `render-api-deploy` workflow
- GitHub secret `VERCEL_TOKEN` + `VERCEL_DEPLOY_HOOK` — production dashboard deploy (`Deploy Trading Platform`)
- Render env `RENDER_DEPLOY_HOOK` — same Deploy Hook URL; stale deploys self-trigger on startup (once/hour) and via `POST /api/admin/trigger-deploy` (after latest backend is live)
- Platform setting `render_deploy_hook` — set via `POST /api/admin/set-deploy-hook` or Supabase `platform_settings` (fallback when env var unset)

**Staleness check:** `GET /api/status` → `deploy.is_stale`. When true, trigger Manual Deploy in Render or POST the Deploy Hook URL once.

### Deploy hook vs GitHub sync

The **Deploy Hook** triggers a redeploy of whatever commit Render last built from GitHub. If `deploy.git_commit` stays behind `latest_main_commit` after hook triggers:

1. **Render Dashboard** → `apex-trading-backend` → **Manual Deploy** → **Deploy latest commit**
2. Verify **Settings → Build & Deploy → Auto-Deploy** is ON and connected to `apexweb-adam/apexweb-adam` branch `main`
3. Add `RENDER_API_KEY` to GitHub secrets for CI deploys with cache clear (Render → Account → API Keys)

The keep-alive workflow (every 10 min) and deploy-render-backend (every 6h) auto-trigger the hook when stale.

## TradingView webhook (after Render live)

```
https://apex-trading-backend.onrender.com/api/webhooks/tradingview
```

Payload must include `"secret": "<TRADINGVIEW_WEBHOOK_SECRET>"`.
