"""Tests for intra-day daily review refresh after losing trades."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.engines.learning_engine import LearningEngine


def test_analyze_losing_trade_refreshes_daily_review():
  session = AsyncMock()
  session.commit = AsyncMock()
  session.add = MagicMock()

  trade = MagicMock()
  trade.id = 1
  trade.bot_type = "commodities"
  trade.symbol = "CL=F"
  trade.pnl = -1.0
  trade.pnl_pct = -0.5
  trade.signal_score = 0.4
  trade.sentiment_score = 0.1
  trade.side = "long"
  trade.reason = "test"
  trade.executed_at = datetime(2026, 8, 29, 12, 0, 0)

  learner = LearningEngine(session)
  learner._get_market_context = AsyncMock(return_value="context")
  learner._had_fomo_intel = AsyncMock(return_value=False)
  learner._apply_adjustments = AsyncMock()
  learner.run_daily_review = AsyncMock(return_value=MagicMock())

  with patch("app.ws_manager.push_live_update", new_callable=AsyncMock):
    import asyncio

    asyncio.run(learner.analyze_losing_trade(trade))

  learner.run_daily_review.assert_called_once_with("commodities", "2026-08-29")
