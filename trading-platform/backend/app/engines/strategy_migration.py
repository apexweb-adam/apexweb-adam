"""Apply safe strategy defaults on startup (especially after deploys)."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.entities import StrategyConfig

POLYMARKET_DEFAULTS = {
  "max_position_pct": settings.polymarket_max_position_pct,
  "stop_loss_pct": settings.polymarket_stop_loss_pct,
  "min_signal_score": 0.22,
  "take_profit_pct": 0.08,
}


async def ensure_polymarket_strategy(session: AsyncSession) -> bool:
  """Clamp Polymarket strategy to safe paper-trading limits. Returns True if updated."""
  result = await session.execute(
    select(StrategyConfig).where(StrategyConfig.bot_type == "polymarket")
  )
  config = result.scalar_one_or_none()
  if not config:
    config = StrategyConfig(bot_type="polymarket", **POLYMARKET_DEFAULTS)
    session.add(config)
    await session.commit()
    return True

  changed = False
  if config.max_position_pct > settings.polymarket_max_position_pct:
    config.max_position_pct = settings.polymarket_max_position_pct
    changed = True
  if config.stop_loss_pct > settings.polymarket_stop_loss_pct:
    config.stop_loss_pct = settings.polymarket_stop_loss_pct
    changed = True
  if config.min_signal_score < 0.20:
    config.min_signal_score = 0.22
    changed = True

  if changed:
    config.version += 1
    config.updated_at = datetime.utcnow()
    await session.commit()
  return changed
