"""Tests for verification-period underperformer detection."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.engines.gate_entry_guard import get_underperforming_bots


def test_get_underperforming_bots_uses_verification_period_wr():
  per_bot = {
    "commodities": {"total_trades": 30, "win_rate": 0.444},
    "crypto": {"total_trades": 60, "win_rate": 0.447},
    "polymarket": {"total_trades": 30, "win_rate": 0.36},
    "stocks_futures": {"total_trades": 15, "win_rate": 0.571},
  }

  with patch("app.engines.gate_entry_guard.ProfitabilityGate") as GateCls:
    GateCls.return_value.evaluate_per_bot = AsyncMock(return_value=per_bot)
    blocked = asyncio.run(get_underperforming_bots(MagicMock()))

  assert blocked == frozenset({"polymarket"})


def test_get_underperforming_bots_skips_low_trade_count():
  per_bot = {
    "stocks_futures": {"total_trades": 10, "win_rate": 0.30},
  }

  with patch("app.engines.gate_entry_guard.ProfitabilityGate") as GateCls:
    GateCls.return_value.evaluate_per_bot = AsyncMock(return_value=per_bot)
    blocked = asyncio.run(get_underperforming_bots(MagicMock()))

  assert blocked == frozenset()
