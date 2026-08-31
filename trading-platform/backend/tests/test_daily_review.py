"""Integration-style tests for run_daily_review upsert and pattern detection."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.engines.learning_engine import LearningEngine
from app.models.entities import DailyReview, Trade

OUTAGE_PATCH = "app.engines.platform_outage_log.platform_outage_patterns_for_review"


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

  with patch(OUTAGE_PATCH, new=AsyncMock(return_value=[])):
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

  with patch(OUTAGE_PATCH, new=AsyncMock(return_value=[])):
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

  with patch(OUTAGE_PATCH, new=AsyncMock(return_value=[])):
    review = asyncio.run(learner.run_daily_review("stocks_futures", "2026-08-30"))

  assert review.total_trades == 0
  assert "no trades" in (review.conclusions or "").lower()


def test_run_daily_review_includes_platform_outage_patterns():
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

  outage_patterns = ["Platform downtime 95min — missed session open with queued: AAPL"]
  with patch(OUTAGE_PATCH, new=AsyncMock(return_value=outage_patterns)):
    review = asyncio.run(learner.run_daily_review("stocks_futures", "2026-08-30"))

  assert "Platform downtime 95min" in (review.patterns_found or "")
  assert "AAPL" in (review.patterns_found or "")


def test_run_daily_review_detects_recurring_intel_loss_patterns():
  trades = [
    _sell_trade(
      id=1,
      pnl=-1.0,
      is_winner=False,
      reason="TikTok viral momentum buy",
    ),
    _sell_trade(
      id=2,
      symbol="PEPEUSDT",
      pnl=-0.9,
      is_winner=False,
      reason="Social hype entry after TikTok trend",
    ),
    _sell_trade(id=3, symbol="ETHUSDT", pnl=1.2, is_winner=True, signal_score=0.7),
  ]
  analysis_one = MagicMock(
    trade_id=1,
    root_cause="TikTok viral sentiment drove entry",
    lessons_learned="confirm with volume",
  )
  analysis_two = MagicMock(
    trade_id=2,
    root_cause="Weak technical signal at entry",
    lessons_learned="wait for confirmation",
  )
  session = AsyncMock()
  session.execute = AsyncMock(
    side_effect=[
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=trades)))),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[analysis_one, analysis_two])))),
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
    ]
  )
  session.commit = AsyncMock()
  session.add = MagicMock()

  learner = LearningEngine(session)
  learner._apply_adjustments = AsyncMock()

  with patch(OUTAGE_PATCH, new=AsyncMock(return_value=[])):
    review = asyncio.run(learner.run_daily_review("crypto", "2026-08-30"))

  assert "tiktok" in (review.patterns_found or "").lower()
  assert "intel confirmation" in (review.patterns_found or "").lower()
  learner._apply_adjustments.assert_awaited()


def test_run_daily_review_detects_recurring_newsapi_intel_loss_patterns():
  trade_day = datetime(2026, 8, 31, 15, 0, 0)
  trades = [
    _sell_trade(
      id=11,
      bot_type="stocks_futures",
      pnl=-1.1,
      is_winner=False,
      reason="newsapi headline breakout",
      executed_at=trade_day,
    ),
    _sell_trade(
      id=12,
      bot_type="stocks_futures",
      symbol="NVDA",
      pnl=-0.85,
      is_winner=False,
      reason="Long on earnings headline",
      executed_at=trade_day,
    ),
    _sell_trade(
      id=13,
      bot_type="stocks_futures",
      symbol="MSFT",
      pnl=1.0,
      is_winner=True,
      signal_score=0.72,
      executed_at=trade_day,
    ),
  ]
  analysis_one = MagicMock(
    trade_id=11,
    root_cause="News headline influenced entry without local technical confirmation",
    lessons_learned="wait for TA alignment",
  )
  analysis_two = MagicMock(
    trade_id=12,
    root_cause="Entered long against bearish news headline intel",
    lessons_learned="align with headline sentiment",
  )
  session = AsyncMock()
  session.execute = AsyncMock(
    side_effect=[
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=trades)))),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[analysis_one, analysis_two])))),
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
    ]
  )
  session.commit = AsyncMock()
  session.add = MagicMock()

  learner = LearningEngine(session)
  learner._apply_adjustments = AsyncMock()

  with patch(OUTAGE_PATCH, new=AsyncMock(return_value=[])):
    review = asyncio.run(learner.run_daily_review("stocks_futures", "2026-08-31"))

  assert "news headline" in (review.patterns_found or "").lower()
  assert "intel confirmation" in (review.patterns_found or "").lower()


def test_run_daily_review_detects_recurring_axiom_intel_loss_patterns():
  trade_day = datetime(2026, 8, 31, 16, 0, 0)
  trades = [
    _sell_trade(
      id=21,
      bot_type="crypto",
      symbol="PEPEUSDT",
      pnl=-1.0,
      is_winner=False,
      reason="axiom wallet mirror buy",
      executed_at=trade_day,
    ),
    _sell_trade(
      id=22,
      bot_type="crypto",
      symbol="BONKUSDT",
      pnl=-0.9,
      is_winner=False,
      reason="axiom multi-wallet signal",
      executed_at=trade_day,
    ),
    _sell_trade(
      id=23,
      bot_type="crypto",
      symbol="ETHUSDT",
      pnl=1.1,
      is_winner=True,
      signal_score=0.7,
      executed_at=trade_day,
    ),
  ]
  analysis_one = MagicMock(
    trade_id=21,
    root_cause="Entry aligned with axiom.trade multi-wallet smart-money signal",
    lessons_learned="confirm liquidity",
  )
  analysis_two = MagicMock(
    trade_id=22,
    root_cause="Weak technical signal at entry",
    lessons_learned="wait for confirmation",
  )
  session = AsyncMock()
  session.execute = AsyncMock(
    side_effect=[
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=trades)))),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[analysis_one, analysis_two])))),
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
    ]
  )
  session.commit = AsyncMock()
  session.add = MagicMock()

  learner = LearningEngine(session)
  learner._apply_adjustments = AsyncMock()

  with patch(OUTAGE_PATCH, new=AsyncMock(return_value=[])):
    review = asyncio.run(learner.run_daily_review("crypto", "2026-08-31"))

  assert "axiom" in (review.patterns_found or "").lower()
  assert "intel confirmation" in (review.patterns_found or "").lower()


def test_run_daily_review_detects_recurring_hyperliquid_intel_loss_patterns():
  trade_day = datetime(2026, 8, 31, 17, 0, 0)
  trades = [
    _sell_trade(
      id=31,
      bot_type="crypto",
      symbol="WIFUSDT",
      pnl=-1.0,
      is_winner=False,
      reason="HL perp momentum entry",
      executed_at=trade_day,
    ),
    _sell_trade(
      id=32,
      bot_type="crypto",
      symbol="BONKUSDT",
      pnl=-0.95,
      is_winner=False,
      reason="Hyperliquid funding flip long",
      executed_at=trade_day,
    ),
    _sell_trade(
      id=33,
      bot_type="crypto",
      symbol="ETHUSDT",
      pnl=1.0,
      is_winner=True,
      signal_score=0.72,
      executed_at=trade_day,
    ),
  ]
  analysis_one = MagicMock(
    trade_id=31,
    root_cause="Hyperliquid perp intel influenced entry without local confirmation",
    lessons_learned="watch funding rate flips",
  )
  analysis_two = MagicMock(
    trade_id=32,
    root_cause="Weak technical signal at entry",
    lessons_learned="wait for TA alignment",
  )
  session = AsyncMock()
  session.execute = AsyncMock(
    side_effect=[
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=trades)))),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[analysis_one, analysis_two])))),
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
    ]
  )
  session.commit = AsyncMock()
  session.add = MagicMock()

  learner = LearningEngine(session)
  learner._apply_adjustments = AsyncMock()

  with patch(OUTAGE_PATCH, new=AsyncMock(return_value=[])):
    review = asyncio.run(learner.run_daily_review("crypto", "2026-08-31"))

  assert "hyperliquid" in (review.patterns_found or "").lower()
  assert "intel confirmation" in (review.patterns_found or "").lower()


def test_run_daily_review_detects_recurring_wallet_tracker_intel_loss_patterns():
  trade_day = datetime(2026, 8, 31, 18, 0, 0)
  trades = [
    _sell_trade(
      id=41,
      bot_type="crypto",
      symbol="PEPEUSDT",
      pnl=-1.1,
      is_winner=False,
      reason="Whale wallet mirror buy",
      executed_at=trade_day,
    ),
    _sell_trade(
      id=42,
      bot_type="crypto",
      symbol="SOLUSDT",
      pnl=-0.88,
      is_winner=False,
      reason="wallet_tracker accumulation signal",
      executed_at=trade_day,
    ),
    _sell_trade(
      id=43,
      bot_type="crypto",
      symbol="BTCUSDT",
      pnl=1.2,
      is_winner=True,
      signal_score=0.74,
      executed_at=trade_day,
    ),
  ]
  analysis_one = MagicMock(
    trade_id=41,
    root_cause="Whale wallet tracker signal preceded loss without TA confirmation",
    lessons_learned="wait for local signal alignment",
  )
  analysis_two = MagicMock(
    trade_id=42,
    root_cause="Weak technical signal at entry",
    lessons_learned="confirm volume before sizing",
  )
  session = AsyncMock()
  session.execute = AsyncMock(
    side_effect=[
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=trades)))),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[analysis_one, analysis_two])))),
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
    ]
  )
  session.commit = AsyncMock()
  session.add = MagicMock()

  learner = LearningEngine(session)
  learner._apply_adjustments = AsyncMock()

  with patch(OUTAGE_PATCH, new=AsyncMock(return_value=[])):
    review = asyncio.run(learner.run_daily_review("crypto", "2026-08-31"))

  assert "whale wallet" in (review.patterns_found or "").lower()
  assert "intel confirmation" in (review.patterns_found or "").lower()
