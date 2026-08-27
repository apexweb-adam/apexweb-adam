import asyncio
from abc import ABC, abstractmethod
from datetime import datetime

import pandas as pd
from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.engines.learning_engine import LearningEngine
from app.engines.market_data import fetch_crypto_data, fetch_yfinance_data
from app.engines.paper_trading import PaperTradingEngine
from app.engines.price_validation import is_price_sane
from app.engines.signal_engine import SignalEngine
from app.models.entities import IntelligenceItem, Trade


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

        position = await engine.get_position(symbol)

        if position:
          if signal.direction == "sell":
            result = await engine.sell(symbol, price, f"Sell signal: {signal.reason}")
            if result:
              actions.append(result)
              if not result.get("is_winner", True):
                await self._analyze_loss(session, symbol)
          continue

        if (
          signal.direction == "buy"
          and composite >= strategy.min_signal_score
          and sentiment >= strategy.min_sentiment_score - 0.5
        ):
          reason = f"Signal:{signal.score:.2f} Sentiment:{sentiment:.2f} | {signal.reason}"
          result = await engine.buy(
            symbol, price, composite, sentiment, reason, strategy=f"v{strategy.version}"
          )
          if result:
            actions.append(result)

      stop_actions = await engine.update_positions(prices)
      actions.extend(stop_actions)

      for action in stop_actions:
        if not action.get("is_winner", True):
          await self._analyze_loss(session, action.get("symbol", ""))

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

  async def run_loop(self) -> None:
    self.running = True
    while self.running:
      try:
        await self.scan_and_trade()
      except Exception as e:
        print(f"[{self.bot_type}] Error in scan: {e}")
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
  scan_interval = 60

  async def get_symbols(self) -> list[str]:
    stocks = [s.strip() for s in settings.stock_symbols.split(",")]
    futures = [s.strip() for s in settings.futures_symbols.split(",")]
    return stocks + futures

  async def fetch_price_data(self, symbol: str) -> tuple[float, pd.DataFrame | None]:
    return await fetch_yfinance_data(symbol)

  async def scan_and_trade(self) -> list[dict]:
    now = datetime.utcnow()
    weekday = now.weekday()
    hour = now.hour
    minute = now.minute
    if weekday >= 5:
      return []
    # US regular session ~9:30–16:00 ET (13:30–21:00 UTC summer / 14:30–22:00 UTC winter)
    minutes = hour * 60 + minute
    if minutes < 13 * 60 + 30 or minutes > 21 * 60:
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
