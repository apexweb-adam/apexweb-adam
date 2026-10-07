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

The **Deploy Hook** triggers a redeploy of whatever commit Render **last built** from GitHub — it does **not** pull the latest commit from `main`. When `deploy.is_stale` is true or `commits_behind` > 0, **do not POST the deploy hook**; it will redeploy the old commit and can block GitHub autoDeploy.

When stale:

1. **Render Dashboard** → `apex-trading-backend` → **Manual Deploy** → **Deploy latest commit**
2. Verify **Settings → Build & Deploy → Auto-Deploy** is **On Commit** (not *After CI Checks Pass* — Vercel rate limits can block deploys)
3. Blueprint `render.yaml` sets `autoDeployTrigger: commit` and `branch: main`
4. Root `vercel.json` uses `ignoreCommand` to skip dashboard builds on backend-only pushes (do **not** set `git.deploymentEnabled.main: false` — that leaves Vercel checks stuck `queued`)
5. `trading-platform/netlify.toml` sets `ignore = "exit 0"` so Netlify skips builds (otherwise stuck `queued`)
6. Add `RENDER_API_KEY` to **GitHub secrets** (CI deploys) and/or **Render env** (hourly self-heal via `redeploy_check_job`)
7. Add `GITHUB_TOKEN` (fine-grained repo read) on Render for reliable staleness detection in `/api/status`

### Ghost GitHub integrations (checksPass deadlock)

If Render Auto-Deploy is **After CI Checks Pass** and deploys never start, check commit statuses on `main`:

```bash
curl -s "https://api.github.com/repos/apexweb-adam/apexweb-adam/commits/main/statuses" | jq '.[].context,.[].state'
```

**Queued** statuses from unused apps (Vercel, Netlify, Supabase, Cursor, Claude) keep combined status `pending` forever.

Fix (pick one):

1. **Render Dashboard** → Settings → Build & Deploy → **On Commit** (recommended)
2. **GitHub** → repo **Settings → Integrations** → remove or disable unused GitHub Apps
3. **Vercel** → `apex-trading-dashboard` → ensure Git linked; use `ignoreCommand` not `deploymentEnabled.main: false`
4. Add **`RENDER_API_KEY`** — deploys via API regardless of commit status

After r83+, `/api/status` → `deploy.github_checks_blocker` lists blocking integrations.

CI workflows and the in-app redeploy trigger skip the deploy hook when stale. The keep-alive workflow (every 10 min) only pings health; it triggers API deploy when stale (if `RENDER_API_KEY` is set).

## TradingView webhook (after Render live)

```
https://apex-trading-backend.onrender.com/api/webhooks/tradingview
```

Payload must include `"secret": "<TRADINGVIEW_WEBHOOK_SECRET>"`.

## Render workflows paused (2026-10-07)

`Render Keep-Alive` (`render-keep-alive.yml`) and `Render Billing Recovery` (`render-billing-recovery.yml`) are disabled with `gh workflow disable`. The files stay in the repo. Reason: the backend runs on the Render free plan and nobody will pay for Render, while both workflows failed on every run:

- **Keep-Alive** had no checkout step, so `source trading-platform/scripts/lib/fetch_json.sh` failed with "No such file or directory" on every run since 2026-08-31 (last green run 2026-08-31 06:49 UTC). The checkout is now added, so re-enabling works without further edits.
- **Billing Recovery** never had a green run (0 of 245). In the 2026-10-07 19:26 UTC run the backend was online and 21 checks passed; the job then died in `trading-platform/scripts/recover-render-billing.sh` line 194: the status JSON is piped into `python3 << 'PY'`, the heredoc takes over stdin, and `json.load(sys.stdin)` reads nothing (JSONDecodeError).
- On 2026-10-07 20:03 UTC the backend was **online**: `/api/health` 200 with `mode: paper_trading`, deployed commit = `main` (`38b8262`), all 4 bots scanning. Render suspends every free service of a workspace when the workspace uses up its 750 free instance hours in a calendar month, and resumes them on the 1st.
- Side effect of pausing: small. A free service sleeps after 15 minutes without inbound traffic, and GitHub started these schedules only about 5 times a day (5 Billing Recovery runs on 2026-10-06), so the backend already slept most of the day: its own `platform_outage_events` log shows wake-up gaps of 28 to 516 minutes (mostly 3 to 7 hours). The paper bots run only while something calls the API; Platform Health Check wakes it every 6 hours, and spin-up takes about a minute.
- Deploys: Render had not deployed `dfcf462` (the commit that added this section) 20 minutes after it reached `main`; `/api/status` listed it under `pending_changes`. The backend redeploys itself only at startup, only when `RENDER_API_KEY` is set in the Render environment, and at most once every 6 hours, so a commit on `main` can stay undeployed until a later restart (or a Manual Deploy in Render).

