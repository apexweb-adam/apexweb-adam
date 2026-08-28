"""Tests for gate skip symbol helpers."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.engines.gate_entry_guard import (
  get_gate_skip_symbols,
  get_recent_loser_symbols,
  get_review_blocked_symbols,
)


def _trade_row(symbol: str, is_winner: bool | None):
  return (symbol, is_winner)


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

  async def fake_review(s, bot):
    return frozenset({"REVIEW"})

  import app.engines.gate_entry_guard as mod

  orig = (
    mod.get_chronic_loser_symbols,
    mod.get_recent_loser_symbols,
    mod.get_review_blocked_symbols,
  )
  mod.get_chronic_loser_symbols = fake_chronic
  mod.get_recent_loser_symbols = fake_recent
  mod.get_review_blocked_symbols = fake_review
  try:
    skip = asyncio.run(get_gate_skip_symbols(session, "crypto"))
    assert skip == frozenset({"CHRONIC", "RECENT", "REVIEW"})
  finally:
    (
      mod.get_chronic_loser_symbols,
      mod.get_recent_loser_symbols,
      mod.get_review_blocked_symbols,
    ) = orig
