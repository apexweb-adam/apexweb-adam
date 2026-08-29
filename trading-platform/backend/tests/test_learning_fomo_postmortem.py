"""Tests for fomo-aware losing trade post-mortems."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.engines.learning_engine import LearningEngine


def test_analyze_losing_trade_flags_weak_fomo_confirmation():
  session = AsyncMock()
  session.commit = AsyncMock()
  session.add = MagicMock()
  session.execute = AsyncMock(
    return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
  )

  trade = MagicMock()
  trade.id = 42
  trade.bot_type = "crypto"
  trade.symbol = "PEPEUSDT"
  trade.pnl = -0.5
  trade.pnl_pct = -0.1
  trade.signal_score = 0.42
  trade.sentiment_score = 0.62
  trade.side = "long"
  trade.reason = "[shadow] Intel:[fomo:+0.62] Integrations:+0.15 (fomo:+0.62)"
  trade.executed_at = datetime(2026, 8, 29, 12, 0, 0)

  learner = LearningEngine(session)
  learner._get_market_context = AsyncMock(return_value="[fomo] legend buy PEPE")
  learner._had_fomo_intel = AsyncMock(return_value=True)
  learner._apply_adjustments = AsyncMock()
  learner.run_daily_review = AsyncMock(return_value=MagicMock())

  with patch("app.ws_manager.push_live_update", new_callable=AsyncMock):
    analysis = asyncio.run(learner.analyze_losing_trade(trade))

  assert "fomo" in analysis.root_cause.lower()
  assert "technical" in analysis.root_cause.lower() or "technical" in analysis.strategy_adjustment.lower()
  learner._apply_adjustments.assert_called_once()
