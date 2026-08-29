"""Apply safe strategy defaults on startup (especially after deploys)."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.engines.platform_settings import is_bot_paused
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


COMMODITIES_EXCESS_TRIM_MAX_LOSS_USD = 5.0


def _commodities_position_unrealized(pos: Position) -> float:
  if pos.unrealized_pnl is not None:
    return float(pos.unrealized_pnl)
  if pos.current_price and pos.entry_price:
    return float((pos.current_price - pos.entry_price) * pos.quantity)
  return 0.0


def _commodities_excess_trim_rank(pos: Position) -> tuple[int, float]:
  """Lower rank trims first: profits, breakeven, small losses; large losses last."""
  u = _commodities_position_unrealized(pos)
  if u >= 0:
    return (0, -u)
  if u >= -1.0:
    return (1, u)
  if u >= -COMMODITIES_EXCESS_TRIM_MAX_LOSS_USD:
    return (2, u)
  return (3, u)


def select_commodities_excess_trim_targets(
  positions: list[Position],
  cap: int,
) -> list[Position]:
  """Pick positions to close when over cap — bank profits before realizing large losses."""
  if len(positions) <= cap:
    return []
  need = len(positions) - cap
  trimmable = [p for p in positions if _commodities_excess_trim_rank(p)[0] < 3]
  ranked = sorted(positions, key=_commodities_excess_trim_rank)
  if len(trimmable) >= need:
    return ranked[:need]
  return sorted(trimmable, key=_commodities_excess_trim_rank)[:need]


def _commodities_graduation_excess_trim_rank(pos: Position) -> tuple[int, float]:
  """During graduation nudge, free slots for recovery futures — trim flat/losers before spot profits."""
  from app.engines.gate_entry_guard import is_commodities_futures_symbol
  from app.engines.market_data import CRYPTO_LIVE_PRICE_PROXY

  u = _commodities_position_unrealized(pos)
  symbol = pos.symbol
  if u <= -COMMODITIES_EXCESS_TRIM_MAX_LOSS_USD:
    return (9, u)
  if symbol in CRYPTO_LIVE_PRICE_PROXY:
    if u >= 0:
      return (4, -u)
    return (3, u)
  if is_commodities_futures_symbol(symbol) or symbol.endswith("=X"):
    if abs(u) <= 0.15:
      return (0, abs(u))
    if u < 0:
      return (1, u)
    return (2, -u)
  if u < 0:
    return (2, u)
  return (3, -u)


def select_commodities_graduation_excess_trim_targets(
  positions: list[Position],
  cap: int,
) -> list[Position]:
  """Pick positions to close when over effective cap during graduation nudge."""
  if len(positions) <= cap:
    return []
  need = len(positions) - cap
  trimmable = [p for p in positions if _commodities_graduation_excess_trim_rank(p)[0] < 9]
  ranked = sorted(trimmable, key=_commodities_graduation_excess_trim_rank)
  return ranked[:need]


async def adapt_for_gate_win_rate(session: AsyncSession) -> int:
  """Raise min_signal_score and min_sentiment when gate win rate is below target."""
  from app.engines.gate_entry_guard import get_underperforming_bots
  from app.engines.profitability_gate import ProfitabilityGate

  gate = await ProfitabilityGate(session).evaluate()
  if gate.get("total_trades", 0) < 30:
    return 0
  if (gate.get("win_rate") or 0) >= ProfitabilityGate.MIN_WIN_RATE:
    return 0

  blocked = await get_underperforming_bots(session)
  configs = list((await session.execute(select(StrategyConfig))).scalars().all())
  updated = 0
  for config in configs:
    ceiling = VERIFICATION_SIGNAL_CEILINGS.get(config.bot_type)
    if ceiling is None:
      continue
    changed = False
    step = 0.02 if config.bot_type in blocked else 0.01
    target_signal = ceiling if config.bot_type in blocked else min(ceiling, config.min_signal_score + step)
    if config.min_signal_score < target_signal - 0.005:
      config.min_signal_score = target_signal
      changed = True
    sentiment_cap = 0.18 if config.bot_type in blocked else 0.15
    if config.min_sentiment_score < sentiment_cap - 0.005:
      config.min_sentiment_score = min(sentiment_cap, config.min_sentiment_score + (0.03 if config.bot_type in blocked else 0.02))
      changed = True
    if config.bot_type == "polymarket":
      if config.stop_loss_pct > 0.03:
        config.stop_loss_pct = 0.03
        changed = True
      if config.bot_type in blocked and config.max_position_pct > settings.polymarket_max_position_pct * 0.5:
        config.max_position_pct = settings.polymarket_max_position_pct * 0.5
        changed = True
    if changed:
      config.version += 1
      config.updated_at = datetime.utcnow()
      updated += 1

  if updated:
    await session.commit()
  return updated


async def clamp_verification_strategy_params(session: AsyncSession) -> int:
  """Lower over-tightened signal thresholds so all bots can trade during verification."""
  from app.engines.profitability_gate import ProfitabilityGate

  gate = await ProfitabilityGate(session).evaluate()
  gate_below_target = (
    gate.get("total_trades", 0) >= 30
    and (gate.get("win_rate") or 0) < ProfitabilityGate.MIN_WIN_RATE
  )
  active_trades = int(gate.get("total_trades") or 0)
  active_wr = float(gate.get("win_rate") or 0)
  early_stocks_verification = (
    active_trades < 30 and active_wr >= ProfitabilityGate.MIN_WIN_RATE
  )

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
    if not gate_below_target and config.min_sentiment_score >= 0.15:
      config.min_sentiment_score = 0.0
      changed = True
    if early_stocks_verification and config.bot_type == "stocks_futures":
      if config.min_signal_score > 0.20:
        config.min_signal_score = 0.20
        changed = True
      if config.min_sentiment_score > 0.0:
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
  paused = await is_bot_paused(session, "polymarket")
  if config.max_position_pct <= 0 and not paused:
    config.max_position_pct = settings.polymarket_max_position_pct
    changed = True
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
    result = await session.execute(
      text(
        """
        SELECT character_maximum_length
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = :table
          AND column_name = 'symbol'
        """
      ),
      {"table": table},
    )
    current = result.scalar_one_or_none()
    if current is not None and int(current) >= 64:
      continue
    try:
      await session.execute(
        text(f"ALTER TABLE {table} ALTER COLUMN symbol TYPE VARCHAR(64)")
      )
      altered = True
    except Exception as exc:
      # Non-owner roles (e.g. apex_render_backend) cannot ALTER — skip if already wide enough.
      if current is not None and int(current) >= 32:
        print(f"[Strategy] Skipping symbol migration on {table} ({exc.__class__.__name__})")
        continue
      raise
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


async def reconcile_portfolio_balances(session: AsyncSession) -> int:
  """Recompute balance/equity/total_pnl from the trade ledger after manual DB edits."""
  portfolios = list((await session.execute(select(Portfolio))).scalars().all())
  updated = 0
  for portfolio in portfolios:
    trades = list(
      (
        await session.execute(select(Trade).where(Trade.bot_type == portfolio.bot_type))
      ).scalars().all()
    )
    buy_cost = sum(t.quantity * t.price for t in trades if t.action == "buy")
    sell_proceeds = sum(t.quantity * t.price for t in trades if t.action == "sell")
    expected_total_pnl = sum(t.pnl for t in trades if t.action == "sell")

    open_positions = list(
      (
        await session.execute(
          select(Position).where(
            Position.bot_type == portfolio.bot_type,
            Position.is_open.is_(True),
          )
        )
      ).scalars().all()
    )
    open_market = sum(
      p.quantity * (p.current_price or p.entry_price) for p in open_positions
    )
    expected_balance = settings.initial_balance - buy_cost + sell_proceeds
    expected_equity = expected_balance + open_market

    drift = (
      abs(portfolio.balance - expected_balance) > 0.02
      or abs(portfolio.equity - expected_equity) > 0.02
      or abs(portfolio.total_pnl - expected_total_pnl) > 0.02
    )
    if drift:
      portfolio.balance = expected_balance
      portfolio.equity = expected_equity
      portfolio.total_pnl = expected_total_pnl
      portfolio.updated_at = datetime.utcnow()
      updated += 1

  if updated:
    await session.commit()
  return updated


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


async def close_non_macro_polymarket_positions(session: AsyncSession) -> int:
  """Exit open PM positions that fail macro/sports filter (legacy sports noise)."""
  from app.engines.paper_trading import PaperTradingEngine
  from app.engines.polymarket_data import fetch_polymarket_data, is_macro_relevant_symbol

  engine = PaperTradingEngine(session, "polymarket")
  positions = await engine.get_open_positions()
  closed = 0
  for pos in positions:
    if is_macro_relevant_symbol(pos.symbol):
      continue
    price, _ = await fetch_polymarket_data(pos.symbol)
    if price <= 0:
      price = pos.current_price or pos.entry_price
    if price <= 0:
      continue
    result = await engine.sell(
      pos.symbol,
      price,
      "Close non-macro PM position (sports/noise filter)",
    )
    if result:
      from app.engines.learning_engine import analyze_losing_trade_for_symbol

      if result.get("is_winner") is False:
        await analyze_losing_trade_for_symbol(session, "polymarket", pos.symbol)
      closed += 1
  if closed:
    await session.commit()
  return closed


async def close_excess_commodities_positions(
  session: AsyncSession,
  max_open: int = 2,
) -> int:
  """Close commodities positions over gate cap — prefer profits and small losses over large losers."""
  from app.engines.gate_entry_guard import (
    commodities_effective_open_cap,
    get_gate_entry_tightening,
    in_shadow_graduation_nudge,
  )
  from app.engines.market_data import fetch_crypto_data, fetch_yfinance_data
  from app.engines.paper_trading import PaperTradingEngine
  from app.engines.profitability_gate import ProfitabilityGate

  gate = await get_gate_entry_tightening(session)
  base_cap = (
    gate.max_commodities_open_positions
    if gate.max_commodities_open_positions is not None
    else max_open
  )
  comm = (await ProfitabilityGate(session).evaluate_per_bot()).get("commodities") or {}
  graduation_nudge = (
    not await is_bot_paused(session, "commodities")
    and in_shadow_graduation_nudge(
      "commodities",
      comm.get("win_rate"),
      profit_factor=comm.get("profit_factor"),
      total_pnl=comm.get("total_pnl"),
    )
  )
  cap = commodities_effective_open_cap(
    base_cap,
    bot_type="commodities",
    graduation_nudge=graduation_nudge,
    shadow_mode=False,
  )
  if not isinstance(cap, int):
    cap = base_cap

  engine = PaperTradingEngine(session, "commodities")
  positions = await engine.get_open_positions()
  if graduation_nudge:
    excess = select_commodities_graduation_excess_trim_targets(positions, cap)
  else:
    excess = select_commodities_excess_trim_targets(positions, cap)
  if not excess:
    return 0

  closed = 0
  for pos in excess:
    if pos.symbol.endswith("USDT"):
      price, _ = await fetch_crypto_data(pos.symbol, "15m")
    else:
      price, _ = await fetch_yfinance_data(pos.symbol)
    if price <= 0:
      price = pos.current_price or pos.entry_price
    if price <= 0:
      continue
    u = _commodities_position_unrealized(pos)
    result = await engine.sell(
      pos.symbol,
      price,
      f"Close excess commodities position (cap {cap}, uPnL ${u:.2f})",
    )
    if result:
      from app.engines.learning_engine import analyze_losing_trade_for_symbol

      if result.get("is_winner") is False:
        await analyze_losing_trade_for_symbol(session, "commodities", pos.symbol)
      closed += 1
  if closed:
    await session.commit()
  return closed


SHADOW_TRIM_BOT_TYPES = ("crypto", "commodities")


async def close_excess_shadow_positions(session: AsyncSession) -> int:
  """Close worst-losing shadow positions when open count exceeds shadow cap."""
  from app.engines.gate_entry_guard import shadow_max_open_for_bot
  from app.engines.market_data import fetch_crypto_data, fetch_yfinance_data
  from app.engines.paper_trading import PaperTradingEngine
  from app.engines.profitability_gate import ProfitabilityGate

  per_bot = await ProfitabilityGate(session).evaluate_per_bot()
  closed = 0

  for bot_type in SHADOW_TRIM_BOT_TYPES:
    if not await is_bot_paused(session, bot_type):
      continue
    stats = per_bot.get(bot_type) or {}
    cap = shadow_max_open_for_bot(
      bot_type,
      shadow_mode=True,
      bot_win_rate=stats.get("win_rate"),
      profit_factor=stats.get("profit_factor"),
      total_pnl=stats.get("total_pnl"),
    )
    if cap is None:
      continue

    engine = PaperTradingEngine(session, bot_type)
    positions = await engine.get_open_positions()
    if len(positions) <= cap:
      continue

    def _unrealized(pos: Position) -> float:
      if pos.unrealized_pnl is not None:
        return float(pos.unrealized_pnl)
      if pos.current_price and pos.entry_price:
        return float((pos.current_price - pos.entry_price) * pos.quantity)
      return 0.0

    positions.sort(key=_unrealized)
    for pos in positions[: len(positions) - cap]:
      if pos.symbol.endswith("USDT"):
        price, _ = await fetch_crypto_data(pos.symbol, "15m")
      else:
        price, _ = await fetch_yfinance_data(pos.symbol)
      if price <= 0:
        price = pos.current_price or pos.entry_price
      if price <= 0:
        continue
      result = await engine.sell(
        pos.symbol,
        price,
        f"Close excess shadow position (cap {cap}, uPnL ${_unrealized(pos):.2f})",
      )
      if result:
        from app.engines.learning_engine import analyze_losing_trade_for_symbol

        if result.get("is_winner") is False:
          await analyze_losing_trade_for_symbol(session, bot_type, pos.symbol)
        closed += 1

  if closed:
    await session.commit()
  return closed
