"""Tests for commodities weekend stale exit guard."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

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


def test_commodities_weekend_futures_entry_blocked():
  from app.engines.gate_entry_guard import commodities_weekend_futures_entry_blocked

  with patch("app.engines.gate_entry_guard.datetime") as mock_dt:
    mock_dt.utcnow.return_value = datetime(2026, 8, 29, 4, 0, 0)
    mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
    assert commodities_weekend_futures_entry_blocked("NG=F") is True
    assert commodities_weekend_futures_entry_blocked("XAUUSDT") is False

  with patch("app.engines.gate_entry_guard.datetime") as mock_dt:
    mock_dt.utcnow.return_value = datetime(2026, 8, 31, 14, 0, 0)
    mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
    assert commodities_weekend_futures_entry_blocked("NG=F") is False


def test_commodities_session_info_weekend_closed():
  from app.engines.gate_entry_guard import commodities_session_info

  with patch("app.engines.gate_entry_guard.datetime") as mock_dt:
    mock_dt.utcnow.return_value = datetime(2026, 8, 29, 4, 0, 0)
    mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
    info = commodities_session_info()
    assert info["in_session"] is False
    assert info["mode"] == "weekend_closed"
    assert info["minutes_until_open"] == 44 * 60


def test_commodities_session_info_pre_session():
  from app.engines.gate_entry_guard import commodities_session_info

  with patch("app.engines.gate_entry_guard.datetime") as mock_dt:
    mock_dt.utcnow.return_value = datetime(2026, 8, 30, 22, 45, 0)
    mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
    info = commodities_session_info()
    assert info["in_session"] is False
    assert info["mode"] == "pre_session"
    assert info["minutes_until_open"] == 75
    assert info["minutes_since_open"] == 0


def test_commodities_session_info_weekday_open():
  from app.engines.gate_entry_guard import commodities_session_info

  with patch("app.engines.gate_entry_guard.datetime") as mock_dt:
    mock_dt.utcnow.return_value = datetime(2026, 8, 31, 14, 0, 0)
    mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
    info = commodities_session_info()
    assert info["in_session"] is True
    assert info["mode"] == "entries"
    assert info["minutes_since_open"] == 14 * 60 + 0


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


def test_commodities_weekend_spot_cooldown_eased():
  from app.engines.gate_entry_guard import (
    COMMODITIES_WEEKEND_SPOT_COOLDOWN_MULTIPLIER,
    _bot_cooldown_seconds,
    symbol_cooldown_remaining_seconds,
  )

  session = AsyncMock()
  executed_at = datetime(2026, 8, 29, 10, 0, 0)
  session.execute = AsyncMock(
    return_value=MagicMock(
      first=MagicMock(return_value=(False, executed_at, "loss exit", -5.0))
    )
  )
  base = _bot_cooldown_seconds("commodities", after_loss=True)
  with patch("app.engines.gate_entry_guard.datetime") as mock_dt:
    mock_dt.utcnow.return_value = datetime(2026, 8, 29, 11, 0, 0)
    mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
    remaining = asyncio.run(
      symbol_cooldown_remaining_seconds(session, "commodities", "XAUUSDT")
    )
  expected = int(base * COMMODITIES_WEEKEND_SPOT_COOLDOWN_MULTIPLIER) - 3600
  assert remaining == max(0, expected)


def test_commodities_weekend_spot_gate_skip_bypass():
  from app.engines.gate_entry_guard import (
    COMMODITIES_WEEKEND_SPOT_GATE_SKIP_COMPOSITE_FLOOR,
    chronic_loser_blocks_shadow_entry,
    commodities_weekend_spot_gate_skip_bypass,
    hard_skip_blocks_shadow_entry,
    symbol_cooldown_remaining_seconds,
  )

  base = dict(
    bot_type="commodities",
    shadow_mode=False,
    symbol="XAUUSDT",
    graduation_nudge=True,
    signal_direction="buy",
    macd_signal="bullish",
    composite=COMMODITIES_WEEKEND_SPOT_GATE_SKIP_COMPOSITE_FLOOR + 0.01,
  )
  with patch("app.engines.gate_entry_guard.datetime") as mock_dt:
    mock_dt.utcnow.return_value = datetime(2026, 8, 29, 14, 0, 0)
    mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
    assert commodities_weekend_spot_gate_skip_bypass(**base) is True
    assert commodities_weekend_spot_gate_skip_bypass(
      **{**base, "composite": COMMODITIES_WEEKEND_SPOT_GATE_SKIP_COMPOSITE_FLOOR - 0.01}
    ) is False
    assert commodities_weekend_spot_gate_skip_bypass(
      **{**base, "signal_direction": "sell"}
    ) is False
    assert hard_skip_blocks_shadow_entry(
      "XAUUSDT",
      bot_type="commodities",
      recent_skip=frozenset({"XAUUSDT"}),
      large_skip=frozenset(),
      review_skip=frozenset(),
      graduation_nudge=True,
      shadow_mode=False,
      intel_override=False,
      composite=0.434,
      integration_boost=0.067,
      signal_direction="buy",
      macd_signal="bullish",
    ) is False
    assert chronic_loser_blocks_shadow_entry(
      "PAXGUSDT",
      frozenset({"PAXGUSDT"}),
      bot_type="commodities",
      graduation_nudge=True,
      shadow_mode=False,
      intel_override=False,
      composite=0.417,
      signal_direction="buy",
      macd_signal="bullish",
    ) is False
    remaining = asyncio.run(
      symbol_cooldown_remaining_seconds(
        AsyncMock(),
        "commodities",
        "XAUUSDT",
        graduation_nudge=True,
        shadow_mode=False,
        signal_direction="buy",
        macd_signal="bullish",
        composite=0.434,
      )
    )
    assert remaining == 0


def test_commodities_weekend_graduation_open_cap_bonus():
  from app.engines.gate_entry_guard import (
    GateEntryTightening,
    commodities_effective_open_cap,
    open_position_cap_blocks_entry,
  )

  tightening = GateEntryTightening(
    active=False,
    win_rate=0.44,
    min_sentiment=0.0,
    require_macd_bullish=False,
    min_composite_boost=0.0,
    max_commodities_open_positions=3,
  )
  with patch("app.engines.gate_entry_guard.datetime") as mock_dt:
    mock_dt.utcnow.return_value = datetime(2026, 8, 29, 14, 0, 0)
    mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
    assert commodities_effective_open_cap(
      3,
      bot_type="commodities",
      graduation_nudge=True,
      shadow_mode=False,
    ) == 4
    assert open_position_cap_blocks_entry(
      "commodities",
      shadow_mode=False,
      open_count=3,
      gate_tightening=tightening,
      shadow_open_cap=None,
      graduation_nudge=True,
    ) is False
    assert open_position_cap_blocks_entry(
      "commodities",
      shadow_mode=False,
      open_count=4,
      gate_tightening=tightening,
      shadow_open_cap=None,
      graduation_nudge=True,
    ) is True
