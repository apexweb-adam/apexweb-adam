"""Tests for commodities cap-trim position selection."""

from app.engines.strategy_migration import (
  select_commodities_excess_trim_targets,
  select_commodities_graduation_excess_trim_targets,
)
from app.models.entities import Position


def _pos(symbol: str, unrealized: float) -> Position:
  return Position(
    bot_type="commodities",
    symbol=symbol,
    side="long",
    quantity=1.0,
    entry_price=100.0,
    current_price=100.0 + unrealized,
    unrealized_pnl=unrealized,
  )


def test_trim_banks_profit_before_large_loser():
  positions = [
    _pos("SI=F", -31.0),
    _pos("CL=F", 2.0),
    _pos("NG=F", 0.0),
    _pos("XAUUSDT", -0.5),
  ]
  targets = select_commodities_excess_trim_targets(positions, cap=3)
  assert len(targets) == 1
  assert targets[0].symbol == "CL=F"


def test_trim_skips_large_losers_when_only_small_losses_trimmable():
  positions = [
    _pos("SI=F", -31.0),
    _pos("CL=F", -41.0),
    _pos("NG=F", -0.5),
    _pos("XAUUSDT", -20.0),
  ]
  targets = select_commodities_excess_trim_targets(positions, cap=3)
  assert len(targets) == 1
  assert targets[0].symbol == "NG=F"


def test_trim_returns_empty_when_only_large_losers_over_cap():
  positions = [
    _pos("SI=F", -31.0),
    _pos("CL=F", -41.0),
    _pos("NG=F", -10.0),
    _pos("XAUUSDT", -6.0),
  ]
  assert select_commodities_excess_trim_targets(positions, cap=3) == []


def test_trim_closes_multiple_profits_and_flat_first():
  positions = [
    _pos("SI=F", -31.0),
    _pos("CL=F", 3.0),
    _pos("NG=F", 0.0),
    _pos("XAUUSDT", -0.5),
    _pos("HG=F", 1.0),
  ]
  targets = select_commodities_excess_trim_targets(positions, cap=3)
  symbols = {p.symbol for p in targets}
  assert len(targets) == 2
  assert symbols == {"CL=F", "HG=F"}


def test_graduation_trim_prefers_loser_over_spot_profit():
  positions = [
    _pos("XAUUSDT", 0.34),
    _pos("PAXGUSDT", 0.12),
    _pos("CL=F", -0.47),
    _pos("EURUSD=X", 0.0),
  ]
  targets = select_commodities_graduation_excess_trim_targets(positions, cap=3)
  assert len(targets) == 1
  assert targets[0].symbol == "EURUSD=X"


def test_graduation_trim_at_effective_cap_no_excess():
  positions = [
    _pos("XAUUSDT", 0.34),
    _pos("PAXGUSDT", 0.12),
    _pos("CL=F", -0.47),
    _pos("EURUSD=X", 0.0),
  ]
  assert select_commodities_graduation_excess_trim_targets(positions, cap=4) == []


def test_graduation_trim_closes_loser_when_flat_already_at_cap():
  positions = [
    _pos("XAUUSDT", 0.34),
    _pos("PAXGUSDT", 0.12),
    _pos("CL=F", -0.47),
    _pos("NG=F", 0.0),
    _pos("EURUSD=X", 0.0),
  ]
  targets = select_commodities_graduation_excess_trim_targets(positions, cap=4)
  assert len(targets) == 1
  assert targets[0].symbol in {"EURUSD=X", "NG=F", "CL=F"}
