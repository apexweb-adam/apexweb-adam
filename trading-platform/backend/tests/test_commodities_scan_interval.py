"""Tests for commodities gate scan interval during CME prep/open."""

from unittest.mock import AsyncMock, patch

from app.bots.trading_bots import CommoditiesBot
from app.engines.gate_entry_guard import (
  COMMODITIES_REOPEN_IMMINENT_SCAN_MINUTES,
  GateEntryTightening,
)


def test_commodities_effective_scan_interval_fast_during_cme_prep():
  import asyncio

  bot = CommoditiesBot()
  # Outside imminent-reopen window (60m) but still in graduation prep fast-scan.
  minutes_until = COMMODITIES_REOPEN_IMMINENT_SCAN_MINUTES + 15
  session_info = {"in_session": False, "minutes_until_open": minutes_until, "minutes_since_open": 0}
  tightening = GateEntryTightening(
    active=True,
    win_rate=0.5,
    min_sentiment=0.0,
    require_macd_bullish=False,
    min_composite_boost=0.0,
    blocked_new_entries=frozenset(),
    max_commodities_open_positions=3,
  )

  async def run() -> int:
    with patch(
      "app.engines.gate_entry_guard.commodities_session_info",
      return_value=session_info,
    ), patch(
      "app.engines.gate_entry_guard.commodities_gate_fast_scan_active",
      return_value=True,
    ), patch(
      "app.engines.gate_entry_guard.in_shadow_graduation_nudge",
      return_value=True,
    ), patch(
      "app.engines.gate_entry_guard.bot_win_rate_for_graduation_nudge",
      return_value=0.5,
    ), patch(
      "app.engines.profitability_gate.ProfitabilityGate",
    ) as mock_gate, patch(
      "app.bots.trading_bots.SessionLocal",
    ) as mock_session_local, patch(
      "app.bots.trading_bots.get_gate_entry_tightening",
      new_callable=AsyncMock,
      return_value=tightening,
    ):
      mock_gate.return_value.evaluate_per_bot = AsyncMock(
        return_value={"commodities": {"win_rate": 0.5, "profit_factor": 1.2, "total_pnl": 20.0}}
      )
      mock_gate.return_value.evaluate = AsyncMock(return_value={})
      mock_session = AsyncMock()
      mock_cm = AsyncMock()
      mock_cm.__aenter__.return_value = mock_session
      mock_cm.__aexit__.return_value = None
      mock_session_local.return_value = mock_cm
      return await bot._effective_scan_interval()

  assert asyncio.run(run()) == 15


def test_commodities_effective_scan_interval_fast_during_graduation_prep():
  import asyncio

  bot = CommoditiesBot()
  session_info = {"in_session": False, "minutes_until_open": 1776, "minutes_since_open": 0}
  tightening = GateEntryTightening(
    active=True,
    win_rate=0.5,
    min_sentiment=0.0,
    require_macd_bullish=False,
    min_composite_boost=0.0,
    blocked_new_entries=frozenset(),
    max_commodities_open_positions=3,
  )

  async def run() -> int:
    with patch(
      "app.engines.gate_entry_guard.commodities_session_info",
      return_value=session_info,
    ), patch(
      "app.engines.gate_entry_guard.commodities_gate_fast_scan_active",
      side_effect=[False, True],
    ), patch(
      "app.engines.gate_entry_guard.in_shadow_graduation_nudge",
      return_value=True,
    ), patch(
      "app.engines.gate_entry_guard.bot_win_rate_for_graduation_nudge",
      return_value=0.5,
    ), patch(
      "app.engines.profitability_gate.ProfitabilityGate",
    ) as mock_gate, patch(
      "app.bots.trading_bots.SessionLocal",
    ) as mock_session_local, patch(
      "app.bots.trading_bots.get_gate_entry_tightening",
      new_callable=AsyncMock,
      return_value=tightening,
    ):
      mock_gate.return_value.evaluate_per_bot = AsyncMock(
        return_value={"commodities": {"win_rate": 0.5, "profit_factor": 1.2, "total_pnl": 20.0}}
      )
      mock_gate.return_value.evaluate = AsyncMock(return_value={})
      mock_session = AsyncMock()
      mock_cm = AsyncMock()
      mock_cm.__aenter__.return_value = mock_session
      mock_cm.__aexit__.return_value = None
      mock_session_local.return_value = mock_cm
      return await bot._effective_scan_interval()

  assert asyncio.run(run()) == 15


