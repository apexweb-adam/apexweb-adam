"""Tests for stocks gate scan interval during trade-count prep / Monday open."""

from unittest.mock import AsyncMock, MagicMock, patch

from app.bots.trading_bots import StocksFuturesBot
from app.engines.gate_entry_guard import GateEntryTightening


def test_stocks_effective_scan_interval_imminent_open():
  import asyncio

  bot = StocksFuturesBot()
  session_info = {"in_session": False, "minutes_until_open": 15, "minutes_since_open": 0}
  tightening = GateEntryTightening(
    active=True,
    win_rate=0.57,
    min_sentiment=0.0,
    require_macd_bullish=False,
    min_composite_boost=0.0,
    blocked_new_entries=frozenset(),
    max_commodities_open_positions=3,
  )
  gate_cls = MagicMock()
  gate_cls.MIN_TRADES = 100
  gate_instance = gate_cls.return_value
  gate_instance.evaluate = AsyncMock(
    return_value={"total_trades": 40, "shadow_mode": True}
  )
  gate_instance.evaluate_per_bot = AsyncMock(
    return_value={
      "stocks_futures": {
        "win_rate": 0.57,
        "profit_factor": 0.62,
        "total_trades": 15,
        "total_pnl": -52.3,
      }
    }
  )

  async def run() -> int:
    with patch.object(bot, "_in_us_session", return_value=False), patch(
      "app.engines.gate_entry_guard.stocks_session_info",
      return_value=session_info,
    ), patch(
      "app.engines.gate_entry_guard.bot_win_rate_for_graduation_nudge",
      return_value=0.57,
    ), patch(
      "app.engines.gate_entry_guard.stocks_trade_count_graduation_nudge",
      return_value=True,
    ), patch(
      "app.engines.gate_entry_guard.stocks_gate_fast_scan_active",
      return_value=True,
    ), patch(
      "app.engines.profitability_gate.ProfitabilityGate",
      gate_cls,
    ), patch(
      "app.bots.trading_bots.SessionLocal",
    ) as mock_session_local, patch(
      "app.bots.trading_bots.get_gate_entry_tightening",
      new_callable=AsyncMock,
      return_value=tightening,
    ), patch(
      "app.engines.session_open_log.get_prep_phase_state",
      new_callable=AsyncMock,
      return_value={},
    ), patch(
      "app.config.settings.paper_trading_only",
      True,
    ):
      mock_session = AsyncMock()
      mock_cm = AsyncMock()
      mock_cm.__aenter__.return_value = mock_session
      mock_cm.__aexit__.return_value = None
      mock_session_local.return_value = mock_cm
      return await bot._effective_scan_interval()

  assert asyncio.run(run()) == 5
