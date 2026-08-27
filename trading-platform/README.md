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

## Deployment (24/7 Live Dashboard)

| Service | Platform | Notes |
|---------|----------|-------|
| Backend | Railway, Render, Fly.io | Docker image, persistent volume for SQLite |
| Dashboard | Vercel, Netlify | Set `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_WS_URL` |

## Important Disclaimer

**No trading system can guarantee profitability.** This platform paper-trades by default. Only disable `PAPER_TRADING_ONLY` after extensive verified paper trading performance.

## What I Need From You

1. **NewsAPI key** — free at https://newsapi.org
2. **Twitter/X Bearer Token** — for real-time social sentiment
3. **TradingView webhook secret** — for your existing alert setup
4. **Polymarket** — account details for prediction market signals
