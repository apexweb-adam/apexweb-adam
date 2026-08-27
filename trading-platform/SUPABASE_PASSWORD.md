# Supabase database password

The password `Tkradam1984` was tested against project `zzgmovjapeyauvpdpuqe` and **did not authenticate**.

## Reset your password (2 minutes)

1. Open https://supabase.com/dashboard/project/zzgmovjapeyauvpdpuqe/settings/database  
2. Click **Reset database password**  
3. Copy the new password  
4. Set on Render:
   ```
   DATABASE_URL=postgresql+asyncpg://postgres.zzgmovjapeyauvpdpuqe:YOUR_NEW_PASSWORD@aws-0-eu-west-1.pooler.supabase.com:6543/postgres
   ```

Or run `./scripts/render-env-bundle.sh` locally after adding the password to `DATABASE_URL` in `.env` (never commit `.env`).

**Do not share database passwords in chat** — rotate after pasting into Render.
