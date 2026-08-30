"""Tests for post-mortem idempotency and bot-specific rules."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.engines.learning_engine import LearningEngine


def _trade(**overrides):
  trade = MagicMock()
  trade.id = 99
  trade.bot_type = "stocks_futures"
  trade.symbol = "AAPL"
  trade.pnl = -2.0
  trade.pnl_pct = -0.8
  trade.signal_score = 0.42
  trade.sentiment_score = 0.1
  trade.side = "long"
  trade.reason = "Sell signal: MACD bearish crossover"
  trade.executed_at = datetime(2026, 8, 29, 20, 0, 0)
  for key, value in overrides.items():
    setattr(trade, key, value)
  return trade


def test_analyze_losing_trade_returns_existing_analysis():
  prior = MagicMock()
  session = AsyncMock()
  session.execute = AsyncMock(
    return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=prior))
  )

  learner = LearningEngine(session)
  result = asyncio.run(learner.analyze_losing_trade(_trade()))

  assert result is prior


def test_analyze_losing_trade_flags_stocks_macd_bearish():
  session = AsyncMock()
  session.execute = AsyncMock(
    side_effect=[
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ]
  )
  session.commit = AsyncMock()
  session.add = MagicMock()

  learner = LearningEngine(session)
  learner._get_market_context = AsyncMock(return_value="context")
  learner._had_fomo_intel = AsyncMock(return_value=False)
  learner._apply_adjustments = AsyncMock()
  learner.run_daily_review = AsyncMock(return_value=MagicMock())

  with patch("app.ws_manager.push_live_update", new_callable=AsyncMock):
    analysis = asyncio.run(learner.analyze_losing_trade(_trade()))

  assert "macd" in analysis.root_cause.lower()
  learner._apply_adjustments.assert_awaited_once()


def test_analyze_losing_trade_flags_commodities_weekend():
  session = AsyncMock()
  session.execute = AsyncMock(
    side_effect=[
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ]
  )
  session.commit = AsyncMock()
  session.add = MagicMock()

  trade = _trade(
    bot_type="commodities",
    symbol="GC=F",
    reason="Weekend gap exit on gold futures",
  )

  learner = LearningEngine(session)
  learner._get_market_context = AsyncMock(return_value="context")
  learner._had_fomo_intel = AsyncMock(return_value=False)
  learner._apply_adjustments = AsyncMock()
  learner.run_daily_review = AsyncMock(return_value=MagicMock())

  with patch("app.ws_manager.push_live_update", new_callable=AsyncMock):
    analysis = asyncio.run(learner.analyze_losing_trade(trade))

  assert "weekend" in analysis.root_cause.lower()


def test_analyze_losing_trade_flags_polymarket_overbought():
  session = AsyncMock()
  session.execute = AsyncMock(
    side_effect=[
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ]
  )
  session.commit = AsyncMock()
  session.add = MagicMock()

  trade = _trade(
    bot_type="polymarket",
    symbol="PM:trump-tariff",
    reason="PM:Yes price overbought (>0.72); Intel bullish (+0.35)",
    signal_score=0.38,
  )

  learner = LearningEngine(session)
  learner._get_market_context = AsyncMock(return_value="context")
  learner._had_fomo_intel = AsyncMock(return_value=False)
  learner._had_source_intel = AsyncMock(return_value=False)
  learner._apply_adjustments = AsyncMock()
  learner.run_daily_review = AsyncMock(return_value=MagicMock())

  with patch("app.ws_manager.push_live_update", new_callable=AsyncMock):
    analysis = asyncio.run(learner.analyze_losing_trade(trade))

  assert "overbought" in analysis.root_cause.lower()
  assert "0.72" in analysis.strategy_adjustment
