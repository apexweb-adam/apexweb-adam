# Apex Trading Platform

Multi-market autonomous paper trading platform with three specialized bots, real-time intelligence gathering, continuous learning from losses, and a production-ready CRM dashboard.

## What This Does

| Bot | Markets | Schedule |
|-----|---------|----------|
| **Crypto Bot** | BTC, ETH, SOL, DOGE, PEPE + memecoins | 24/7, scans every 15s |
| **Stocks & Futures Bot** | AAPL, MSFT, NVDA, TSLA, SPY, QQQ, ES, NQ | Market hours (Mon-Fri, 14-21 UTC) |
| **Commodities Bot** | Gold, Silver, Oil, EUR/USD | 24/7, scans every 30s |

### Core Features

- **Paper trading only** — hardcoded safety lock; no real money until you explicitly disable it after verified profitability
- **Real-time dashboard** — WebSocket-powered CRM showing P&L, trades, positions, bot status
- **Intelligence gathering** — RSS news, Reddit, NewsAPI (optional), sentiment analysis on every item
- **Loss analysis** — every losing trade is automatically analyzed for root cause, lessons, and strategy adjustments
- **Daily reviews** — end-of-day post-mortem at 22:00 UTC with pattern detection and strategy changes
- **External knowledge** — trading strategies from YouTube, podcasts, Reddit wiki applied to bot parameters
- **Auto-adapting strategy** — RSI thresholds, signal scores, position sizes adjust based on performance

## Quick Start

### Docker (recommended)

```bash
cd trading-platform
cp .env.example .env
docker compose up --build
```

- Dashboard: http://localhost:3000
- API docs: http://localhost:8000/docs
- WebSocket: ws://localhost:8000/api/ws

### Manual Setup

**Backend:**
```bash
cd trading-platform/backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
mkdir -p data
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Dashboard:**
```bash
cd trading-platform/dashboard
npm install
npm run dev
```

### Deployment (24/7 Live Dashboard)

**Live CRM Dashboard (production):**
- https://apex-trading-dashboard-flame.vercel.app
- Auto-deploys from `main` → `trading-platform/dashboard` on Vercel

**Backend (bots must run 24/7):**
1. Go to [Render Dashboard](https://dashboard.render.com) → New → Blueprint
2. Connect repo `apexweb-adam/apexweb-adam`, set root directory to `trading-platform`
3. Render reads `render.yaml` — deploys `apex-trading-backend` with persistent disk
4. Copy your Render URL (e.g. `https://apex-trading-backend.onrender.com`)

**Connect dashboard to backend (Vercel project settings → Environment Variables):**
```
NEXT_PUBLIC_API_URL=https://your-backend.onrender.com
NEXT_PUBLIC_WS_URL=wss://your-backend.onrender.com
```
Redeploy dashboard after setting these.

**Local Docker:**
```bash
cd trading-platform && docker compose up --build
```

| Service | Platform | Notes |
|---------|----------|-------|
| Backend | Render, Railway, Fly.io | Docker, persistent volume for SQLite |
| Dashboard | Vercel, Netlify | Set API/WS URLs to backend |

### Intelligence Sources (Active)

| Source | Status | What it monitors |
|--------|--------|------------------|
| RSS News | Active | CoinDesk, Reuters |
| Reddit | Active | crypto, WSB, politics |
| YouTube | Active | Coin Bureau, Benjamin Cowen, Chart Guys |
| Polymarket | Active | Crypto, Trump, Fed, election markets |
| Political | Active | Trump tariffs, Google News, Reddit |
| TikTok | Active | Trading sentiment via Google News |
| X/Twitter | Needs token | Real-time social sentiment |
| TradingView | Webhook ready | Your existing alerts |
| NewsAPI | Optional | Enhanced news coverage |

### Profitability Gate

Live trading is blocked until ALL checks pass:
- 100+ paper trades
- 55%+ win rate
- 1.3+ profit factor
- Positive total P&L

Check status: `GET /api/profitability`

## Important Disclaimer

**No trading system can guarantee profitability.** This platform paper-trades by default. Only disable `PAPER_TRADING_ONLY` after extensive verified paper trading performance.

## What I Need From You

1. **NewsAPI key** — free at https://newsapi.org
2. **Twitter/X Bearer Token** — for real-time social sentiment
3. **TradingView webhook secret** — for your existing alert setup
4. **Polymarket** — account details for prediction market signals
