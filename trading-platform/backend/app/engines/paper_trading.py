from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.engines.price_validation import is_price_consistent
from app.models.entities import BotState, Portfolio, Position, StrategyConfig, Trade


class PaperTradingEngine:
  """Simulates order execution. Real trading is blocked when paper_trading_only=True."""

  def __init__(self, session: AsyncSession, bot_type: str):
    self.session = session
    self.bot_type = bot_type

  async def get_portfolio(self) -> Portfolio:
    result = await self.session.execute(
      select(Portfolio).where(Portfolio.bot_type == self.bot_type)
    )
    portfolio = result.scalar_one_or_none()
    if not portfolio:
      portfolio = Portfolio(
        bot_type=self.bot_type,
        balance=settings.initial_balance,
        equity=settings.initial_balance,
      )
      self.session.add(portfolio)
      await self.session.commit()
      await self.session.refresh(portfolio)
    return portfolio

  async def get_strategy(self) -> StrategyConfig:
    result = await self.session.execute(
      select(StrategyConfig).where(StrategyConfig.bot_type == self.bot_type)
    )
    strategy = result.scalar_one_or_none()
    if not strategy:
      defaults = {}
      if self.bot_type == "polymarket":
        defaults = {
          "max_position_pct": settings.polymarket_max_position_pct,
          "stop_loss_pct": settings.polymarket_stop_loss_pct,
          "min_signal_score": 0.22,
          "take_profit_pct": 0.08,
        }
      strategy = StrategyConfig(bot_type=self.bot_type, **defaults)
      self.session.add(strategy)
      await self.session.commit()
      await self.session.refresh(strategy)
    return strategy

  async def get_open_positions(self) -> list[Position]:
    result = await self.session.execute(
      select(Position).where(
        Position.bot_type == self.bot_type,
        Position.is_open.is_(True),
      )
    )
    return list(result.scalars().all())

  async def get_position(self, symbol: str) -> Position | None:
    result = await self.session.execute(
      select(Position).where(
        Position.bot_type == self.bot_type,
        Position.symbol == symbol,
        Position.is_open.is_(True),
      )
    )
    return result.scalar_one_or_none()

  async def buy(
    self,
    symbol: str,
    price: float,
    signal_score: float,
    sentiment_score: float,
    reason: str,
    strategy: str = "composite",
  ) -> dict[str, Any] | None:
    if not settings.paper_trading_only:
      raise RuntimeError("Live trading disabled. Set PAPER_TRADING_ONLY=false only after verification.")

    portfolio = await self.get_portfolio()
    strategy_cfg = await self.get_strategy()

    existing = await self.get_position(symbol)
    if existing:
      return None

    position_value = portfolio.balance * strategy_cfg.max_position_pct
    if self.bot_type == "polymarket":
      position_value = min(
        settings.polymarket_max_position_usd,
        portfolio.balance * min(
          strategy_cfg.max_position_pct,
          settings.polymarket_max_position_pct,
        ),
      )
    quantity = position_value / price if price > 0 else 0
    if quantity <= 0 or position_value > portfolio.balance:
      return None

    stop_loss = price * (1 - strategy_cfg.stop_loss_pct)
    take_profit = price * (1 + strategy_cfg.take_profit_pct)

    position = Position(
      bot_type=self.bot_type,
      symbol=symbol,
      side="long",
      quantity=quantity,
      entry_price=price,
      current_price=price,
      stop_loss=stop_loss,
      take_profit=take_profit,
    )
    portfolio.balance -= position_value

    trade = Trade(
      bot_type=self.bot_type,
      symbol=symbol,
      side="long",
      action="buy",
      quantity=quantity,
      price=price,
      strategy=strategy,
      signal_score=signal_score,
      sentiment_score=sentiment_score,
      reason=reason,
    )

    self.session.add(position)
    self.session.add(trade)
    await self._update_bot_state(f"BUY {symbol} @ {price:.4f}")
    await self.session.commit()
    return {"action": "buy", "symbol": symbol, "price": price, "quantity": quantity}

  async def sell(
    self,
    symbol: str,
    price: float,
    reason: str,
  ) -> dict[str, Any] | None:
    position = await self.get_position(symbol)
    if not position:
      return None

    portfolio = await self.get_portfolio()
    entry_value = position.quantity * position.entry_price
    exit_value = position.quantity * price
    pnl = exit_value - entry_value
    pnl_pct = (pnl / entry_value) * 100 if entry_value else 0
    is_winner = pnl > 0

    portfolio.balance += exit_value
    portfolio.total_pnl += pnl
    portfolio.total_trades += 1
    if is_winner:
      portfolio.winning_trades += 1
    portfolio.win_rate = (
      portfolio.winning_trades / portfolio.total_trades if portfolio.total_trades else 0
    )

    position.is_open = False
    position.current_price = price
    position.unrealized_pnl = pnl

    trade = Trade(
      bot_type=self.bot_type,
      symbol=symbol,
      side="long",
      action="sell",
      quantity=position.quantity,
      price=price,
      pnl=pnl,
      pnl_pct=pnl_pct,
      is_winner=is_winner,
      reason=reason,
    )

    self.session.add(trade)
    await self._record_trade_pnl(pnl)
    await self._update_bot_state(f"SELL {symbol} @ {price:.4f} PnL: {pnl:.2f}")
    await self.session.commit()
    return {
      "action": "sell",
      "symbol": symbol,
      "price": price,
      "pnl": pnl,
      "pnl_pct": pnl_pct,
      "is_winner": is_winner,
    }

  async def update_positions(self, prices: dict[str, float]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    positions = await self.get_open_positions()

    for pos in positions:
      price = prices.get(pos.symbol)
      if not price:
        continue
      if not is_price_consistent(pos.entry_price, price):
        continue

      pos.current_price = price
      pos.unrealized_pnl = (price - pos.entry_price) * pos.quantity

      if pos.stop_loss and price <= pos.stop_loss:
        result = await self.sell(pos.symbol, price, f"Stop loss triggered at {price:.4f}")
        if result:
          actions.append(result)
      elif pos.take_profit and price >= pos.take_profit:
        result = await self.sell(pos.symbol, price, f"Take profit triggered at {price:.4f}")
        if result:
          actions.append(result)

    portfolio = await self.get_portfolio()
    open_positions = await self.get_open_positions()
    unrealized = sum(p.unrealized_pnl for p in open_positions)
    portfolio.equity = portfolio.balance + sum(
      p.quantity * p.current_price for p in open_positions
    )
    portfolio.updated_at = datetime.utcnow()
    await self.session.commit()
    return actions

  async def _update_bot_state(self, action: str) -> None:
    result = await self.session.execute(
      select(BotState).where(BotState.bot_type == self.bot_type)
    )
    state = result.scalar_one_or_none()
    if not state:
      state = BotState(bot_type=self.bot_type)
      self.session.add(state)
    state.last_action = action
    state.last_scan_at = datetime.utcnow()
    state.trades_today += 1
    state.updated_at = datetime.utcnow()

  async def _record_trade_pnl(self, pnl: float) -> None:
    result = await self.session.execute(
      select(BotState).where(BotState.bot_type == self.bot_type)
    )
    state = result.scalar_one_or_none()
    if state:
      state.pnl_today += pnl
      state.updated_at = datetime.utcnow()
