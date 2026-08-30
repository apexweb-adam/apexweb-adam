"""Tests for TradingView signal refresh helper."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.engines.integration_signals import refresh_tradingview_signals


def test_refresh_tradingview_signals_skips_recent():
  session = AsyncMock()
  recent_item = MagicMock()
  result_mock = MagicMock()
  result_mock.scalar_one_or_none.return_value = recent_item
  session.execute.return_value = result_mock

  refreshed = asyncio.run(refresh_tradingview_signals(session, ["NVDA"]))
  assert refreshed == []
  session.add.assert_not_called()
  session.commit.assert_not_called()


def test_refresh_tradingview_signals_injects_missing():
  session = AsyncMock()
  result_mock = MagicMock()
  result_mock.scalar_one_or_none.return_value = None
  session.execute.return_value = result_mock

  refreshed = asyncio.run(refresh_tradingview_signals(session, ["NVDA", "AAPL"]))
  assert refreshed == ["NVDA", "AAPL"]
  assert session.add.call_count == 2
  added = session.add.call_args_list[0][0][0]
  assert added.category == "synthetic"
  session.commit.assert_awaited_once()


def test_refresh_tradingview_signals_force_refresh():
  session = AsyncMock()
  recent_item = MagicMock()
  result_mock = MagicMock()
  result_mock.scalar_one_or_none.return_value = recent_item
  session.execute.return_value = result_mock

  refreshed = asyncio.run(
    refresh_tradingview_signals(session, ["NVDA"], force_refresh=True)
  )
  assert refreshed == ["NVDA"]
  session.add.assert_called_once()
  session.commit.assert_awaited_once()
