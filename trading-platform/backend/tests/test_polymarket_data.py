"""Tests for Polymarket price history bootstrap and persistence."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.engines import polymarket_data as pm


@pytest.fixture(autouse=True)
def _reset_pm_history():
  pm.clear_pm_history_cache()
  yield
  pm.clear_pm_history_cache()


def test_parse_yes_token_id_from_json_string():
  market = {"clobTokenIds": '["12345", "67890"]'}
  assert pm._parse_yes_token_id(market) == "12345"


def test_serialize_and_load_pm_history_roundtrip():
  now = datetime.utcnow()
  pm._merge_history_points("trump-win", [(now, 0.55), (now - timedelta(hours=1), 0.52)])
  payload = pm.serialize_pm_history()
  pm.clear_pm_history_cache()
  pm.load_pm_history_payload(payload)
  assert len(pm._pm_history["trump-win"]) == 2


@pytest.mark.asyncio
async def test_bootstrap_history_from_clob_populates_ticks():
  now = datetime.utcnow()
  history = [
    {"t": int((now - timedelta(minutes=idx * 30)).timestamp()), "p": f"{0.40 + idx * 0.01:.2f}"}
    for idx in range(12)
  ]
  market = {
    "slug": "fed-rate-cut-2025",
    "clobTokenIds": '["999"]',
    "outcomePrices": "[0.45]",
    "volume24hr": 5000,
  }

  with patch.object(pm, "_fetch_clob_price_history", AsyncMock(return_value=[
    (datetime.utcfromtimestamp(point["t"]), float(point["p"])) for point in history
  ])):
    await pm._bootstrap_history_from_clob("fed-rate-cut-2025", market)

  assert len(pm._pm_history["fed-rate-cut-2025"]) >= pm.PM_HISTORY_MIN_TICKS


@pytest.mark.asyncio
async def test_fetch_polymarket_data_returns_dataframe_after_clob_bootstrap():
  market = {
    "slug": "bitcoin-100k",
    "clobTokenIds": '["888"]',
    "outcomePrices": "[0.62]",
    "volume24hr": 12000,
  }
  boot_points = [
    (datetime.utcnow() - timedelta(minutes=30 * idx), 0.50 + idx * 0.01)
    for idx in range(12)
  ]

  with patch.object(pm, "_find_market_by_slug", AsyncMock(return_value=market)):
    with patch.object(pm, "_fetch_clob_price_history", AsyncMock(return_value=boot_points)):
      price, df = await pm.fetch_polymarket_data("PM:bitcoin-100k")

  assert price == pytest.approx(0.62)
  assert df is not None
  assert len(df) >= pm.PM_HISTORY_MIN_TICKS


@pytest.mark.asyncio
async def test_persist_pm_history_to_settings_writes_payload():
  session = AsyncMock()
  pm._merge_history_points("btc-etf", [(datetime.utcnow(), 0.71)])
  with patch("app.engines.platform_settings.set_platform_setting", AsyncMock()) as mock_set:
    await pm.persist_pm_history_to_settings(session)
  mock_set.assert_awaited_once()
  _session, key, raw = mock_set.await_args.args
  assert key == pm.PM_HISTORY_SETTING_KEY
  assert "btc-etf" in raw
