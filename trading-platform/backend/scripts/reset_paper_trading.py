#!/usr/bin/env python3
"""Reset paper trading state to clean $100k per bot (fixes corrupted P&L from bad prices)."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import delete, select

from app.config import settings, BOT_TYPES
from app.database import SessionLocal, init_db
from app.models.entities import (
  BotState,
  DailyReview,
  IntelligenceItem,
  LearningInsight,
  Portfolio,
  Position,
  StrategyConfig,
  Trade,
  TradeAnalysis,
)


async def reset() -> None:
  await init_db()
  async with SessionLocal() as session:
    for model in (TradeAnalysis, Trade, Position, DailyReview, LearningInsight):
      await session.execute(delete(model))
    await session.execute(delete(Portfolio))
    await session.execute(delete(BotState))

    for bot_type in BOT_TYPES:
      session.add(
        Portfolio(
          bot_type=bot_type,
          balance=settings.initial_balance,
          equity=settings.initial_balance,
          total_pnl=0.0,
          win_rate=0.0,
          total_trades=0,
          winning_trades=0,
        )
      )
      result = await session.execute(
        select(StrategyConfig).where(StrategyConfig.bot_type == bot_type)
      )
      if not result.scalar_one_or_none():
        session.add(StrategyConfig(bot_type=bot_type))
      session.add(
        BotState(
          bot_type=bot_type,
          status="running",
          last_action="Paper reset — scanning markets",
          trades_today=0,
          pnl_today=0.0,
        )
      )

    await session.commit()

  intel = await _intel_count()
  print(f"Paper trading reset complete. Each bot: ${settings.initial_balance:,.0f}. Intel items kept: {intel}")


async def _intel_count() -> int:
  async with SessionLocal() as session:
    result = await session.execute(select(IntelligenceItem))
    return len(list(result.scalars().all()))


if __name__ == "__main__":
  asyncio.run(reset())
