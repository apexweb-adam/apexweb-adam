# Permanent Backend Deploy (Render)

One-click deploy for 24/7 paper-trading bots with persistent SQLite storage.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/apexweb-adam/apexweb-adam)

## Steps

1. Click **Deploy to Render** above (or go to [Render Blueprint](https://dashboard.render.com/blueprints) → New → connect repo).
2. Render reads root `render.yaml` and creates `apex-trading-backend`.
3. In Render → **Environment**, paste secrets from:
   ```bash
   ./trading-platform/scripts/export-render-env.sh
   ```
4. Wait for deploy (first build ~3–5 min). Copy your service URL, e.g. `https://apex-trading-backend.onrender.com`.
5. Wire dashboard:
   ```bash
   ./trading-platform/scripts/post-render-deploy.sh https://apex-trading-backend.onrender.com
   ```
6. Set `BACKEND_URL` and `BACKEND_WS_URL` on Vercel (see script output).

## Optional: Auto-redeploy

Add GitHub secret `RENDER_DEPLOY_HOOK` from Render → Settings → Deploy Hook.  
Pushes to `main` that touch `trading-platform/backend/**` will trigger redeploy.

## Optional: Render API

Add GitHub secret `RENDER_API_KEY` (from [Render Account Settings](https://dashboard.render.com/u/settings?add-api-key)) to enable the `render-api-deploy` workflow for programmatic deploy triggers.

## Verify

```bash
curl https://YOUR-SERVICE.onrender.com/api/health
curl https://YOUR-SERVICE.onrender.com/api/stats
```

Dashboard should show **Live** at https://apex-trading-dashboard-flame.vercel.app after Vercel env is updated.
