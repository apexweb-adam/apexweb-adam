"""Tests for commodities weekend stale exit guard."""

from datetime import datetime
from unittest.mock import patch

from app.engines.gate_entry_guard import (
  commodities_futures_weekend_closed,
  commodities_weekend_stale_signal_exit_blocked,
  is_commodities_futures_symbol,
)


def test_is_commodities_futures_symbol():
  assert is_commodities_futures_symbol("NG=F") is True
  assert is_commodities_futures_symbol("XAUUSDT") is False


def test_commodities_weekend_stale_signal_exit_blocked_flat_ng():
  with patch("app.engines.gate_entry_guard.datetime") as mock_dt:
    mock_dt.utcnow.return_value = datetime(2026, 8, 29, 3, 59, 0)
    mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
    assert commodities_futures_weekend_closed() is True
    assert commodities_weekend_stale_signal_exit_blocked(
      symbol="NG=F",
      unrealized=0.0,
      signal_direction="sell",
    ) is True


def test_commodities_weekend_stale_signal_exit_allows_loss():
  with patch("app.engines.gate_entry_guard.datetime") as mock_dt:
    mock_dt.utcnow.return_value = datetime(2026, 8, 29, 3, 59, 0)
    mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
    assert commodities_weekend_stale_signal_exit_blocked(
      symbol="NG=F",
      unrealized=-1.5,
      signal_direction="sell",
    ) is False


def test_commodities_weekend_stale_signal_exit_not_blocked_weekday():
  with patch("app.engines.gate_entry_guard.datetime") as mock_dt:
    mock_dt.utcnow.return_value = datetime(2026, 8, 31, 14, 0, 0)
    mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
    assert commodities_futures_weekend_closed() is False
    assert commodities_weekend_stale_signal_exit_blocked(
      symbol="NG=F",
      unrealized=0.0,
      signal_direction="sell",
    ) is False
