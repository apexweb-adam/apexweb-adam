"""Tests for CRM live snapshot."""

from unittest.mock import AsyncMock, MagicMock, patch

import asyncio

from app.engines.crm_summary import build_crm_live_snapshot


def test_build_crm_live_snapshot_includes_positions_and_tightening():
  position = MagicMock(
    bot_type="commodities",
    symbol="CL=F",
    side="long",
    entry_price=83.44,
    current_price=83.4,
    unrealized_pnl=-0.47,
  )
  session = AsyncMock()
  session.execute = AsyncMock(
    return_value=type("Result", (), {"scalars": lambda self: type("S", (), {"all": lambda self: [position]})()})()
  )

  gate_payload = {
    "gate_entry_tightening": {
      "active": True,
      "win_rate": 0.44,
      "min_sentiment": 0.08,
      "require_macd_bullish": True,
      "blocked_new_entries": ["crypto"],
      "max_commodities_open_positions": 2,
      "proven_winner_symbols": {"commodities": ["SI=F"]},
      "chronic_loser_symbols": {},
    }
  }

  with patch(
    "app.engines.crm_summary.get_paused_bot_types",
    new_callable=AsyncMock,
    return_value=frozenset({"crypto", "stocks_futures", "polymarket"}),
  ):
    with patch(
      "app.engines.crm_summary.build_gate_ws_payload",
      new_callable=AsyncMock,
      return_value=gate_payload,
    ):
      result = asyncio.run(build_crm_live_snapshot(session))

  assert result["active_bots"] == ["commodities"]
  assert len(result["positions"]) == 1
  assert result["positions"][0]["is_active_gate"] is True
  assert result["gate_tightening"]["require_macd_bullish"] is True
  assert result["proven_winner_symbols"]["commodities"] == ["SI=F"]
