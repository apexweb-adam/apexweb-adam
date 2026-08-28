"""Tests for stocks bot US session gating."""

from datetime import datetime
from unittest.mock import patch

from app.bots.trading_bots import StocksFuturesBot
from app.engines.gate_entry_guard import (
  GateEntryTightening,
  stocks_gate_entry_sentiment_ok,
  stocks_in_us_session,
  stocks_session_info,
)


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


def test_stocks_bot_faster_scan_during_gated_us_session():
  bot = StocksFuturesBot()
  tightening = GateEntryTightening(
    active=True,
    win_rate=0.47,
    min_sentiment=0.06,
    require_macd_bullish=True,
    min_composite_boost=0.03,
  )

  async def _run():
    with patch("app.bots.trading_bots.stocks_in_us_session", return_value=True):
      with patch(
        "app.bots.trading_bots.get_gate_entry_tightening",
        return_value=tightening,
      ):
        assert await bot._effective_scan_interval() == 15

  import asyncio

  asyncio.run(_run())


def test_stocks_bot_default_scan_outside_session():
  bot = StocksFuturesBot()

  async def _run():
    with patch("app.bots.trading_bots.stocks_in_us_session", return_value=False):
      assert await bot._effective_scan_interval() == 30

  import asyncio

  asyncio.run(_run())


def test_stocks_bot_faster_scan_during_verification_period():
  bot = StocksFuturesBot()
  gate_result = {"total_trades": 5, "win_rate": 1.0}
  tightening = GateEntryTightening(
    active=False,
    win_rate=1.0,
    min_sentiment=0.0,
    require_macd_bullish=False,
    min_composite_boost=0.0,
  )

  async def _run():
    with patch("app.bots.trading_bots.stocks_in_us_session", return_value=True):
      with patch("app.config.settings.paper_trading_only", True):
        with patch(
          "app.engines.profitability_gate.ProfitabilityGate.evaluate",
          return_value=gate_result,
        ):
          with patch(
            "app.bots.trading_bots.get_gate_entry_tightening",
            return_value=tightening,
          ):
            assert await bot._effective_scan_interval() == 15

  import asyncio

  asyncio.run(_run())


def test_stocks_session_info_in_session():
  with patch("app.engines.gate_entry_guard.datetime") as mock_dt:
    mock_dt.utcnow.return_value = datetime(2026, 8, 28, 15, 0, 0)
    mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
    info = stocks_session_info()
    assert info["in_session"] is True
    assert info["mode"] == "entries"
    assert info["minutes_until_open"] == 0
    assert info["minutes_until_close"] is not None
    assert info["minutes_until_close"] > 0


def test_stocks_session_info_before_open():
  with patch("app.engines.gate_entry_guard.datetime") as mock_dt:
    mock_dt.utcnow.return_value = datetime(2026, 8, 28, 5, 12, 0)
    mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
    info = stocks_session_info()
    assert info["in_session"] is False
    assert info["mode"] == "winddown_only"
    assert info["minutes_until_open"] == 498  # 13:30 - 05:12
    assert info["minutes_until_close"] is None
    assert "13:30:00" in info["session_open_utc"]


def test_stocks_session_info_after_close_weekday():
  with patch("app.engines.gate_entry_guard.datetime") as mock_dt:
    mock_dt.utcnow.return_value = datetime(2026, 8, 28, 22, 0, 0)
    mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
    info = stocks_session_info()
    assert info["in_session"] is False
    assert info["mode"] == "winddown_only"
    assert info["minutes_until_open"] > 0
    assert info["session_open_utc"].startswith("2026-08-31")
