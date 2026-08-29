"""Tests for post-mortems on migration/trim forced closes."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.engines.learning_engine import analyze_losing_trade_for_symbol


def test_analyze_losing_trade_for_symbol_runs_post_mortem():
  trade = MagicMock()
  trade.is_winner = False

  session = AsyncMock()
  session.execute = AsyncMock(
    return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=trade))
  )

  analysis = MagicMock()
  learner = MagicMock()
  learner.analyze_losing_trade = AsyncMock(return_value=analysis)

  with patch("app.engines.learning_engine.LearningEngine", return_value=learner):
    result = asyncio.run(analyze_losing_trade_for_symbol(session, "commodities", "CL=F"))

  assert result is analysis
  learner.analyze_losing_trade.assert_awaited_once_with(trade)


def test_analyze_losing_trade_for_symbol_skips_winners():
  trade = MagicMock()
  trade.is_winner = True

  session = AsyncMock()
  session.execute = AsyncMock(
    return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=trade))
  )

  with patch("app.engines.learning_engine.LearningEngine") as LearnerCls:
    result = asyncio.run(analyze_losing_trade_for_symbol(session, "crypto", "BTCUSDT"))

  assert result is None
  LearnerCls.return_value.analyze_losing_trade.assert_not_called()
