"""Tests for gate recovery rotation and shadow open cap during graduation nudge."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.engines.gate_entry_guard import (
  get_gate_entry_tightening,
  shadow_max_open_for_bot,
  sync_gate_recovery_rotation,
)


def test_shadow_max_open_for_bot_raises_cap_during_profitable_nudge():
  cap = shadow_max_open_for_bot(
    "crypto",
    shadow_mode=True,
    bot_win_rate=0.422,
    profit_factor=1.06,
    total_pnl=5.63,
  )
  assert cap == 3


def test_shadow_max_open_for_bot_stays_at_one_when_nudge_not_profitable():
  cap = shadow_max_open_for_bot(
    "crypto",
    shadow_mode=True,
    bot_win_rate=0.40,
    profit_factor=0.90,
    total_pnl=-1.0,
  )
  assert cap == 1


def test_shadow_max_open_for_bot_raises_cap_during_near_graduation_crypto():
  cap = shadow_max_open_for_bot(
    "crypto",
    shadow_mode=True,
    bot_win_rate=0.406,
    profit_factor=0.96,
    total_pnl=-4.88,
  )
  assert cap == 3


def test_shadow_max_open_for_bot_default_when_not_in_nudge():
  cap = shadow_max_open_for_bot(
    "crypto",
    shadow_mode=True,
    bot_win_rate=0.35,
    profit_factor=0.9,
    total_pnl=-1.0,
  )
  assert cap == 1


def test_shadow_max_open_for_bot_none_when_not_shadow():
  assert shadow_max_open_for_bot("crypto", shadow_mode=False) is None


def test_sync_gate_recovery_rotation_pauses_stocks_and_activates_crypto():
  gate_result = {
    "total_trades": 15,
    "profit_factor": 0.62,
    "total_pnl": -52.34,
  }
  per_bot = {
    "crypto": {
      "paused": True,
      "win_rate": 0.422,
      "profit_factor": 1.06,
      "total_pnl": 5.63,
    },
    "commodities": {
      "paused": True,
      "win_rate": 0.444,
      "profit_factor": 1.19,
      "total_pnl": 19.13,
    },
    "stocks_futures": {"paused": False},
  }

  with patch("app.engines.gate_entry_guard.ProfitabilityGate") as GateCls:
    gate = GateCls.return_value
    gate.evaluate = AsyncMock(return_value=gate_result)
    gate.evaluate_per_bot = AsyncMock(return_value=per_bot)
    with patch(
      "app.engines.platform_settings.is_bot_paused",
      AsyncMock(return_value=False),
    ):
      with patch(
        "app.engines.platform_settings.get_paused_bot_types",
        AsyncMock(return_value=["crypto", "commodities", "polymarket"]),
      ):
        with patch(
          "app.engines.platform_settings.set_bot_paused",
          AsyncMock(),
        ) as set_pause:
          session = MagicMock()
          result = asyncio.run(sync_gate_recovery_rotation(session))

  assert result == {"paused": "stocks_futures", "activated": "commodities"}
  assert set_pause.await_count == 2


def test_sync_gate_recovery_rotation_skips_when_pf_healthy():
  gate_result = {
    "total_trades": 15,
    "profit_factor": 1.2,
    "total_pnl": 10.0,
  }

  with patch("app.engines.gate_entry_guard.ProfitabilityGate") as GateCls:
    GateCls.return_value.evaluate = AsyncMock(return_value=gate_result)
    with patch(
      "app.engines.platform_settings.get_paused_bot_types",
      AsyncMock(return_value=["crypto", "stocks_futures", "polymarket"]),
    ):
      with patch(
        "app.engines.platform_settings.set_bot_paused",
        AsyncMock(),
      ) as set_pause:
        result = asyncio.run(sync_gate_recovery_rotation(MagicMock()))

  assert result is None
  set_pause.assert_not_called()


def test_sync_gate_recovery_rotation_reactivates_when_all_paused():
  per_bot = {
    "crypto": {
      "paused": True,
      "win_rate": 0.422,
      "profit_factor": 1.06,
      "total_pnl": 5.63,
    },
    "commodities": {
      "paused": True,
      "win_rate": 0.444,
      "profit_factor": 1.19,
      "total_pnl": 19.13,
    },
  }

  with patch("app.engines.gate_entry_guard.ProfitabilityGate") as GateCls:
    GateCls.return_value.evaluate_per_bot = AsyncMock(return_value=per_bot)
    with patch(
      "app.engines.platform_settings.get_paused_bot_types",
      AsyncMock(return_value=["crypto", "stocks_futures", "commodities", "polymarket"]),
    ):
      with patch(
        "app.engines.platform_settings.set_bot_paused",
        AsyncMock(),
      ) as set_pause:
        result = asyncio.run(sync_gate_recovery_rotation(MagicMock()))

  assert result == {"paused": "all", "activated": "commodities"}
  set_pause.assert_awaited_once()
  assert set_pause.await_args.args[1:] == ("commodities", False)


def test_get_gate_entry_tightening_raises_commodities_cap_during_profitable_nudge():
  gate_result = {
    "total_trades": 29,
    "win_rate": 0.444,
  }
  per_bot = {
    "commodities": {
      "paused": False,
      "win_rate": 0.444,
      "profit_factor": 1.19,
      "total_pnl": 19.13,
    },
  }

  with patch("app.engines.gate_entry_guard.ProfitabilityGate") as GateCls:
    gate = GateCls.return_value
    gate.evaluate = AsyncMock(return_value=gate_result)
    gate.evaluate_per_bot = AsyncMock(return_value=per_bot)
    with patch(
      "app.engines.gate_entry_guard.get_underperforming_bots",
      AsyncMock(return_value=frozenset()),
    ):
      tightening = asyncio.run(get_gate_entry_tightening(MagicMock()))

  assert tightening.active is False
  assert tightening.max_commodities_open_positions == 3


def test_get_gate_entry_tightening_exempts_active_gate_from_entry_block():
  gate_result = {
    "total_trades": 30,
    "win_rate": 0.444,
  }
  per_bot = {
    "commodities": {
      "paused": False,
      "win_rate": 0.444,
      "profit_factor": 1.19,
      "total_pnl": 19.13,
      "total_trades": 30,
    },
    "crypto": {
      "paused": True,
      "win_rate": 0.447,
      "profit_factor": 1.11,
      "total_pnl": 10.51,
      "total_trades": 60,
    },
    "polymarket": {
      "paused": True,
      "win_rate": 0.36,
      "profit_factor": 3.09,
      "total_pnl": 1370.0,
      "total_trades": 30,
    },
  }

  with patch("app.engines.gate_entry_guard.ProfitabilityGate") as GateCls:
    GateCls.MIN_WIN_RATE = 0.55
    gate = GateCls.return_value
    gate.evaluate = AsyncMock(return_value=gate_result)
    gate.evaluate_per_bot = AsyncMock(return_value=per_bot)
    with patch(
      "app.engines.gate_entry_guard.get_underperforming_bots",
      AsyncMock(return_value=frozenset({"commodities", "crypto", "polymarket"})),
    ):
      with patch(
        "app.engines.gate_entry_guard.active_gate_entry_exempt_bots",
        AsyncMock(return_value=frozenset({"commodities"})),
      ):
        tightening = asyncio.run(get_gate_entry_tightening(MagicMock()))

  assert tightening.active is True
  assert "commodities" not in tightening.blocked_new_entries
  assert "polymarket" in tightening.blocked_new_entries
