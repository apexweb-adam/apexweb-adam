"""Tests for stocks bot US session gating."""

from datetime import datetime
from unittest.mock import AsyncMock, patch

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
    mock_session = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = None

    with patch("app.bots.trading_bots.SessionLocal", return_value=mock_cm):
      with patch("app.bots.trading_bots.stocks_in_us_session", return_value=True):
        with patch(
          "app.engines.profitability_gate.ProfitabilityGate",
        ) as MockGate:
          MockGate.MIN_TRADES = 100
          MockGate.return_value.evaluate = AsyncMock(return_value={"total_trades": 100})
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
    mock_session = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = None

    with patch("app.bots.trading_bots.SessionLocal", return_value=mock_cm):
      with patch("app.bots.trading_bots.stocks_in_us_session", return_value=False):
        with patch(
          "app.engines.profitability_gate.ProfitabilityGate",
        ) as MockGate:
          MockGate.MIN_TRADES = 100
          MockGate.GRADUATION_MIN_WIN_RATE = 0.55
          MockGate.return_value.evaluate = AsyncMock(
            return_value={"total_trades": 100, "shadow_mode": True}
          )
          MockGate.return_value.evaluate_per_bot = AsyncMock(
            return_value={"stocks_futures": {"total_trades": 15, "win_rate": 0.4}}
          )
          with patch(
            "app.engines.gate_entry_guard.stocks_gate_fast_scan_active",
            return_value=False,
          ):
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


def test_stocks_bot_faster_scan_during_trade_count_prep():
  bot = StocksFuturesBot()
  gate_result = {"total_trades": 50, "win_rate": 0.6, "shadow_mode": True}
  per_bot = {"total_trades": 95, "win_rate": 0.6, "profit_factor": 1.1, "total_pnl": 10.0}
  tightening = GateEntryTightening(
    active=False,
    win_rate=0.6,
    min_sentiment=0.0,
    require_macd_bullish=False,
    min_composite_boost=0.0,
  )

  async def _run():
    mock_session = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = None

    with patch("app.bots.trading_bots.SessionLocal", return_value=mock_cm):
      with patch("app.bots.trading_bots.stocks_in_us_session", return_value=False):
        with patch(
          "app.engines.profitability_gate.ProfitabilityGate",
        ) as MockGate:
          MockGate.MIN_TRADES = 100
          MockGate.GRADUATION_MIN_WIN_RATE = 0.55
          MockGate.GRADUATION_MIN_TRADES = 100
          MockGate.return_value.evaluate = AsyncMock(return_value=gate_result)
          MockGate.return_value.evaluate_per_bot = AsyncMock(
            return_value={"stocks_futures": per_bot}
          )
          with patch(
            "app.bots.trading_bots.get_gate_entry_tightening",
            return_value=tightening,
          ):
            with patch(
              "app.engines.gate_entry_guard.stocks_gate_fast_scan_active",
              return_value=True,
            ):
              with patch(
                "app.engines.gate_entry_guard.ProfitabilityGate",
                MockGate,
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


def test_stocks_session_info_winddown_last_30_minutes():
  with patch("app.engines.gate_entry_guard.datetime") as mock_dt:
    mock_dt.utcnow.return_value = datetime(2026, 8, 28, 21, 10, 0)
    mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
    info = stocks_session_info()
    assert info["in_session"] is True
    assert info["mode"] == "winddown"
    assert info["minutes_until_close"] == 20


def test_stocks_session_info_before_open():
  with patch("app.engines.gate_entry_guard.datetime") as mock_dt:
    mock_dt.utcnow.return_value = datetime(2026, 8, 28, 5, 12, 0)
    mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
    info = stocks_session_info()
    assert info["in_session"] is False
    assert info["mode"] == "outside_session"
    assert info["minutes_until_open"] == 498  # 13:30 - 05:12
    assert info["minutes_until_close"] is None
    assert "13:30:00" in info["session_open_utc"]


def test_stocks_session_info_pre_session_window():
  with patch("app.engines.gate_entry_guard.datetime") as mock_dt:
    mock_dt.utcnow.return_value = datetime(2026, 8, 28, 12, 35, 0)
    mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
    info = stocks_session_info()
    assert info["in_session"] is False
    assert info["mode"] == "pre_session"
    assert info["minutes_until_open"] == 55


def test_stocks_session_info_after_close_weekday():
  with patch("app.engines.gate_entry_guard.datetime") as mock_dt:
    mock_dt.utcnow.return_value = datetime(2026, 8, 28, 22, 0, 0)
    mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
    info = stocks_session_info()
    assert info["in_session"] is False
    assert info["mode"] == "winddown_only"
    assert info["minutes_until_open"] > 0
    assert info["session_open_utc"].startswith("2026-08-31")
