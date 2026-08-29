"""Tests for stocks pre-US-session TradingView prep."""

from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

from app.workers.scheduler import stocks_pre_session_prep_job


@contextmanager
def _mock_scheduler_session():
  mock_session = AsyncMock()
  mock_cm = AsyncMock()
  mock_cm.__aenter__.return_value = mock_session
  mock_cm.__aexit__.return_value = None
  with patch("app.workers.scheduler.SessionLocal", return_value=mock_cm):
    yield mock_session


def test_stocks_prep_skips_when_in_session():
  with patch(
    "app.engines.gate_entry_guard.stocks_session_info",
    return_value={"in_session": True, "minutes_until_open": 0},
  ):
    with patch(
      "app.engines.integration_signals.refresh_tradingview_signals",
      new_callable=AsyncMock,
    ) as mock_refresh:
      import asyncio

      asyncio.run(stocks_pre_session_prep_job())
      mock_refresh.assert_not_called()


def test_stocks_prep_refreshes_recovery_symbols_within_prep_window():
  with patch(
    "app.engines.gate_entry_guard.stocks_session_info",
    return_value={
      "in_session": False,
      "minutes_until_open": 60,
      "mode": "pre_session",
    },
  ):
    with patch(
      "app.engines.gate_entry_guard.get_proven_winner_symbols",
      new_callable=AsyncMock,
      return_value=frozenset({"AAPL"}),
    ):
      with patch(
        "app.engines.gate_entry_guard.get_chronic_loser_symbols",
        new_callable=AsyncMock,
        return_value=frozenset({"NVDA"}),
      ):
        with patch(
          "app.engines.integration_signals.refresh_tradingview_signals",
          new_callable=AsyncMock,
          return_value=["NVDA", "AAPL"],
        ) as mock_refresh:
          with patch("app.ws_manager.push_live_update", new_callable=AsyncMock):
            with _mock_scheduler_session():
              import asyncio

              asyncio.run(stocks_pre_session_prep_job())
            mock_refresh.assert_called_once()
            symbols = mock_refresh.call_args[0][1]
            assert "NVDA" in symbols
            assert "AAPL" in symbols
