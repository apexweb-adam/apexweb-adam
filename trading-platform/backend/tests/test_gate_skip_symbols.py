"""Tests for gate skip symbol helpers."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from app.engines.gate_entry_guard import (
  gate_entry_guards_active,
  get_gate_skip_symbols,
  get_large_recent_loss_symbols,
  get_recent_loser_symbols,
  is_symbol_in_trade_cooldown,
  get_review_blocked_symbols,
)


def _trade_row(symbol: str, is_winner: bool | None):
  return (symbol, is_winner)


def test_is_symbol_in_trade_cooldown_after_win():
  session = AsyncMock()
  executed = datetime.utcnow() - timedelta(minutes=5)
  session.execute = AsyncMock(
    return_value=MagicMock(first=lambda: (True, executed))
  )
  blocked = asyncio.run(is_symbol_in_trade_cooldown(session, "commodities", "SI=F"))
  assert blocked is True


def test_is_symbol_in_trade_cooldown_expired():
  session = AsyncMock()
  executed = datetime.utcnow() - timedelta(hours=2)
  session.execute = AsyncMock(
    return_value=MagicMock(first=lambda: (True, executed))
  )
  blocked = asyncio.run(is_symbol_in_trade_cooldown(session, "commodities", "SI=F"))
  assert blocked is False


def test_large_recent_loss_symbols_blocks_until_win():
  session = AsyncMock()
  rows = [
    ("NVDA", -71.82, False, datetime.utcnow()),
    ("AAPL", 0.26, True, datetime.utcnow()),
  ]
  session.execute = AsyncMock(return_value=MagicMock(all=lambda: rows))

  blocked = asyncio.run(get_large_recent_loss_symbols(session, "stocks_futures"))
  assert "NVDA" in blocked
  assert "AAPL" not in blocked


def test_gate_entry_guards_active_during_verification():
  tightening = MagicMock(active=False)
  assert gate_entry_guards_active(
    gate_tightening=tightening, shadow_mode=False, live_trading_ready=False
  ) is True
  assert gate_entry_guards_active(
    gate_tightening=tightening, shadow_mode=False, live_trading_ready=True
  ) is False


def test_recent_loser_symbols_blocks_zero_win_streak():
  session = AsyncMock()
  cutoff_losses = [
    _trade_row("TSLA", False),
    _trade_row("TSLA", False),
    _trade_row("NVDA", True),
    _trade_row("NVDA", False),
  ]
  session.execute = AsyncMock(return_value=MagicMock(all=lambda: cutoff_losses))

  blocked = asyncio.run(get_recent_loser_symbols(session, "stocks_futures"))
  assert "TSLA" in blocked
  assert "NVDA" not in blocked


def test_review_blocked_symbols_parses_gate_skip_recommendation():
  session = AsyncMock()
  session.execute = AsyncMock(
    return_value=MagicMock(
      all=lambda: [
        (
          "Most losses on CL=F (2 trades); "
          "Gate skip recommended for CL=F until win rate recovers",
        ),
      ]
    )
  )
  blocked = asyncio.run(get_review_blocked_symbols(session, "commodities"))
  assert "CL=F" in blocked


def test_review_blocked_symbols_parses_patterns():
  session = AsyncMock()
  session.execute = AsyncMock(
    return_value=MagicMock(
      all=lambda: [
        ("More losing trades than winning; Most losses on ETHUSDT (3 trades)",),
      ]
    )
  )
  blocked = asyncio.run(get_review_blocked_symbols(session, "crypto"))
  assert "ETHUSDT" in blocked


def test_gate_skip_unions_sources():
  session = AsyncMock()

  async def fake_chronic(s, bot):
    return frozenset({"CHRONIC"})

  async def fake_recent(s, bot):
    return frozenset({"RECENT"})

  async def fake_large(s, bot):
    return frozenset({"LARGE"})

  async def fake_review(s, bot):
    return frozenset({"REVIEW"})

  import app.engines.gate_entry_guard as mod

  orig = (
    mod.get_chronic_loser_symbols,
    mod.get_recent_loser_symbols,
    mod.get_large_recent_loss_symbols,
    mod.get_review_blocked_symbols,
  )
  mod.get_chronic_loser_symbols = fake_chronic
  mod.get_recent_loser_symbols = fake_recent
  mod.get_large_recent_loss_symbols = fake_large
  mod.get_review_blocked_symbols = fake_review
  try:
    skip = asyncio.run(get_gate_skip_symbols(session, "crypto"))
    assert skip == frozenset({"CHRONIC", "RECENT", "LARGE", "REVIEW"})
  finally:
    (
      mod.get_chronic_loser_symbols,
      mod.get_recent_loser_symbols,
      mod.get_large_recent_loss_symbols,
      mod.get_review_blocked_symbols,
    ) = orig
