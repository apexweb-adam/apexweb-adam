"""Tests for per-bot gate evaluation and graduation."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.engines.gate_entry_guard import try_graduate_paused_bots
from app.engines.profitability_gate import ProfitabilityGate, _sells_since
from app.models.entities import Trade


def _sell(bot: str, pnl: float, *, winner: bool, at: datetime) -> Trade:
  t = Trade(
    bot_type=bot,
    symbol="TEST",
    side="long",
    action="sell",
    quantity=1.0,
    price=100.0,
    pnl=pnl,
    is_winner=winner,
  )
  t.executed_at = at
  return t


def test_evaluate_per_bot_graduation_ready():
  gate = ProfitabilityGate(session=None)  # type: ignore[arg-type]
  start = datetime(2026, 8, 27, 15, 54, 5)
  sells = [
    _sell("crypto", 10, winner=True, at=datetime(2026, 8, 28, 10, 0))
    for _ in range(20)
  ]
  filtered = _sells_since(sells, start)
  metrics = gate._trade_metrics(filtered, [])
  assert metrics["total_trades"] == 20
  assert metrics["win_rate"] == 1.0


def test_try_graduate_paused_bots_unpauses_ready_bot():
  active_gate = {"win_rate": 0.60, "total_trades": 40}
  per_bot = {
    "crypto": {
      "paused": True,
      "graduation_ready": True,
      "total_trades": 25,
      "win_rate": 0.62,
    },
    "stocks_futures": {"paused": False, "graduation_ready": False},
  }

  with patch("app.engines.gate_entry_guard.ProfitabilityGate") as GateCls:
    GateCls.MIN_WIN_RATE = 0.55
    gate_inst = GateCls.return_value
    gate_inst.evaluate = AsyncMock(return_value=active_gate)
    gate_inst.evaluate_per_bot = AsyncMock(return_value=per_bot)
    with patch(
      "app.engines.platform_settings.is_bot_paused",
      AsyncMock(return_value=True),
    ):
      with patch(
        "app.engines.platform_settings.set_bot_paused",
        AsyncMock(),
      ) as set_pause:
        graduated = asyncio.run(try_graduate_paused_bots(MagicMock()))

  assert graduated == ["crypto"]
  set_pause.assert_awaited_once()
  args = set_pause.await_args.args
  assert args[1] == "crypto"
  assert args[2] is False


def test_try_graduate_skips_when_active_gate_weak():
  active_gate = {"win_rate": 0.48, "total_trades": 50}
  per_bot = {"crypto": {"paused": True, "graduation_ready": True}}

  with patch("app.engines.gate_entry_guard.ProfitabilityGate") as GateCls:
    GateCls.MIN_WIN_RATE = 0.55
    GateCls.return_value.evaluate = AsyncMock(return_value=active_gate)
    GateCls.return_value.evaluate_per_bot = AsyncMock(return_value=per_bot)
    with patch(
      "app.engines.platform_settings.set_bot_paused",
      AsyncMock(),
    ) as set_pause:
      graduated = asyncio.run(try_graduate_paused_bots(MagicMock()))

  assert graduated == []
  set_pause.assert_not_called()
