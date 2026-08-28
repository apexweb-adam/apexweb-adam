# Unblock Render Production Deploy

Production backend is often **15+ commits behind** `main` because Render **After CI Checks Pass** waits for GitHub check-suites that never complete.

## Diagnose

```bash
./trading-platform/scripts/check-github-blockers.sh
./trading-platform/scripts/verify-deploy-ready.sh
curl -s https://apex-trading-backend.onrender.com/api/status | jq '.deploy | {git_commit, latest_main_commit, is_stale, github_checks_blocker, next_steps}'
```

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

Verify:

```bash
curl https://apex-trading-backend.onrender.com/api/status
curl https://apex-trading-backend.onrender.com/api/dashboard-url
```

Gate auto-pause underperformers:

```bash
curl -X POST https://apex-trading-backend.onrender.com/api/admin/sync-gate-pauses \
  -H 'Content-Type: application/json' \
  -d '{"secret":"YOUR_TRADINGVIEW_WEBHOOK_SECRET"}'
```

## Dashboard (works before backend deploy)

Verified r25 CRM preview: https://apex-trading-dashboard-73nruanbo-apexweb-adams-projects.vercel.app

Promote to production `-flame`: Vercel → Deployments → `dpl_29H1cYhLuLb1wN7L3HJD9yizZ8pL` → Promote to Production (requires `VERCEL_TOKEN` in GitHub secrets for CI promote).

See also: [RENDER_DEPLOY.md](./RENDER_DEPLOY.md)
