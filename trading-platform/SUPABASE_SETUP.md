# Supabase setup for Apex Trading Platform

Paper-trading data persists in **Supabase Postgres** (project: `apexweb`, ref `zzgmovjapeyauvpdpuqe`).  
Render free tier does not support disks, so SQLite files would be wiped on every deploy.

## Tables created

Migration `create_trading_platform_tables` includes:

- `portfolios`, `positions`, `trades`, `trade_analyses`, `daily_reviews`
- `intelligence_items`, `learning_insights`, `strategy_configs`, `bot_states`

RLS is enabled on all tables (backend uses direct Postgres connection, not anon key).

## Get your DATABASE_URL

1. Open [Supabase Dashboard](https://supabase.com/dashboard/project/zzgmovjapeyauvpdpuqe/settings/database)
2. **Connect** → **ORMs** → copy the **SQLAlchemy** URI, or use the pooler URI:
3. Convert to async format for this backend:

```bash
# Pooler (local dev / serverless)
DATABASE_URL=postgresql+asyncpg://postgres.zzgmovjapeyauvpdpuqe:[PASSWORD]@aws-0-eu-west-1.pooler.supabase.com:6543/postgres

# Direct connection (recommended for Render + asyncpg — avoids pgbouncer prepared-statement issues)
DATABASE_URL=postgresql+asyncpg://postgres.zzgmovjapeyauvpdpuqe:[PASSWORD]@aws-0-eu-west-1.pooler.supabase.com:5432/postgres
```

Replace `[PASSWORD]` with your database password from **Database Settings → Database password**.

## Local dev

- **SQLite** (default): no setup — `DATABASE_URL=sqlite+aiosqlite:///./data/trading.db`
- **Supabase** (shared prod DB): paste the pooler URI above into `trading-platform/.env`

## Render Blueprint

After fixing `render.yaml` (disk removed), deploy and set in Render → Environment:

| Key | Value |
|-----|-------|
| `DATABASE_URL` | Supabase pooler URI (asyncpg format above) |
| `POLYMARKET_API_KEY` | Your Polymarket API key |
| `POLYMARKET_WALLET_ADDRESS` | Profile proxy wallet (`0x52c4…`) |
| `POLYMARKET_DEPOSIT_ADDRESS` | Deposit wallet (`0xd1be…`) |
| Other keys | From `RENDER_ENV_TEMPLATE.txt` |
