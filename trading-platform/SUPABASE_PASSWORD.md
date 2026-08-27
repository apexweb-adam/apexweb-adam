# Supabase database password

Password has been configured on Render (`DATABASE_URL`). **Rotate it** if it was ever shared in chat:

1. Open https://supabase.com/dashboard/project/zzgmovjapeyauvpdpuqe/settings/database  
2. Click **Reset database password**  
3. Update `DATABASE_URL` on Render → apex-trading-backend → Environment  

## Render DATABASE_URL format (asyncpg + direct connection)

```
postgresql+asyncpg://postgres.zzgmovjapeyauvpdpuqe:YOUR_PASSWORD@aws-0-eu-west-1.pooler.supabase.com:5432/postgres
```

Use port **5432** (direct) on Render — port 6543 (pgbouncer) can break asyncpg prepared statements.

Never commit passwords to git.
