import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.engines.integration_signals import get_integration_boost
from app.engines.learning_engine import LearningEngine
from app.engines.market_data import fetch_crypto_data, fetch_yfinance_data
from app.engines.polymarket_data import (
  canonical_pm_symbol,
  fetch_polymarket_data,
  find_pm_position,
  get_market_meta,
  get_polymarket_symbols,
)
from app.engines.polymarket_signals import analyze_polymarket
from app.engines.paper_trading import PaperTradingEngine
from app.engines.price_validation import is_price_sane
from app.engines.signal_engine import SignalEngine
from app.models.entities import BotState, IntelligenceItem, Trade


class BaseBot(ABC):
  bot_type: str = "base"
  scan_interval: int = 30

  def __init__(self):
    self.signal_engine = SignalEngine()
    self.running = False

  @abstractmethod
  async def get_symbols(self) -> list[str]:
    pass

  @abstractmethod
  async def fetch_price_data(self, symbol: str) -> tuple[float, pd.DataFrame | None]:
    pass

  async def get_sentiment_score(self, symbol: str) -> float:
    async with SessionLocal() as session:
      clean = symbol.replace("USDT", "").replace("=F", "").replace("=X", "")
      result = await session.execute(
        select(IntelligenceItem)
        .where(IntelligenceItem.symbols_mentioned.contains(clean))
        .order_by(IntelligenceItem.fetched_at.desc())
        .limit(10)
      )
      items = list(result.scalars().all())
      if not items:
        result = await session.execute(
          select(IntelligenceItem).order_by(IntelligenceItem.fetched_at.desc()).limit(20)
        )
        items = list(result.scalars().all())

      if not items:
        return 0.0
      return sum(i.sentiment for i in items) / len(items)

  async def scan_and_trade(self) -> list[dict]:
    actions: list[dict] = []
    symbols = await self.get_symbols()

    async with SessionLocal() as session:
      from app.engines.platform_settings import is_bot_paused

      if await is_bot_paused(session, self.bot_type):
        await self._record_scan_result(len(symbols), [], "paused — no new trades")
        return []

      engine = PaperTradingEngine(session, self.bot_type)
      strategy = await engine.get_strategy()
      strategy_params = {
        "rsi_oversold": strategy.rsi_oversold,
        "rsi_overbought": strategy.rsi_overbought,
      }
      weights = {
        "technical_weight": strategy.technical_weight,
        "sentiment_weight": strategy.sentiment_weight,
        "momentum_weight": strategy.momentum_weight,
      }

      prices: dict[str, float] = {}

      for symbol in symbols:
        price, df = await self.fetch_price_data(symbol)
        if price <= 0 or not is_price_sane(symbol, price):
          continue
        prices[symbol] = price

        signal = self.signal_engine.analyze(symbol, df, strategy_params)
        sentiment = await self.get_sentiment_score(symbol)
        composite = self.signal_engine.composite_score(signal.score, sentiment, weights)
        integration_boost, integration_reason = await get_integration_boost(session, symbol)
        composite = max(0.0, composite + integration_boost)

        position = await engine.get_position(symbol)

        if position:
          if signal.direction == "sell" or integration_boost < -0.1:
            reason = f"Sell signal: {signal.reason}"
            if integration_reason:
              reason += f" | Integrations: {integration_reason}"
            result = await engine.sell(symbol, price, reason)
            if result:
              actions.append(result)
              if result.get("is_winner") is False:
                await self._analyze_loss(session, symbol)
          continue

        if (
          signal.direction == "buy"
          and composite >= strategy.min_signal_score
          and sentiment + integration_boost >= strategy.min_sentiment_score - 0.5
        ):
          reason = f"Signal:{signal.score:.2f} Sentiment:{sentiment:.2f}"
          if integration_reason:
            reason += f" Integrations:{integration_boost:+.2f} ({integration_reason})"
          reason += f" | {signal.reason}"
          result = await engine.buy(
            symbol, price, composite, sentiment, reason, strategy=f"v{strategy.version}"
          )
          if result:
            actions.append(result)

      stop_actions = await engine.update_positions(prices)
      actions.extend(stop_actions)

      for action in stop_actions:
        if action.get("is_winner") is False:
          await self._analyze_loss(session, action.get("symbol", ""))

    await self._record_scan_result(len(symbols), actions)

    if actions:
      from app.ws_manager import broadcast_trade, push_live_update

      for action in actions:
        await broadcast_trade({**action, "bot_type": self.bot_type})
      await push_live_update()

    return actions

  async def _analyze_loss(self, session, symbol: str) -> None:
    result = await session.execute(
      select(Trade)
      .where(Trade.bot_type == self.bot_type, Trade.symbol == symbol, Trade.action == "sell")
      .order_by(Trade.executed_at.desc())
      .limit(1)
    )
    trade = result.scalar_one_or_none()
    if trade and trade.is_winner is False:
      learner = LearningEngine(session)
      await learner.analyze_losing_trade(trade)

  async def _record_scan_heartbeat(self) -> None:
    async with SessionLocal() as session:
      result = await session.execute(
        select(BotState).where(BotState.bot_type == self.bot_type)
      )
      state = result.scalar_one_or_none()
      if not state:
        state = BotState(bot_type=self.bot_type, status="running")
        session.add(state)
      state.last_scan_at = datetime.utcnow()
      state.status = "running"
      if state.last_action.startswith("Paper reset"):
        state.last_action = "Scanning markets"
      state.updated_at = datetime.utcnow()
      await session.commit()

  async def _record_scan_result(self, symbol_count: int, actions: list[dict], detail: str = "") -> None:
    trade_actions = [a for a in actions if a.get("action") in ("buy", "sell")]
    if trade_actions:
      return
    async with SessionLocal() as session:
      result = await session.execute(
        select(BotState).where(BotState.bot_type == self.bot_type)
      )
      state = result.scalar_one_or_none()
      if not state:
        return
      if state.last_action.startswith(("BUY", "SELL", "PM:")):
        return
      summary = detail or "watching for signals"
      state.last_action = f"Scanned {symbol_count} symbols — {summary}"[:200]
      state.updated_at = datetime.utcnow()
      await session.commit()

  async def _record_scan_failure(self, error: str) -> None:
    async with SessionLocal() as session:
      result = await session.execute(
        select(BotState).where(BotState.bot_type == self.bot_type)
      )
      state = result.scalar_one_or_none()
      if not state:
        return
      state.last_action = f"Scan error — {error[:120]}"
      state.updated_at = datetime.utcnow()
      await session.commit()

  async def run_loop(self) -> None:
    self.running = True
    while self.running:
      try:
        await self._record_scan_heartbeat()
        await self.scan_and_trade()
      except Exception as e:
        print(f"[{self.bot_type}] Error in scan: {e}")
        await self._record_scan_failure(str(e))
      await asyncio.sleep(self.scan_interval)

  def stop(self) -> None:
    self.running = False


