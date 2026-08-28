from datetime import datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.profitability_gate import ProfitabilityGate
from app.models.entities import VerificationSnapshot

PERFORMANCE_CHECK_KEYS = ("min_win_rate", "min_profit_factor", "positive_pnl", "paper_trading_only")


def serialize_verification_snapshot(snapshot: VerificationSnapshot) -> dict[str, Any]:
  return {
    "snapshot_date": snapshot.snapshot_date,
    "verification_day": snapshot.verification_day,
    "total_trades": snapshot.total_trades,
    "win_rate": snapshot.win_rate,
    "profit_factor": snapshot.profit_factor,
    "total_pnl": snapshot.total_pnl,
    "performance_checks_passed": snapshot.performance_checks_passed,
    "live_trading_ready": snapshot.live_trading_ready,
    "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
  }


async def record_verification_snapshot(session: AsyncSession, *, when: datetime | None = None) -> VerificationSnapshot:
  """Upsert daily gate metrics for the 30-day verification audit trail."""
  now = when or datetime.utcnow()
  snapshot_date = now.strftime("%Y-%m-%d")
  gate = await ProfitabilityGate(session).evaluate()
  checks = gate.get("checks", {})
  performance_passed = all(checks.get(key, {}).get("passed") for key in PERFORMANCE_CHECK_KEYS)

  existing = (
    await session.execute(
      select(VerificationSnapshot).where(VerificationSnapshot.snapshot_date == snapshot_date)
    )
  ).scalar_one_or_none()

  pf = gate.get("profit_factor")
  pf_value = 0.0 if pf is None else float(pf)

  if existing:
    existing.verification_day = gate.get("verification_day") or 0
    existing.total_trades = gate.get("total_trades") or 0
    existing.win_rate = gate.get("win_rate") or 0.0
    existing.profit_factor = pf_value
    existing.total_pnl = gate.get("total_pnl") or 0.0
    existing.performance_checks_passed = performance_passed
    existing.live_trading_ready = bool(gate.get("live_trading_ready"))
    snapshot = existing
  else:
    snapshot = VerificationSnapshot(
      snapshot_date=snapshot_date,
      verification_day=gate.get("verification_day") or 0,
      total_trades=gate.get("total_trades") or 0,
      win_rate=gate.get("win_rate") or 0.0,
      profit_factor=pf_value,
      total_pnl=gate.get("total_pnl") or 0.0,
      performance_checks_passed=performance_passed,
      live_trading_ready=bool(gate.get("live_trading_ready")),
    )
    session.add(snapshot)

  await session.commit()
  await session.refresh(snapshot)
  return snapshot
