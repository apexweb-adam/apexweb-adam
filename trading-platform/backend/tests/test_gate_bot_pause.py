"""Tests for auto-pausing underperformers during verification gate."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.engines.gate_entry_guard import sync_gate_bot_pauses


def test_sync_gate_bot_pauses_underperformers():
  gate_result = {
    "win_rate": 0.47,
    "total_trades": 111,
    "aggregate": {"win_rate": 0.47, "total_trades": 111},
  }

  with patch("app.engines.gate_entry_guard.ProfitabilityGate") as GateCls:
    GateCls.MIN_WIN_RATE = 0.55
    GateCls.return_value.evaluate = AsyncMock(return_value=gate_result)
    with patch(
      "app.engines.gate_entry_guard.get_underperforming_bots",
      AsyncMock(return_value=frozenset({"crypto", "commodities", "polymarket"})),
    ):
      with patch(
        "app.engines.platform_settings.is_bot_paused",
        AsyncMock(return_value=False),
      ):
        with patch(
          "app.engines.platform_settings.set_bot_paused",
          AsyncMock(),
        ) as set_pause:
          session = MagicMock()
          paused = asyncio.run(sync_gate_bot_pauses(session))

  assert set(paused) == {"crypto", "commodities", "polymarket"}
  assert set_pause.await_count == 3


def test_sync_gate_bot_pauses_skips_when_wr_met():
  gate_result = {
    "win_rate": 0.56,
    "total_trades": 120,
    "aggregate": {"win_rate": 0.56, "total_trades": 120},
  }

  with patch("app.engines.gate_entry_guard.ProfitabilityGate") as GateCls:
    GateCls.MIN_WIN_RATE = 0.55
    GateCls.return_value.evaluate = AsyncMock(return_value=gate_result)
    with patch(
      "app.engines.platform_settings.set_bot_paused",
      AsyncMock(),
    ) as set_pause:
      paused = asyncio.run(sync_gate_bot_pauses(MagicMock()))

  assert paused == []
  set_pause.assert_not_called()
