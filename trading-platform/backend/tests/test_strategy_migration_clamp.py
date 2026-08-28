"""Tests for verification strategy clamping."""

from unittest.mock import AsyncMock, MagicMock, patch

from app.engines.strategy_migration import clamp_verification_strategy_params


def test_clamp_resets_sentiment_at_ceiling():
  config = MagicMock()
  config.bot_type = "stocks_futures"
  config.min_signal_score = 0.28
  config.min_sentiment_score = 0.15
  config.version = 1

  session = AsyncMock()
  session.execute = AsyncMock(
    return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[config]))))
  )
  session.commit = AsyncMock()

  async def _run():
    with patch("app.engines.profitability_gate.ProfitabilityGate") as GateCls:
      GateCls.MIN_WIN_RATE = 0.55
      GateCls.return_value.evaluate = AsyncMock(
        return_value={"total_trades": 5, "win_rate": 1.0}
      )
      return await clamp_verification_strategy_params(session)

  import asyncio

  updated = asyncio.run(_run())

  assert updated == 1
  assert config.min_sentiment_score == 0.0
  assert config.min_signal_score == 0.20
