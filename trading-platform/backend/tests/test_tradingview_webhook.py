"""Tests for TradingView webhook ingestion."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.api.routes import tradingview_webhook
from app.main import app


def _mock_db_session():
  session = AsyncMock()
  session.add = MagicMock()
  session.commit = AsyncMock()
  return session


def test_tradingview_webhook_rejects_bad_secret():
  session = _mock_db_session()
  with patch("app.config.settings") as mock_settings:
    mock_settings.tradingview_webhook_secret = "secret"
    result = asyncio.run(tradingview_webhook({"secret": "wrong"}, session))
  assert result == {"status": "unauthorized"}
  session.add.assert_not_called()


def test_tradingview_webhook_buy_sets_positive_sentiment():
  session = _mock_db_session()
  with patch("app.config.settings") as mock_settings:
    mock_settings.tradingview_webhook_secret = "secret"
    with patch("app.ws_manager.push_live_update", new_callable=AsyncMock):
      result = asyncio.run(
        tradingview_webhook(
          {"secret": "secret", "symbol": "AAPL", "action": "buy", "message": "RSI cross"},
          session,
        )
      )
  assert result["status"] == "received"
  assert result["symbol"] == "AAPL"
  assert result["action"] == "buy"
  session.add.assert_called_once()
  item = session.add.call_args[0][0]
  assert item.source == "tradingview"
  assert item.sentiment == 0.5
  assert item.symbols_mentioned == "AAPL"


def test_tradingview_webhook_sell_sets_negative_sentiment():
  session = _mock_db_session()
  with patch("app.config.settings") as mock_settings:
    mock_settings.tradingview_webhook_secret = "secret"
    with patch("app.ws_manager.push_live_update", new_callable=AsyncMock):
      result = asyncio.run(
        tradingview_webhook(
          {"secret": "secret", "ticker": "BTCUSDT", "action": "sell"},
          session,
        )
      )
  assert result["symbol"] == "BTCUSDT"
  item = session.add.call_args[0][0]
  assert item.sentiment == -0.5


def test_tradingview_webhook_test_admin_endpoint():
  client = TestClient(app)
  with patch("app.api.routes.settings") as mock_settings:
    mock_settings.tradingview_webhook_secret = "secret"
    with patch("app.api.routes.tradingview_webhook", new_callable=AsyncMock) as mock_tv:
      mock_tv.return_value = {"status": "received", "symbol": "ETHUSDT", "action": "buy"}
      resp = client.post(
        "/api/admin/test-tradingview-webhook",
        json={"secret": "secret", "symbol": "ETHUSDT", "action": "buy"},
      )
  assert resp.status_code == 200
  body = resp.json()
  assert body["status"] == "ok"
  assert "webhooks/tradingview" in body["webhook_url"]
