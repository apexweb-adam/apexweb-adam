"""Tests for closed-trade statistics."""

from app.engines.trade_stats import aggregate_win_rate
from app.models.entities import Trade


def _sell(is_winner: bool | None, pnl: float = 0.0) -> Trade:
  t = Trade(
    bot_type="stocks_futures",
    symbol="NVDA",
    side="long",
    action="sell",
    quantity=1.0,
    price=100.0,
    pnl=pnl,
    is_winner=is_winner,
  )
  return t


def test_aggregate_win_rate_all_winners():
  sells = [_sell(True, 10), _sell(True, 5)]
  assert aggregate_win_rate(sells) == 1.0


def test_aggregate_win_rate_mixed():
  sells = [_sell(True, 10), _sell(False, -5), _sell(True, 3), _sell(False, -2)]
  assert aggregate_win_rate(sells) == 0.5


def test_aggregate_win_rate_excludes_breakeven():
  sells = [_sell(True, 10), _sell(None, 0), _sell(False, -5)]
  assert aggregate_win_rate(sells) == 0.5


def test_aggregate_win_rate_empty():
  assert aggregate_win_rate([]) == 0.0