def test_commodities_effective_scan_interval_default_outside_prep():
  import asyncio

  bot = CommoditiesBot()
  session_info = {"in_session": False, "minutes_until_open": 5000, "minutes_since_open": 0}

  async def run() -> int:
    with patch(
      "app.engines.gate_entry_guard.commodities_session_info",
      return_value=session_info,
    ), patch(
      "app.engines.gate_entry_guard.commodities_gate_fast_scan_active",
      return_value=False,
    ), patch(
      "app.engines.gate_entry_guard.in_shadow_graduation_nudge",
      return_value=False,
    ), patch(
      "app.engines.gate_entry_guard.bot_win_rate_for_graduation_nudge",
      return_value=0.5,
    ), patch(
      "app.engines.profitability_gate.ProfitabilityGate",
    ) as mock_gate, patch(
      "app.bots.trading_bots.SessionLocal",
    ) as mock_session_local:
      mock_gate.return_value.evaluate_per_bot = AsyncMock(
        return_value={"commodities": {"win_rate": 0.5, "profit_factor": 1.2, "total_pnl": 20.0}}
      )
      mock_gate.return_value.evaluate = AsyncMock(return_value={})
      mock_session = AsyncMock()
      mock_cm = AsyncMock()
      mock_cm.__aenter__.return_value = mock_session
      mock_cm.__aexit__.return_value = None
      mock_session_local.return_value = mock_cm
      return await bot._effective_scan_interval()

  assert asyncio.run(run()) == 30


def test_commodities_effective_scan_interval_imminent_reopen():
  import asyncio

  bot = CommoditiesBot()
  session_info = {"in_session": False, "minutes_until_open": 15, "minutes_since_open": 0}
  tightening = GateEntryTightening(
    active=True,
    win_rate=0.5,
    min_sentiment=0.0,
    require_macd_bullish=False,
    min_composite_boost=0.0,
    blocked_new_entries=frozenset(),
    max_commodities_open_positions=3,
  )

  async def run() -> int:
    with patch(
      "app.engines.gate_entry_guard.commodities_session_info",
      return_value=session_info,
    ), patch(
      "app.engines.gate_entry_guard.commodities_gate_fast_scan_active",
      return_value=True,
    ), patch(
      "app.engines.gate_entry_guard.in_shadow_graduation_nudge",
      return_value=True,
    ), patch(
      "app.engines.gate_entry_guard.bot_win_rate_for_graduation_nudge",
      return_value=0.5,
    ), patch(
      "app.engines.profitability_gate.ProfitabilityGate",
    ) as mock_gate, patch(
      "app.bots.trading_bots.SessionLocal",
    ) as mock_session_local, patch(
      "app.bots.trading_bots.get_gate_entry_tightening",
      new_callable=AsyncMock,
      return_value=tightening,
    ):
      mock_gate.return_value.evaluate_per_bot = AsyncMock(
        return_value={"commodities": {"win_rate": 0.5, "profit_factor": 1.2, "total_pnl": 20.0}}
      )
      mock_gate.return_value.evaluate = AsyncMock(return_value={})
      mock_session = AsyncMock()
      mock_cm = AsyncMock()
      mock_cm.__aenter__.return_value = mock_session
      mock_cm.__aexit__.return_value = None
      mock_session_local.return_value = mock_cm
      return await bot._effective_scan_interval()

  assert asyncio.run(run()) == 5
