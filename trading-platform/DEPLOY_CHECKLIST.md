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

Részletes lépések: `RENDER_DEPLOY.md`

1. Kattints a **Deploy to Render** gombra (vagy Render → Blueprint → repo)
2. Environment fülön: `./scripts/export-render-env.sh` kimenetét másold be
3. Deploy után: `./scripts/post-render-deploy.sh https://YOUR-SERVICE.onrender.com`

### Railway alternatíva

1. https://railway.app → New Project → Deploy from GitHub
2. Root: `trading-platform/backend`
3. Dockerfile deploy
4. Add persistent volume: `/app/data`
5. Ugyanazok az env var-ok

---

## 3. Dashboard → Backend összekötés (Vercel)

Vercel → **apex-trading-dashboard** → Settings → Environment Variables:

```
BACKEND_URL=https://YOUR-BACKEND.onrender.com
BACKEND_WS_URL=wss://YOUR-BACKEND.onrender.com
```

A dashboard REST hívásokat runtime proxy-n keresztül továbbítja (`/api/backend/*`), így a backend URL Vercel env-ből olvasható újra-build nélkül is. A WebSocket közvetlenül a backendre csatlakozik.

**Redeploy** csak akkor kell, ha a `vercel.json`-ban lévő alapértelmezett env-t is frissíted.

Live dashboard: https://apex-trading-dashboard-flame.vercel.app

---

## 4. TradingView webhook

Lásd: `TRADINGVIEW_SETUP.md`

**Webhook secret (generálva neked):** `apex_tv_EB9nj4sZ_8nZCIYY-38U8ci4IodUX4G2`

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
  "message": "Alert {{ticker}} {{close}}"
}
```

---

## 5. Polymarket

**Nincs szükség bejelentkezésre** a jelenlegi scannerhez — nyilvános API.

Ha mégis be akarsz lépni: https://polymarket.com (Google / email / MetaMask).

---

## 6. Paper mode — hetekig futás

- `PAPER_TRADING_ONLY=true` maradjon
- Dashboard → **Profitability Gate** mutatja a win rate-et
- Napi review: 22:00 UTC
- Live trading csak ha: 100+ trade, 55%+ win rate, 1.3+ profit factor

Ellenőrzés: `GET /api/profitability`