class CryptoBot(BaseBot):
  bot_type = "crypto"
  scan_interval = 15

  async def get_symbols(self) -> list[str]:
    return [s.strip() for s in settings.crypto_symbols.split(",")]

  async def fetch_price_data(self, symbol: str) -> tuple[float, pd.DataFrame | None]:
    return await fetch_crypto_data(symbol, "5m")


class StocksFuturesBot(BaseBot):
  bot_type = "stocks_futures"
  scan_interval = 45

  async def get_symbols(self) -> list[str]:
    stocks = [s.strip() for s in settings.stock_symbols.split(",")]
    futures = [s.strip() for s in settings.futures_symbols.split(",")]
    return stocks + futures

  async def fetch_price_data(self, symbol: str) -> tuple[float, pd.DataFrame | None]:
    return await fetch_yfinance_data(symbol)

  def _in_us_session(self) -> bool:
    now = datetime.utcnow()
    if now.weekday() >= 5:
      return False
    minutes = now.hour * 60 + now.minute
    # US regular session ~9:30–16:00 ET (13:30–21:00 UTC); extend 30m for closes
    return 13 * 60 + 30 <= minutes <= 21 * 60 + 30

  async def scan_and_trade(self) -> list[dict]:
    symbols = await self.get_symbols()
    if not self._in_us_session():
      await self._record_scan_result(len(symbols), [], "outside US market hours")
      return []
    return await super().scan_and_trade()


class CommoditiesBot(BaseBot):
  bot_type = "commodities"
  scan_interval = 30

  async def get_symbols(self) -> list[str]:
    yf_symbols = [s.strip() for s in settings.commodity_symbols.split(",")]
    crypto_fallback = ["PAXGUSDT", "XAUUSDT"]
    return yf_symbols + crypto_fallback

  async def fetch_price_data(self, symbol: str) -> tuple[float, pd.DataFrame | None]:
    if symbol.endswith("USDT"):
      return await fetch_crypto_data(symbol, "15m")
    return await fetch_yfinance_data(symbol)


