"""Market data fallback tests — crypto must work when Binance is geo-blocked."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.engines.market_data import fetch_crypto_data, fetch_yahoo_crypto
from app.engines.price_validation import is_price_sane


@pytest.mark.parametrize(
  "symbol,price,expected",
  [
    ("BTCUSDT", 78_000.0, True),
    ("PEPEUSDT", 0.000006, True),
    ("BNBUSDT", 693.0, True),
    ("WIFUSDT", 0.21, True),
    ("BTCUSDT", 0.0, False),
    ("PEPEUSDT", 1.0, False),
  ],
)
def test_is_price_sane_crypto_bounds(symbol, price, expected):
  assert is_price_sane(symbol, price) is expected


def test_fetch_crypto_data_yahoo_fallback_when_binance_blocked():
  async def run():
    with patch(
      "app.engines.market_data.fetch_binance",
      new=AsyncMock(return_value=(0.0, None)),
    ), patch(
      "app.engines.market_data.settings"
    ) as mock_settings, patch(
      "app.engines.market_data.fetch_yahoo_crypto",
      new=AsyncMock(return_value=(105.32, object())),
    ) as yahoo:
      mock_settings.hyperliquid_enabled = False
      price, df = await fetch_crypto_data("SOLUSDT", "15m")
      assert price == 105.32
      assert df is not None
      yahoo.assert_awaited_once_with("SOLUSDT", "15m")

  asyncio.run(run())


def test_fetch_yahoo_crypto_synthetic_when_chart_sparse():
  async def run():
    with patch(
      "app.engines.market_data.fetch_yahoo_chart",
      new=AsyncMock(return_value=(0.000006, None)),
    ):
      price, df = await fetch_yahoo_crypto("PEPEUSDT", "15m")
      assert price == 0.000006
      assert df is not None
      assert len(df) >= 30

  asyncio.run(run())
