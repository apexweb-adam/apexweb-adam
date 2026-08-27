"""Daily cumulative realized PnL from closed sells."""

from __future__ import annotations

from typing import Any

from app.models.entities import Trade


def build_equity_history(sells: list[Trade]) -> list[dict[str, Any]]:
  by_day: dict[str, float] = {}
  for t in sells:
    if not t.executed_at:
      continue
    day = t.executed_at.strftime("%Y-%m-%d")
    by_day[day] = by_day.get(day, 0.0) + t.pnl

  cumulative = 0.0
  points: list[dict[str, Any]] = []
  for day in sorted(by_day.keys()):
    cumulative += by_day[day]
    points.append(
      {
        "date": day,
        "daily_pnl": round(by_day[day], 2),
        "cumulative_pnl": round(cumulative, 2),
      }
    )
  return points