class PolymarketBot(BaseBot):
  """Paper-trades Polymarket Yes shares — politics, crypto, sports, geopolitics, weather, etc."""

  bot_type = "polymarket"
  scan_interval = 45
  _symbol_cooldown_until: dict[str, datetime] = {}

  async def get_symbols(self) -> list[str]:
    return await get_polymarket_symbols()

  async def fetch_price_data(self, symbol: str) -> tuple[float, pd.DataFrame | None]:
    return await fetch_polymarket_data(symbol)

  def _register_symbol_cooldown(self, symbol: str, *, after_loss: bool) -> None:
    if not symbol:
      return
    seconds = (
      settings.polymarket_loss_cooldown_seconds
      if after_loss
      else settings.polymarket_reentry_cooldown_seconds
    )
    self._symbol_cooldown_until[symbol] = datetime.utcnow() + timedelta(seconds=seconds)

  async def scan_and_trade(self) -> list[dict]:
    actions: list[dict] = []
    symbols = await self.get_symbols()
    buy_candidates = 0
    best_buy_score = 0.0
    skipped = 0

    try:
      async with SessionLocal() as session:
        from app.engines.platform_settings import is_bot_paused

        if await is_bot_paused(session, self.bot_type):
          await self._record_scan_result(len(symbols), [], "paused — no new trades")
          return []

        engine = PaperTradingEngine(session, self.bot_type)
        strategy = await engine.get_strategy()
        min_score = strategy.min_signal_score
        open_positions = await engine.get_open_positions()
        pm_open = len(open_positions)
        prices: dict[str, float] = {}
        held_symbols = [p.symbol for p in open_positions]
        scan_symbols = list(dict.fromkeys(held_symbols + symbols))

        for symbol in scan_symbols:
          try:
            price, df = await self.fetch_price_data(symbol)
            if price <= 0 or not is_price_sane(symbol, price):
              continue

            meta = await get_market_meta(symbol)
            symbol = canonical_pm_symbol(symbol, meta)
            prices[symbol] = price

            question = (meta or {}).get("question", symbol)
            pm_sig = await analyze_polymarket(session, symbol, price, df, question)
            integration_boost, integration_reason = await get_integration_boost(session, symbol)
            composite = pm_sig.score + integration_boost

            position = find_pm_position(open_positions, symbol)

            if position:
              if position.stop_loss and price <= position.stop_loss:
                exit_price = position.stop_loss
                result = await engine.sell(
                  position.symbol,
                  exit_price,
                  f"Stop loss triggered at {exit_price:.4f}",
                )
                if result:
                  actions.append(result)
                  if result.get("is_winner") is False:
                    await self._analyze_loss(session, symbol)
                  self._register_symbol_cooldown(symbol, after_loss=result.get("is_winner") is False)
                continue

              opened = position.opened_at
              if opened and opened.tzinfo is not None:
                opened = opened.replace(tzinfo=None)
              held_seconds = (datetime.utcnow() - opened).total_seconds() if opened else 9999
              min_hold_seconds = settings.polymarket_min_hold_seconds
              allow_signal_exit = (
                held_seconds >= min_hold_seconds
                and pm_sig.direction == "sell"
                and pm_sig.sentiment <= 0.05
                and (price >= 0.60 or (df is not None and len(df) >= 15))
              )
              if allow_signal_exit or integration_boost < -0.15:
                reason = f"PM exit: {pm_sig.reason}"
                if integration_reason:
                  reason += f" | {integration_reason}"
                result = await engine.sell(position.symbol, price, reason)
                if result:
                  actions.append(result)
                  won = result.get("is_winner")
                  if won is False:
                    await self._analyze_loss(session, symbol)
                  self._register_symbol_cooldown(symbol, after_loss=won is False)
              continue

            if symbol not in symbols:
              continue

            if find_pm_position(open_positions, symbol):
              continue

            cooldown = self._symbol_cooldown_until.get(symbol)
            if cooldown and datetime.utcnow() < cooldown:
              continue

            if pm_open >= settings.polymarket_max_open_positions:
              continue

            if pm_sig.direction == "buy":
              buy_candidates += 1
              best_buy_score = max(best_buy_score, composite)

            if (
              pm_sig.direction == "buy"
              and composite >= min_score
              and pm_sig.sentiment + integration_boost >= strategy.min_sentiment_score - 0.35
            ):
              reason = f"PM:{pm_sig.reason}"
              if integration_reason:
                reason += f" | {integration_reason}"
              result = await engine.buy(
                symbol,
                price,
                composite,
                pm_sig.sentiment,
                reason,
                strategy=f"v{strategy.version}",
              )
              if result:
                actions.append(result)
                pm_open += 1
          except Exception as e:
            skipped += 1
            print(f"[polymarket] skip {symbol}: {e}")

        stop_actions = await engine.update_positions(prices)
        actions.extend(stop_actions)

        for action in stop_actions:
          if action.get("is_winner") is False:
            sym = action.get("symbol", "")
            await self._analyze_loss(session, sym)
            self._register_symbol_cooldown(sym, after_loss=True)
          else:
            sym = action.get("symbol", "")
            self._register_symbol_cooldown(sym, after_loss=False)
    except Exception as e:
      await self._record_scan_result(len(symbols), actions, f"failed — {e}")
      raise

    pm_detail = (
      f"{buy_candidates} buy signals (best {best_buy_score:.2f})"
      if buy_candidates
      else "no qualifying entries"
    )
    if skipped:
      pm_detail += f", {skipped} skipped"
    await self._record_scan_result(len(symbols), actions, pm_detail)

    if actions:
      from app.ws_manager import broadcast_trade, push_live_update

      for action in actions:
        await broadcast_trade({**action, "bot_type": self.bot_type})
      await push_live_update()

    return actions
