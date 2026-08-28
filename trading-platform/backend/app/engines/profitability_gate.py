from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.engines.platform_settings import get_paused_bot_types, get_verification_started_at
from app.engines.trade_stats import aggregate_win_rate
from app.models.entities import Portfolio, Trade


def _naive_utc(dt: datetime) -> datetime:
  if dt.tzinfo is not None:
    return dt.replace(tzinfo=None)
  return dt


def _sells_since(sells: list[Trade], since: datetime | None) -> list[Trade]:
  """Keep closed sells on or after the verification window start."""
  if since is None:
    return sells
  start = _naive_utc(since)
  return [
    t for t in sells
    if t.executed_at and _naive_utc(t.executed_at) >= start
  ]


class ProfitabilityGate:
  """Tracks whether paper trading performance meets thresholds for live trading."""

  MIN_TRADES = 100
  MIN_WIN_RATE = 0.55
  MIN_PROFIT_FACTOR = 1.3
  MIN_DAYS = 30

  def __init__(self, session: AsyncSession):
    self.session = session

  def _trade_metrics(
    self,
    sells: list[Trade],
    portfolios: list[Portfolio],
  ) -> dict[str, Any]:
    winners = [t for t in sells if t.is_winner is True]
    losers = [t for t in sells if t.is_winner is False]
    win_rate = aggregate_win_rate(sells)
    gross_profit = sum(t.pnl for t in winners)
    gross_loss = abs(sum(t.pnl for t in losers))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf") if gross_profit > 0 else 0
    total_pnl = sum(t.pnl for t in sells)
    return {
      "total_trades": len(sells),
      "win_rate": win_rate,
      "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else None,
      "total_pnl": total_pnl,
      "_profit_factor_raw": profit_factor,
    }

  async def evaluate(self) -> dict:
    portfolios = list((await self.session.execute(select(Portfolio))).scalars().all())
    sells = list(
      (await self.session.execute(select(Trade).where(Trade.action == "sell"))).scalars().all()
    )
    paused_bots = await get_paused_bot_types(self.session)
    paused_set = set(paused_bots)
    verification_start = await get_verification_started_at(self.session)

    period_sells = _sells_since(sells, verification_start)
    active_sells = [t for t in period_sells if t.bot_type not in paused_set]
    active_portfolios = [p for p in portfolios if p.bot_type not in paused_set]
    active_metrics = self._trade_metrics(active_sells, active_portfolios)
    aggregate_metrics = self._trade_metrics(period_sells, portfolios)
    from app.engines.equity_history import build_equity_history

    equity_history = build_equity_history(active_sells)

    total_trades = active_metrics["total_trades"]
    win_rate = active_metrics["win_rate"]
    profit_factor = active_metrics["_profit_factor_raw"]
    total_pnl = active_metrics["total_pnl"]

    first_trade = (
      await self.session.execute(select(func.min(Trade.executed_at)))
    ).scalar_one_or_none()
    period_start = verification_start
    if first_trade:
      if first_trade.tzinfo is not None:
        first_trade = first_trade.replace(tzinfo=None)
      if period_start is None or first_trade < period_start:
        period_start = first_trade
    if period_start:
      days_trading = (datetime.utcnow() - period_start).days
    else:
      days_trading = 0

    verification_day = days_trading + 1 if period_start else 0
    verification_days_remaining = max(0, self.MIN_DAYS - verification_day)

    checks = {
      "min_trades": {
        "required": self.MIN_TRADES,
        "actual": total_trades,
        "passed": total_trades >= self.MIN_TRADES,
      },
      "min_win_rate": {
        "required": self.MIN_WIN_RATE,
        "actual": win_rate,
        "passed": win_rate >= self.MIN_WIN_RATE,
      },
      "min_profit_factor": {
        "required": self.MIN_PROFIT_FACTOR,
        "actual": active_metrics["profit_factor"] if profit_factor != float("inf") else "inf",
        "passed": profit_factor >= self.MIN_PROFIT_FACTOR,
      },
      "positive_pnl": {
        "required": 0,
        "actual": total_pnl,
        "passed": total_pnl > 0,
      },
      "min_days": {
        "required": self.MIN_DAYS,
        "actual": verification_day,
        "passed": verification_day >= self.MIN_DAYS,
      },
      "paper_trading_only": {
        "required": True,
        "actual": settings.paper_trading_only,
        "passed": settings.paper_trading_only,
      },
    }

    all_passed = all(
      c["passed"]
      for key, c in checks.items()
      if key != "paper_trading_only"
    )
    live_ready = all_passed and total_trades >= self.MIN_TRADES

    blockers: list[str] = []
    if total_trades < self.MIN_TRADES:
      blockers.append(f"{self.MIN_TRADES - total_trades} more trades")
    if verification_day < self.MIN_DAYS:
      blockers.append(f"{max(0, self.MIN_DAYS - verification_day)} more days")
    if total_pnl <= 0:
      blockers.append("positive PnL")
    if profit_factor < self.MIN_PROFIT_FACTOR:
      blockers.append(f"profit factor ≥ {self.MIN_PROFIT_FACTOR}")
    if win_rate < self.MIN_WIN_RATE:
      blockers.append(f"win rate ≥ {self.MIN_WIN_RATE:.0%}")

    recommendation = (
      "READY for live trading review" if live_ready
      else "Continue paper trading — need " + ", ".join(blockers)
    )
    if paused_bots:
      recommendation += f" (excludes paused: {', '.join(paused_bots)})"

    return {
      "live_trading_ready": live_ready,
      "paper_trading_only": settings.paper_trading_only,
      "paused_bots": paused_bots,
      "total_trades": total_trades,
      "win_rate": win_rate,
      "profit_factor": active_metrics["profit_factor"],
      "total_pnl": total_pnl,
      "days_trading": days_trading,
      "verification_day": verification_day,
      "verification_days_remaining": verification_days_remaining,
      "verification_started_at": verification_start.isoformat() if verification_start else None,
      "checks": checks,
      "recommendation": recommendation,
      "aggregate": {
        "total_trades": aggregate_metrics["total_trades"],
        "win_rate": aggregate_metrics["win_rate"],
        "profit_factor": aggregate_metrics["profit_factor"],
        "total_pnl": aggregate_metrics["total_pnl"],
      },
      "equity_history": equity_history,
    }
