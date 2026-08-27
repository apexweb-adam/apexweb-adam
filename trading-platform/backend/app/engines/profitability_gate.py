from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.engines.platform_settings import get_verification_started_at
from app.models.entities import Portfolio, Trade


class ProfitabilityGate:
  """Tracks whether paper trading performance meets thresholds for live trading."""

  MIN_TRADES = 100
  MIN_WIN_RATE = 0.55
  MIN_PROFIT_FACTOR = 1.3
  MIN_DAYS = 30

  def __init__(self, session: AsyncSession):
    self.session = session

  async def evaluate(self) -> dict:
    portfolios = (await self.session.execute(select(Portfolio))).scalars().all()
    sells = (await self.session.execute(select(Trade).where(Trade.action == "sell"))).scalars().all()

    total_trades = len(sells)
    winners = [t for t in sells if t.is_winner]
    losers = [t for t in sells if t.is_winner is False]

    win_rate = len(winners) / total_trades if total_trades else 0
    gross_profit = sum(t.pnl for t in winners)
    gross_loss = abs(sum(t.pnl for t in losers))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf") if gross_profit > 0 else 0
    total_pnl = sum(p.total_pnl for p in portfolios)

    first_trade = (
      await self.session.execute(select(func.min(Trade.executed_at)))
    ).scalar_one_or_none()
    verification_start = await get_verification_started_at(self.session)
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
        "actual": round(profit_factor, 2) if profit_factor != float("inf") else "inf",
        "passed": profit_factor >= self.MIN_PROFIT_FACTOR,
      },
      "positive_pnl": {
        "required": 0,
        "actual": total_pnl,
        "passed": total_pnl > 0,
      },
      "min_days": {
        "required": self.MIN_DAYS,
        "actual": days_trading,
        "passed": days_trading >= self.MIN_DAYS,
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
    if days_trading < self.MIN_DAYS:
      blockers.append(f"{self.MIN_DAYS - days_trading} more days")
    if total_pnl <= 0:
      blockers.append("positive PnL")
    if profit_factor < self.MIN_PROFIT_FACTOR:
      blockers.append(f"profit factor ≥ {self.MIN_PROFIT_FACTOR}")
    if win_rate < self.MIN_WIN_RATE:
      blockers.append(f"win rate ≥ {self.MIN_WIN_RATE:.0%}")

    return {
      "live_trading_ready": live_ready,
      "paper_trading_only": settings.paper_trading_only,
      "total_trades": total_trades,
      "win_rate": win_rate,
      "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else None,
      "total_pnl": total_pnl,
      "days_trading": days_trading,
      "verification_started_at": verification_start.isoformat() if verification_start else None,
      "checks": checks,
      "recommendation": (
        "READY for live trading review" if live_ready
        else "Continue paper trading — need " + ", ".join(blockers)
      ),
    }
