"""Tests for stocks bot US session gating."""

from datetime import datetime
from unittest.mock import patch

from app.bots.trading_bots import StocksFuturesBot


def test_in_us_session_weekday_during_hours():
  bot = StocksFuturesBot()
  # Monday 2026-08-31 15:00 UTC (11:00 ET) — inside session
  with patch("app.bots.trading_bots.datetime") as mock_dt:
    mock_dt.utcnow.return_value = datetime(2026, 8, 31, 15, 0, 0)
    mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
    assert bot._in_us_session() is True


def test_in_us_session_outside_hours():
  bot = StocksFuturesBot()
  # Friday 2026-08-28 02:53 UTC — outside session
  with patch("app.bots.trading_bots.datetime") as mock_dt:
    mock_dt.utcnow.return_value = datetime(2026, 8, 28, 2, 53, 0)
    mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
    assert bot._in_us_session() is False


def test_in_us_session_weekend():
  bot = StocksFuturesBot()
  with patch("app.bots.trading_bots.datetime") as mock_dt:
    mock_dt.utcnow.return_value = datetime(2026, 8, 29, 15, 0, 0)  # Saturday
    mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
    assert bot._in_us_session() is False
