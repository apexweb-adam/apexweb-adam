#!/usr/bin/env bash
# Manually run daily post-mortem reviews for all bots (normally 22:00 UTC cron)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"
python3 << 'PY'
import asyncio
from datetime import datetime
from app.database import SessionLocal, init_db
from app.engines.learning_engine import LearningEngine
from app.config import BOT_TYPES

async def main():
    await init_db()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    async with SessionLocal() as session:
        learner = LearningEngine(session)
        for bot_type in BOT_TYPES:
            review = await learner.run_daily_review(bot_type, today)
            print(
                f"[DailyReview] {bot_type}: {review.total_trades} trades, "
                f"win rate {review.win_rate:.1%}, net PnL ${review.net_pnl:.2f}"
            )

asyncio.run(main())
PY
