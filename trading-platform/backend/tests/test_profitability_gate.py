"""Tests for profitability gate trade metrics."""

from app.engines.profitability_gate import ProfitabilityGate
from app.models.entities import Portfolio, Trade


def _sell(bot: str, is_winner: bool | None, pnl: float) -> Trade:
  return Trade(
    bot_type=bot,
    symbol="TEST",
    side="long",
    action="sell",
    quantity=1.0,
    price=100.0,
    pnl=pnl,
    is_winner=is_winner,
  )


def _portfolio(bot: str, total_pnl: float) -> Portfolio:
  return Portfolio(bot_type=bot, total_pnl=total_pnl, balance=100_000, equity=100_000)


def test_trade_metrics_win_rate_and_profit_factor():
  gate = ProfitabilityGate(session=None)  # type: ignore[arg-type]
  sells = [
    _sell("stocks_futures", True, 50),
    _sell("stocks_futures", True, 30),
    _sell("crypto", False, -20),
    _sell("crypto", False, -10),
  ]
  portfolios = [_portfolio("stocks_futures", 80), _portfolio("crypto", -30)]
  m = gate._trade_metrics(sells, portfolios)
  assert m["total_trades"] == 4
  assert m["win_rate"] == 0.5
  assert m["profit_factor"] == 2.67
  assert m["total_pnl"] == 50


def test_trade_metrics_all_winners_infinite_pf():
  gate = ProfitabilityGate(session=None)  # type: ignore[arg-type]
  sells = [_sell("stocks_futures", True, 10), _sell("stocks_futures", True, 5)]
  portfolios = [_portfolio("stocks_futures", 15)]
  m = gate._trade_metrics(sells, portfolios)
  assert m["win_rate"] == 1.0
  assert m["_profit_factor_raw"] == float("inf")
