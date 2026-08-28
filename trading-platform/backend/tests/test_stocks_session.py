"""Tests for stocks bot US session gating."""

from datetime import datetime
from unittest.mock import patch

from app.bots.trading_bots import StocksFuturesBot
from app.engines.gate_entry_guard import stocks_gate_entry_sentiment_ok, stocks_in_us_session


def test_stocks_in_us_session_weekday_during_hours():
  with patch("app.engines.gate_entry_guard.datetime") as mock_dt:
    mock_dt.utcnow.return_value = datetime(2026, 8, 31, 15, 0, 0)
    mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
    assert stocks_in_us_session() is True


def test_stocks_in_us_session_outside_hours():
  with patch("app.engines.gate_entry_guard.datetime") as mock_dt:
    mock_dt.utcnow.return_value = datetime(2026, 8, 28, 2, 53, 0)
    mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
    assert stocks_in_us_session() is False


def test_stocks_in_us_session_weekend():
  with patch("app.engines.gate_entry_guard.datetime") as mock_dt:
    mock_dt.utcnow.return_value = datetime(2026, 8, 29, 15, 0, 0)
    mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
    assert stocks_in_us_session() is False


def test_bot_delegates_to_shared_session_helper():
  bot = StocksFuturesBot()
  with patch("app.bots.trading_bots.stocks_in_us_session", return_value=True):
    assert bot._in_us_session() is True


def test_stocks_gate_entry_sentiment_ok():
  assert stocks_gate_entry_sentiment_ok(0.1, 0.0) is True
  assert stocks_gate_entry_sentiment_ok(-0.2, 0.05) is True
  assert stocks_gate_entry_sentiment_ok(-0.2, 0.0) is False
