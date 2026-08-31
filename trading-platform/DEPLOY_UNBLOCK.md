# Unblock Render Production Deploy

Production backend is often **15+ commits behind** `main` because Render **After CI Checks Pass** waits for GitHub check-suites that never complete.

## Diagnose

```bash
./trading-platform/scripts/verify-platform.sh
./trading-platform/scripts/check-github-blockers.sh
./trading-platform/scripts/verify-deploy-ready.sh
curl -s https://apex-trading-backend.onrender.com/api/status | jq '.deploy | {git_commit, latest_main_commit, is_stale, github_checks_blocker, next_steps}'
```

## Render billing suspension (503 Service Suspended)

If `/api/health` returns **503** with `Service Suspended`, or Render API shows `suspenders: ["billing"]`:

| Symptom | Cause |
|---------|--------|
| Backend 503 HTML | Free-tier billing limit (750 instance hours/month) or missing payment method |
| `POST /v1/services/.../resume` → 400 | Billing suspension — only user-resumed in dashboard |
| `POST /v1/services/.../deploys` → 400 | Cannot deploy while billing-suspended |
| Dashboard proxy returns HTML | Same — bots and CRM data offline |

### Fix

1. [Render Dashboard → apex-trading-backend](https://dashboard.render.com/web/srv-da848ms9v7es739k38jg)
2. Resolve billing: add payment method and/or upgrade from **free** plan
3. **Resume** the service manually
4. Verify:

```bash
bash trading-platform/scripts/wait-for-render-deploy.sh --verify
bash trading-platform/scripts/verify-platform.sh
```

Ops scripts (`verify-us-stocks-open.sh`, `verify-platform.sh`, etc.) exit **2** with recovery steps when billing suspension is detected.

### Automated recovery (after billing fixed)

```bash
bash trading-platform/scripts/recover-render-billing.sh
```

Polls until the backend resumes, then **auto-triggers a Render deploy** if production revision is behind main, runs deploy wait, platform verify, and Monday US stocks post-open checks.

**Platform-outage recovery (r467+):** If billing suspension caused a missed US open but open-ready symbols (e.g. AAPL) were queued in prep state, burst scan/auto-entry still runs on resume for up to **270 minutes** after session open (13:30 UTC Monday). **After grace expires**, r467+ still forces open-ready scan from preserved prep state on post-outage startup. On startup the platform:

- Logs outage gap + held open positions
- Force-refreshes TradingView for held positions
- Runs immediate post-outage recovery burst scans (stocks/commodities + crypto held)
- Recovery script runs US stocks scan preview, CME post-open verify, crypto scan preview, and `verify-crypto-held.sh` for 24/7 held-position recovery

```bash
bash trading-platform/scripts/print-outage-status.sh
bash trading-platform/scripts/recover-render-billing.sh
```

---

## Typical blockers

| GitHub App | Symptom | Fix |
|------------|---------|-----|
| Vercel | check-suite `queued` | Repo uses `ignoreCommand` in root `vercel.json` — do **not** set `deploymentEnabled.main: false`. If still queued, remove repo access in [GitHub App settings](https://github.com/apexweb-adam/apexweb-adam/settings/installations) or disconnect Git in Vercel project settings. |
| Netlify | check-suite `queued` | `trading-platform/netlify.toml` sets `ignore = "exit 0"`. Remove Netlify GitHub App access to this repo if still stuck. |
| Supabase | check-suite `queued` | Remove Supabase GitHub integration for this repo (platform uses Supabase via `DATABASE_URL` on Render, not Netlify/Supabase GitHub builds). |
| Cursor / Claude | check-suite `queued` | Remove or reconfigure IDE bot integrations under [Installed GitHub Apps](https://github.com/apexweb-adam/apexweb-adam/settings/installations). |

## Fix (choose one)

### A. Fastest — Render Manual Deploy (~5 min)

1. Open [Render Dashboard](https://dashboard.render.com) → **apex-trading-backend**
2. **Manual Deploy** → **Deploy latest commit**
3. **Settings → Build & Deploy → Auto-Deploy** → **On Commit** (not *After CI Checks Pass*)

### B. Clean GitHub — permanent fix for checksPass

1. [GitHub → apexweb-adam → Settings → Integrations](https://github.com/apexweb-adam/apexweb-adam/settings/installations)
2. For **Vercel, Netlify, Supabase, Cursor, Claude**: Configure → remove this repository (or uninstall if unused)
3. Push an empty commit or re-run **Manual Deploy** on Render

### C. Bypass GitHub checks — API deploy

1. Create a [Render API key](https://dashboard.render.com/u/settings#api-keys)
2. Add **`RENDER_API_KEY`** to:
   - GitHub repo **Secrets** (for `render-api-deploy` / `Deploy Backend to Render` workflows)
   - Render service **Environment** (for hourly `redeploy_check_job` self-heal)
3. Trigger: **Actions → Render Hook Recovery → Run workflow**

## After deploy succeeds (r78+)

Render is now on **610e1a6 (r87+)** as of manual deploy. Verify:

```bash
./trading-platform/scripts/verify-platform.sh
curl https://apex-trading-backend.onrender.com/api/dashboard-url
curl https://apex-trading-backend.onrender.com/api/platform-urls
```

Gate auto-pause underperformers:

```bash
./trading-platform/scripts/sync-prod-gate-pauses.sh
```

Or (r79+ backend only):

```bash
curl -X POST https://apex-trading-backend.onrender.com/api/admin/sync-gate-pauses \
  -H 'Content-Type: application/json' \
  -d '{"secret":"YOUR_TRADINGVIEW_WEBHOOK_SECRET"}'
```

The sync script falls back to `set-bot-paused` per bot when `sync-gate-pauses` returns 404 (stale Render).

**Deploy hook (stored in prod DB, not git):**

```bash
# One-time: get URL from Render → apex-trading-backend → Settings → Deploy Hook
./trading-platform/scripts/setup-render-deploy-hook.sh "$RENDER_DEPLOY_HOOK"
# Or trigger via stored hook:
curl -X POST https://apex-trading-backend.onrender.com/api/admin/trigger-deploy \
  -H 'Content-Type: application/json' \
  -d '{"secret":"YOUR_TRADINGVIEW_WEBHOOK_SECRET","force":true}'
```

Prefer **RENDER_API_KEY** for stale deploys (pulls latest commit); deploy hook redeploys last built commit.

## Dashboard (works before backend deploy)

Verified r25 CRM preview: https://apex-trading-dashboard-73nruanbo-apexweb-adams-projects.vercel.app

Promote to production `-flame`: Vercel → Deployments → `dpl_29H1cYhLuLb1wN7L3HJD9yizZ8pL` → Promote to Production (requires `VERCEL_TOKEN` in GitHub secrets for CI promote).

Or run locally:

```bash
export VERCEL_TOKEN=...
./trading-platform/scripts/promote-vercel-dashboard.sh
```

**Vercel free tier:** 100 API deploys/day — if promote fails with `payment_required`, wait 24h or promote manually in the Vercel dashboard.

**Use verified preview now (stable until promote):** https://apex-trading-dashboard-73nruanbo-apexweb-adams-projects.vercel.app

See also: [RENDER_DEPLOY.md](./RENDER_DEPLOY.md)
