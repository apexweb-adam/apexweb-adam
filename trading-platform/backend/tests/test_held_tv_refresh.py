"""Tests for held-position TradingView refresh job."""

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from app.workers.scheduler import held_positions_tv_refresh_job


@contextmanager
def _mock_scheduler_session():
  mock_session = AsyncMock()
  mock_cm = AsyncMock()
  mock_cm.__aenter__.return_value = mock_session
  mock_cm.__aexit__.return_value = None
  with patch("app.workers.scheduler.SessionLocal", return_value=mock_cm):
    yield mock_session


def test_held_positions_tv_refresh_skips_when_no_active_bots():
  with patch(
    "app.engines.platform_settings.get_paused_bot_types",
    new_callable=AsyncMock,
    return_value=["crypto", "stocks_futures", "polymarket", "commodities"],
  ):
    with patch(
      "app.engines.integration_signals.refresh_tradingview_signals",
      new_callable=AsyncMock,
    ) as mock_refresh:
      with _mock_scheduler_session():
        import asyncio

        asyncio.run(held_positions_tv_refresh_job())
      mock_refresh.assert_not_called()


def test_held_positions_tv_refresh_refreshes_open_gate_symbols():
  position = MagicMock(symbol="CL=F")
  engine = MagicMock()
  engine.get_open_positions = AsyncMock(return_value=[position])

  with patch(
    "app.engines.platform_settings.get_paused_bot_types",
    new_callable=AsyncMock,
    return_value=["crypto", "stocks_futures", "polymarket"],
  ):
    with patch("app.engines.paper_trading.PaperTradingEngine", return_value=engine):
      with patch(
        "app.engines.integration_signals.refresh_tradingview_signals",
        new_callable=AsyncMock,
        return_value=["CL=F"],
      ) as mock_refresh:
        with patch("app.ws_manager.push_live_update", new_callable=AsyncMock):
          with _mock_scheduler_session():
            import asyncio

            asyncio.run(held_positions_tv_refresh_job())
          mock_refresh.assert_called_once()
          symbols = mock_refresh.call_args[0][1]
          assert "CL=F" in symbols
