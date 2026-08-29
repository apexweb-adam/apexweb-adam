"""Tests for shadow excess position trimming."""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.engines.strategy_migration import close_excess_shadow_positions


def _position(symbol: str, unrealized: float) -> SimpleNamespace:
  return SimpleNamespace(
    symbol=symbol,
    unrealized_pnl=unrealized,
    current_price=100.0,
    entry_price=99.0,
    quantity=1.0,
    opened_at=datetime.now(timezone.utc),
  )


def test_close_excess_shadow_positions_closes_worst_loser():
  positions = [_position("LINKUSDT", -1.13), _position("BNBUSDT", 0.13)]

  engine = MagicMock()
  engine.get_open_positions = AsyncMock(return_value=positions)
  engine.sell = AsyncMock(return_value={"symbol": "LINKUSDT"})

  per_bot = {
    "crypto": {
      "win_rate": 0.414,
      "profit_factor": 0.97,
      "total_pnl": -4.13,
    },
  }

  async def paused(session, bot_type: str) -> bool:
    return bot_type == "crypto"

  with patch(
    "app.engines.strategy_migration.is_bot_paused",
    paused,
  ):
    with patch("app.engines.profitability_gate.ProfitabilityGate") as GateCls:
      GateCls.return_value.evaluate_per_bot = AsyncMock(return_value=per_bot)
      with patch(
        "app.engines.gate_entry_guard.shadow_max_open_for_bot",
        return_value=1,
      ):
        with patch(
          "app.engines.paper_trading.PaperTradingEngine",
          return_value=engine,
        ):
          with patch(
            "app.engines.market_data.fetch_crypto_data",
            AsyncMock(return_value=(10.0, None)),
          ):
            session = MagicMock()
            session.commit = AsyncMock()
            closed = asyncio.run(close_excess_shadow_positions(session))

  assert closed == 1
  engine.sell.assert_awaited_once()
  assert engine.sell.await_args.args[0] == "LINKUSDT"


def test_close_excess_shadow_positions_skips_active_gate_bot():
  with patch(
    "app.engines.strategy_migration.is_bot_paused",
    AsyncMock(return_value=False),
  ):
    with patch("app.engines.profitability_gate.ProfitabilityGate") as GateCls:
      GateCls.return_value.evaluate_per_bot = AsyncMock(return_value={})
      closed = asyncio.run(close_excess_shadow_positions(MagicMock()))

  assert closed == 0
