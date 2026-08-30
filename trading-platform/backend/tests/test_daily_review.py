"""Integration-style tests for run_daily_review upsert and pattern detection."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.engines.learning_engine import LearningEngine
from app.models.entities import DailyReview, Trade


def _sell_trade(**overrides):
  trade = MagicMock(spec=Trade)
  trade.action = "sell"
  trade.bot_type = "crypto"
  trade.symbol = "BTCUSDT"
  trade.pnl = -1.5
  trade.is_winner = False
  trade.signal_score = 0.35
  trade.sentiment_score = -0.1
  trade.side = "long"
  trade.reason = "weak signal exit"
  trade.executed_at = datetime(2026, 8, 30, 14, 0, 0)
  for key, value in overrides.items():
    setattr(trade, key, value)
  return trade


def test_run_daily_review_creates_review_with_patterns():
  trades = [
    _sell_trade(pnl=-1.0, is_winner=False),
    _sell_trade(symbol="ETHUSDT", pnl=2.0, is_winner=True, signal_score=0.7),
    _sell_trade(symbol="SOLUSDT", pnl=-0.8, is_winner=False, signal_score=0.4),
  ]
  session = AsyncMock()
  session.execute = AsyncMock(
    side_effect=[
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=trades)))),
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
    ]
  )
  session.commit = AsyncMock()
  session.add = MagicMock()

  learner = LearningEngine(session)
  learner._apply_adjustments = AsyncMock()

  review = asyncio.run(learner.run_daily_review("crypto", "2026-08-30"))

  assert review.total_trades == 3
  assert review.losing_trades == 2
  assert review.net_pnl == pytest.approx(0.2)
  assert "weak signals" in (review.patterns_found or "").lower()
  session.add.assert_called_once()


def test_run_daily_review_upserts_existing_row():
  existing = DailyReview(
    bot_type="polymarket",
    review_date="2026-08-30",
    total_trades=1,
    losing_trades=1,
    total_loss=-0.5,
    total_profit=0.0,
    net_pnl=-0.5,
    win_rate=0.0,
    patterns_found="old",
    conclusions="old",
    strategy_changes="old",
  )
  trades = [
    _sell_trade(
      bot_type="polymarket",
      symbol="PM:trump-win-2028",
      pnl=-0.6,
      is_winner=False,
      reason="PM:Yes price overbought (>0.72)",
    ),
    _sell_trade(
      bot_type="polymarket",
      symbol="PM:fed-rate-cut",
      pnl=0.4,
      is_winner=True,
      reason="PM:take profit",
    ),
  ]
  session = AsyncMock()
  session.execute = AsyncMock(
    side_effect=[
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=trades)))),
      MagicMock(scalar_one_or_none=MagicMock(return_value=existing)),
    ]
  )
  session.commit = AsyncMock()

  learner = LearningEngine(session)
  learner._apply_adjustments = AsyncMock()

  review = asyncio.run(learner.run_daily_review("polymarket", "2026-08-30"))

  assert review is existing
  assert review.total_trades == 2
  assert "overbought" in (review.patterns_found or "").lower()
  session.add.assert_not_called()


def test_run_daily_review_empty_day():
  session = AsyncMock()
  session.execute = AsyncMock(
    side_effect=[
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
    ]
  )
  session.commit = AsyncMock()
  session.add = MagicMock()

  learner = LearningEngine(session)
  learner._apply_adjustments = AsyncMock()

  review = asyncio.run(learner.run_daily_review("stocks_futures", "2026-08-30"))

  assert review.total_trades == 0
  assert "no trades" in (review.conclusions or "").lower()
