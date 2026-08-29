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


def test_exclude_feed_artifact_sells_drops_proxy_wind_down():
  from app.engines.profitability_gate import _exclude_feed_artifact_sells

  artifact = _sell("commodities", False, -9.44)
  artifact.symbol = "XAUUSDT"
  artifact.reason = "Gate graduation wind-down (uPnL $-9.44) | MACD bullish"
  real_loss = _sell("commodities", False, -5.0)
  real_loss.symbol = "NG=F"
  real_loss.reason = "Stop loss triggered"
  win = _sell("commodities", True, 12.0)
  win.symbol = "CL=F"

  filtered = _exclude_feed_artifact_sells([artifact, real_loss, win])
  assert len(filtered) == 2
  assert artifact not in filtered


def test_trade_metrics_excludes_feed_artifact_losses():
  from app.engines.profitability_gate import _exclude_feed_artifact_sells

  gate = ProfitabilityGate(session=None)  # type: ignore[arg-type]
  artifact = _sell("commodities", False, -9.44)
  artifact.symbol = "XAUUSDT"
  artifact.reason = "Gate graduation wind-down (uPnL $-9.44)"
  sells = [
    _sell("commodities", True, 10.0),
    _sell("commodities", True, 8.0),
    artifact,
    _sell("commodities", False, -4.0),
  ]
  m = gate._trade_metrics(_exclude_feed_artifact_sells(sells), [])
  assert m["total_trades"] == 3
  assert m["total_pnl"] == 14.0


def test_sells_since_filters_before_verification_start():
  from datetime import datetime

  from app.engines.profitability_gate import _sells_since

  start = datetime(2026, 8, 27, 15, 54, 5)
  old = _sell("stocks_futures", True, 10)
  old.executed_at = datetime(2026, 8, 27, 10, 0, 0)
  new = _sell("stocks_futures", True, 5)
  new.executed_at = datetime(2026, 8, 27, 19, 0, 0)
  filtered = _sells_since([old, new], start)
  assert len(filtered) == 1
  assert filtered[0].pnl == 5
