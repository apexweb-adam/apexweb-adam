"""Apply safe strategy defaults on startup (especially after deploys)."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.entities import BotState, Portfolio, Position, StrategyConfig, Trade

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


def cap_verification_signal_score(bot_type: str, score: float) -> float:
  ceiling = VERIFICATION_SIGNAL_CEILINGS.get(bot_type, 0.9)
  return min(score, ceiling)


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


async def migrate_symbol_columns(session: AsyncSession) -> bool:
  """Widen symbol columns for Polymarket slugs (PM: + up to 61 chars)."""
  from sqlalchemy import text

  from app.database import is_postgres

  if not is_postgres():
    return False

  altered = False
  for table in ("positions", "trades", "trade_analyses"):
    await session.execute(
      text(f"ALTER TABLE {table} ALTER COLUMN symbol TYPE VARCHAR(64)")
    )
    altered = True
  if altered:
    await session.commit()
  return altered


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


async def fix_breakeven_trade_labels(session: AsyncSession) -> int:
  """Relabel zero-PnL sells as breakeven (not losses) for accurate win-rate tracking."""
  sells = list(
    (
      await session.execute(
        select(Trade).where(
          Trade.action == "sell",
          Trade.pnl == 0,
          Trade.is_winner.is_(False),
        )
      )
    ).scalars().all()
  )
  for trade in sells:
    trade.is_winner = None
  if sells:
    await session.commit()
  return len(sells)


async def recalculate_portfolio_win_rates(session: AsyncSession) -> int:
  """Reconcile portfolio win_rate / winning_trades from closed sell records."""
  portfolios = list((await session.execute(select(Portfolio))).scalars().all())
  updated = 0
  for portfolio in portfolios:
    sells = list(
      (
        await session.execute(
          select(Trade).where(
            Trade.bot_type == portfolio.bot_type,
            Trade.action == "sell",
          )
        )
      ).scalars().all()
    )
    winning = sum(1 for t in sells if t.is_winner is True)
    total = len(sells)
    win_rate = winning / total if total else 0.0
    if portfolio.total_trades != total or portfolio.winning_trades != winning or portfolio.win_rate != win_rate:
      portfolio.total_trades = total
      portfolio.winning_trades = winning
      portfolio.win_rate = win_rate
      portfolio.updated_at = datetime.utcnow()
      updated += 1
  if updated:
    await session.commit()
  return updated


async def dedupe_polymarket_positions(session: AsyncSession) -> int:
  """Close duplicate open PM positions that share the same market under different slug truncations."""
  from app.engines.polymarket_data import pm_symbols_match

  result = await session.execute(
    select(Position).where(
      Position.bot_type == "polymarket",
      Position.is_open.is_(True),
    )
  )
  positions = list(result.scalars().all())
  if len(positions) < 2:
    return 0

  groups: list[list[Position]] = []
  for pos in positions:
    for group in groups:
      if pm_symbols_match(group[0].symbol, pos.symbol):
        group.append(pos)
        break
    else:
      groups.append([pos])

  portfolio = (
    await session.execute(select(Portfolio).where(Portfolio.bot_type == "polymarket"))
  ).scalar_one_or_none()
  if not portfolio:
    return 0

  closed = 0
  for group in groups:
    if len(group) <= 1:
      continue
    group.sort(key=lambda p: p.opened_at or datetime.min)
    for dup in group[1:]:
      refund = dup.quantity * dup.entry_price
      portfolio.balance += refund
      dup.is_open = False
      dup.unrealized_pnl = 0.0
      closed += 1

  if closed:
    open_remaining = [p for p in positions if p.is_open]
    portfolio.equity = portfolio.balance + sum(
      p.quantity * (p.current_price or p.entry_price) for p in open_remaining
    )
    portfolio.updated_at = datetime.utcnow()
    await session.commit()
  return closed
