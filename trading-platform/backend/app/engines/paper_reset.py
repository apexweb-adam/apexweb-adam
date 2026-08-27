from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import BOT_TYPES, settings
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


async def reset_paper_trading(session: AsyncSession) -> dict:
  """Clear trades/positions/portfolios and re-seed $100k per bot. Keeps intel, strategies, and learning insights."""
  intel_before = (
    await session.execute(select(func.count(IntelligenceItem.id)))
  ).scalar_one()
  insights_before = (
    await session.execute(select(func.count(LearningInsight.id)))
  ).scalar_one()

  for model in (TradeAnalysis, Trade, Position, DailyReview):
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

  from app.engines.platform_settings import set_verification_started_at

  started_at = await set_verification_started_at(session)

  return {
    "bots_reset": len(BOT_TYPES),
    "initial_balance_per_bot": settings.initial_balance,
    "intel_items_kept": intel_before,
    "learning_insights_kept": insights_before,
    "verification_started_at": started_at.isoformat(),
  }
