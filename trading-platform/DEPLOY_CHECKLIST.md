# 24/7 Deploy — lépésről lépésre

## 1. API kulcsok (már beállítva lokálisan)

A `trading-platform/.env` fájlban megvannak. **Ne commitold gitbe.**

Production backendnél ugyanezeket add hozzá Render/Railway **Environment Variables** menüben.

| Változó | Mit csinál |
|---------|------------|
| `NEWSAPI_KEY` | NewsAPI hírek |
| `TWITTER_BEARER_TOKEN` | X/Twitter sentiment |
| `TRADINGVIEW_WEBHOOK_SECRET` | TradingView alertek |
| `PAPER_TRADING_ONLY` | `true` — ne változtasd |
| `CORS_ORIGINS` | Vercel dashboard URL-ek |

---

## 2. Backend 24/7 — Render (ajánlott)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/apexweb-adam/apexweb-adam)

**Fontos:** A Render free tier **nem támogat disket**. Az adatbázis **Supabase Postgres** (lásd `SUPABASE_SETUP.md`).

1. Blueprint → branch `main` → `render.yaml` (disk nélkül)
2. Environment: `./scripts/export-render-env.sh` + Supabase `DATABASE_URL` (jelszó a Supabase dashboardból)
3. Deploy után: `./scripts/post-render-deploy.sh https://YOUR-SERVICE.onrender.com`

| Változó | Mit csinál |
|---------|------------|
| `DATABASE_URL` | Supabase pooler URI (`postgresql+asyncpg://...`) |
| `POLYMARKET_API_KEY` | Polymarket API kulcs |
| `POLYMARKET_WALLET_ADDRESS` | @apexweb proxy wallet |
| `POLYMARKET_DEPOSIT_ADDRESS` | Deposit wallet |

---

## 3. Dashboard → Backend összekötés (Vercel)

Vercel → **apex-trading-dashboard** → Settings → Environment Variables:

```
BACKEND_URL=https://YOUR-BACKEND.onrender.com
BACKEND_WS_URL=wss://YOUR-BACKEND.onrender.com
```

A dashboard REST hívásokat runtime proxy-n keresztül továbbítja (`/api/backend/*`), így a backend URL Vercel env-ből olvasható újra-build nélkül is. A WebSocket közvetlenül a backendre csatlakozik.

**Redeploy** csak akkor kell, ha a `vercel.json`-ban lévő alapértelmezett env-t is frissíted.

**Operational dashboard (full features):** https://apex-trading-dashboard-q1o1x9nlh-apexweb-adams-projects.vercel.app  
(`bundleRevision` r7, native `/api/active-gate`, equity chart — use this until production is promoted.)

Legacy production alias (stale bundle): https://apex-trading-dashboard-flame.vercel.app  
(Promote `dpl_DFWFJtVnsfSLAkby6DWNLqUHYX7p` in [Vercel deployments](https://vercel.com/apexweb-adams-projects/apex-trading-dashboard/deployments) or add `VERCEL_TOKEN` to GitHub secrets.)

### GitHub Actions deploy secrets (CI)

Add these in **GitHub → repo → Settings → Secrets and variables → Actions**:

| Secret | Purpose |
|--------|---------|
| `VERCEL_TOKEN` | Production dashboard deploy (`Deploy Trading Platform` workflow) |
| `VERCEL_DEPLOY_HOOK` | Fallback: Vercel → apex-trading-dashboard → Settings → Git → Deploy Hooks (branch `main`) |
| `RENDER_DEPLOY_HOOK` | Auto-redeploy backend when stale (Render → apex-trading-backend → Settings → Deploy Hook) |
| `RENDER_API_KEY` | Alternative backend deploy via Render API |

**One-time production promote:** After adding `VERCEL_TOKEN`, run **Promote Vercel Dashboard to Production** (auto-runs on main dashboard pushes). Verified preview: `dpl_DFWFJtVnsfSLAkby6DWNLqUHYX7p`.

Optional repo **variables** (defaults exist in workflow):

| Variable | Value |
|----------|-------|
| `VERCEL_ORG_ID` | `team_K7OUE7uroVXeVUf42cUAQvAl` |
| `VERCEL_PROJECT_ID` | `prj_HGbG5vHgfutHi31QfXDqSsTnTAGv` |

**If production is stale:** Render → Manual Deploy (only if `deploy.is_stale`); Vercel → Promote latest preview or add `VERCEL_TOKEN`.

**Gate on stale Vercel prod:** `/api/backend/active-gate` and `/api/backend/equity-history` work via proxy (backend must be current).

Verify backend: `curl https://apex-trading-backend.onrender.com/api/status` — `deploy.git_commit` should match `latest_main_commit`; `curl .../api/equity-history` should return 200.

---

## 4. TradingView webhook

Lásd: `TRADINGVIEW_SETUP.md`

**Webhook secret (generálva):** `apex_tv_EB9nj4sZ_8nZCIYY-38U8ci4IodUX4G2` — ugyanaz legyen Render env-ben és az alert JSON-ban.

**Webhook URL (backend deploy után):**
```
https://YOUR-BACKEND.onrender.com/api/webhooks/tradingview
```

Alert Message mező (JSON):
```json
{
  "secret": "apex_tv_EB9nj4sZ_8nZCIYY-38U8ci4IodUX4G2",
  "symbol": "{{ticker}}",
  "action": "{{strategy.order.action}}",
  "message": "Alert {{ticker}} at {{close}}"
}
```

---

## 5. Polymarket

**Nincs szükség bejelentkezésre** — a piaci scanner a nyilvános Gamma API-t használja (már fut).

Opcionális: ha megadod a proxy wallet címedet (`POLYMARKET_WALLET_ADDRESS=0x...` a `.env`-ben), a bot a saját pozícióidat is olvassa. Jelenleg nincs wallet beállítva — ez rendben van, nem kötelező.

---

## 6. Paper mode — hetekig futás

- `PAPER_TRADING_ONLY=true` maradjon
- Dashboard → **Profitability Gate** mutatja a win rate-et
- Napi review: 22:00 UTC
- Live trading csak ha: 100+ trade, 55%+ win rate, 1.3+ profit factor

Ellenőrzés: `GET /api/profitability`
