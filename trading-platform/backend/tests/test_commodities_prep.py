"""Tests for commodities pre-CME-session TradingView prep."""

from unittest.mock import AsyncMock, patch

from app.workers.scheduler import commodities_pre_session_prep_job


def test_commodities_prep_skips_when_in_session():
  with patch(
    "app.engines.gate_entry_guard.commodities_session_info",
    return_value={"in_session": True, "minutes_until_open": 0},
  ):
    with patch(
      "app.engines.integration_signals.refresh_tradingview_signals",
      new_callable=AsyncMock,
    ) as mock_refresh:
      import asyncio

      asyncio.run(commodities_pre_session_prep_job())
      mock_refresh.assert_not_called()


def test_commodities_prep_refreshes_within_prep_window():
  with patch(
    "app.engines.gate_entry_guard.commodities_session_info",
    return_value={
      "in_session": False,
      "minutes_until_open": 60,
      "mode": "pre_session",
    },
  ):
    with patch(
      "app.engines.gate_entry_guard.get_proven_winner_symbols",
      new_callable=AsyncMock,
      return_value=frozenset({"CL=F"}),
    ):
      with patch(
        "app.engines.integration_signals.refresh_tradingview_signals",
        new_callable=AsyncMock,
        return_value=["CL=F", "SI=F"],
      ) as mock_refresh:
        with patch("app.ws_manager.push_live_update", new_callable=AsyncMock):
          import asyncio

          asyncio.run(commodities_pre_session_prep_job())
          mock_refresh.assert_called_once()
          symbols = mock_refresh.call_args[0][1]
          assert "CL=F" in symbols
          assert "SI=F" in symbols


def test_commodities_prep_includes_chronic_recovery_futures():
  with patch(
    "app.engines.gate_entry_guard.commodities_session_info",
    return_value={
      "in_session": False,
      "minutes_until_open": 45,
      "mode": "pre_session",
    },
  ):
    with patch(
      "app.engines.gate_entry_guard.get_proven_winner_symbols",
      new_callable=AsyncMock,
      return_value=frozenset(),
    ):
      with patch(
        "app.engines.gate_entry_guard.get_chronic_loser_symbols",
        new_callable=AsyncMock,
        return_value=frozenset({"SI=F", "XAUUSDT"}),
      ):
        with patch(
          "app.engines.integration_signals.refresh_tradingview_signals",
          new_callable=AsyncMock,
          return_value=["SI=F"],
        ) as mock_refresh:
          with patch("app.ws_manager.push_live_update", new_callable=AsyncMock):
            import asyncio

            asyncio.run(commodities_pre_session_prep_job())
            symbols = mock_refresh.call_args[0][1]
            assert "SI=F" in symbols
            assert "XAUUSDT" not in symbols