`Platform Health Check` now probes the backend and the Vercel dashboard first and skips the live checks that target something not serving (with a `::warning::`). Backend unit tests always run. Its freshness step fails only when the commits Render has not deployed change what Render builds (`trading-platform/backend/`, `render.yaml`, `trading-platform/render.yaml`); newer docs or workflow commits give a `::warning::`.

### What still depends on the Render backend

Service `srv-da848ms9v7es739k38jg`, `https://apex-trading-backend.onrender.com` (and `wss://` for `/api/ws`):

| Where | What |
|---|---|
| `.github/workflows/platform-health-check.yml` | live backend checks (snapshot, deploy freshness, `/crm`, WebSocket, equity history) |
| `.github/workflows/deploy-render-backend.yml`, `render-api-deploy.yml` (push to `main`, backend paths), `render-hook-recovery.yml` (manual) | trigger Render deploys with `RENDER_DEPLOY_HOOK` (the only secret set) or `RENDER_API_KEY` (not set) |
| `.github/workflows/render-keep-alive.yml`, `render-billing-recovery.yml` | paused, see above |
| `.github/workflows/deploy-trading-platform.yml`, `trading-platform/vercel.json`, `trading-platform/dashboard/vercel.json`, `trading-platform/dashboard/lib/production-backend.ts` | Vercel dashboard: `BACKEND_URL`, `BACKEND_WS_URL`, `/api/backend/*` proxy. All dashboard URLs return 404 `DEPLOYMENT_NOT_FOUND` (checked 2026-10-07) |
| `render.yaml`, `trading-platform/render.yaml`, `trading-platform/RENDER_ENV_TEMPLATE.txt` | Render Blueprint and env template |
| `trading-platform/backend/app/api/routes.py`, `app/engines/crm_summary.py`, `app/engines/platform_status.py` | links the backend prints about itself |
| `trading-platform/backend/assets/*.user.js`, `trading-platform/scripts/fomo-family-bridge.user.js` | browser userscripts (Axiom, fomo.family, Phantom) that post to the backend |
| TradingView alerts (`TRADINGVIEW_SETUP.md`), Zapier fomo hook (`scripts/fomo-zapier-setup.md`) | senders configured outside this repo |
| 38 ops scripts in `trading-platform/scripts/` (`verify-*.sh`, `recover-render-billing.sh`, `lib/fetch_json.sh` with `RENDER_SERVICE_ID`, ...) | default backend URL |

Data lives in Supabase project `zzgmovjapeyauvpdpuqe` (`DATABASE_URL`), not on Render, so a move keeps all history. The `apex-web-codex` trading lab does not use this backend.

### Re-enable on Render

1. If the service is suspended: wait for the monthly reset or add a payment method, then resume it at https://dashboard.render.com/web/srv-da848ms9v7es739k38jg.
2. `gh workflow enable render-keep-alive.yml -R apexweb-adam/apexweb-adam`, then `gh workflow run render-keep-alive.yml -R apexweb-adam/apexweb-adam` and confirm the run is green. A 24/7 keep-alive uses about 744 of the 750 free hours, so any other free service in the same workspace ends the month early.
3. Billing Recovery only after fixing `recover-render-billing.sh` line 194 (pass the JSON through an env var or a temp file instead of stdin); then `gh workflow enable render-billing-recovery.yml -R apexweb-adam/apexweb-adam`.

### Move to the Hetzner VPS (not done)

1. On the VPS: `docker build -t apex-trading-backend trading-platform/backend` (Python 3.12 image, uvicorn on port 8000, `HEALTHCHECK` on `/api/health`).
2. Env file from the Render service (`scripts/export-render-env.sh`, `RENDER_ENV_TEMPLATE.txt`): `DATABASE_URL` (Supabase pooler), `PAPER_TRADING_ONLY=true`, `INITIAL_BALANCE`, `NEWSAPI_KEY`, `TWITTER_BEARER_TOKEN`, `TRADINGVIEW_WEBHOOK_SECRET`, `POLYMARKET_*`, `CORS_ORIGINS`, `PLATFORM_REVISION`, `DISABLE_AUTO_REDEPLOY=true`; drop `RENDER_DEPLOY_HOOK` and `RENDER_API_KEY`.
3. `docker run -d --restart unless-stopped --env-file <file> -p 127.0.0.1:8000:8000 apex-trading-backend`, behind Caddy or nginx with TLS on a subdomain; forward WebSocket upgrades for `/api/ws`.
4. Check: `curl https://<new-host>/api/health` returns `{"status":"ok","mode":"paper_trading"}`, `/api/status` shows 4 bots scanning, and the WebSocket sends an `update` message.
5. Replace `https://apex-trading-backend.onrender.com` and `wss://apex-trading-backend.onrender.com` in the files listed above, plus the TradingView alert URL, the Zapier hook and the installed userscripts.
6. Delete the Render-only workflows (`render-*.yml`, `deploy-render-backend.yml`) and the probe's Render wording in `platform-health-check.yml`; a VPS needs no keep-alive.
7. Suspend the Render service, and delete it after a week without traffic.
