"""Apply safe strategy defaults on startup (especially after deploys)."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.entities import BotState, Portfolio, Position, StrategyConfig

POLYMARKET_DEFAULTS = {
  "max_position_pct": settings.polymarket_max_position_pct,
  "stop_loss_pct": settings.polymarket_stop_loss_pct,
  "min_signal_score": 0.22,
  "take_profit_pct": 0.08,
}

# Learning/content-study can inflate thresholds — cap during paper verification
VERIFICATION_SIGNAL_CEILINGS = {
  "crypto": 0.22,
  "stocks_futures": 0.28,
  "commodities": 0.28,
  "polymarket": 0.25,
}


async def clamp_verification_strategy_params(session: AsyncSession) -> int:
  """Lower over-tightened signal thresholds so all bots can trade during verification."""
  configs = list((await session.execute(select(StrategyConfig))).scalars().all())
  updated = 0
  for config in configs:
    ceiling = VERIFICATION_SIGNAL_CEILINGS.get(config.bot_type)
    if ceiling is None:
      continue
    changed = False
    if config.min_signal_score > ceiling:
      config.min_signal_score = ceiling
      changed = True
    if config.min_sentiment_score > 0.15:
      config.min_sentiment_score = 0.0
      changed = True
    if config.bot_type == "polymarket":
      if config.max_position_pct > settings.polymarket_max_position_pct:
        config.max_position_pct = settings.polymarket_max_position_pct
        changed = True
    if changed:
      config.version += 1
      config.updated_at = datetime.utcnow()
      updated += 1
  if updated:
    await session.commit()
  return updated


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
  if config.min_signal_score > VERIFICATION_SIGNAL_CEILINGS["polymarket"]:
    config.min_signal_score = VERIFICATION_SIGNAL_CEILINGS["polymarket"]
    changed = True

  if changed:
    config.version += 1
    config.updated_at = datetime.utcnow()
    await session.commit()
  return changed


async def trim_oversized_polymarket_positions(session: AsyncSession) -> int:
  """Shrink legacy PM positions that exceed the USD cap (pre-fix deploys). Returns count trimmed."""
  result = await session.execute(
    select(Portfolio).where(Portfolio.bot_type == "polymarket")
  )
  portfolio = result.scalar_one_or_none()
  if not portfolio:
    return 0

  result = await session.execute(
    select(Position).where(
      Position.bot_type == "polymarket",
      Position.is_open.is_(True),
    )
  )
  positions = list(result.scalars().all())
  trimmed = 0
  cap = settings.polymarket_max_position_usd

  for pos in positions:
    price = pos.current_price or pos.entry_price
    if price <= 0:
      continue
    notional = pos.quantity * price
    if notional <= cap * 1.05:
      continue

    max_qty = cap / price
    excess_qty = pos.quantity - max_qty
    if excess_qty <= 0:
      continue

    refund = excess_qty * pos.entry_price
    pos.quantity = max_qty
    pos.unrealized_pnl = (price - pos.entry_price) * pos.quantity
    portfolio.balance += refund
    trimmed += 1

  if trimmed:
    open_positions = [p for p in positions if p.is_open]
    portfolio.equity = portfolio.balance + sum(
      p.quantity * (p.current_price or p.entry_price) for p in open_positions
    )
    portfolio.updated_at = datetime.utcnow()
    await session.commit()

  return trimmed


async def sync_bot_strategy_versions(session: AsyncSession) -> int:
  """Align BotState.current_strategy_version with StrategyConfig.version."""
  configs = {
    c.bot_type: c.version
    for c in (await session.execute(select(StrategyConfig))).scalars().all()
  }
  states = list((await session.execute(select(BotState))).scalars().all())
  updated = 0
  for state in states:
    version = configs.get(state.bot_type)
    if version is not None and state.current_strategy_version != version:
      state.current_strategy_version = version
      state.updated_at = datetime.utcnow()
      updated += 1
  if updated:
    await session.commit()
  return updated
