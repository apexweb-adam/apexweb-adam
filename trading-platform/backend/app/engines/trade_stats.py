"""Shared helpers for closed-trade statistics."""

from app.models.entities import Trade


def aggregate_win_rate(sells: list[Trade]) -> float:
  """Win rate across all closed sells (decisive trades only; breakeven excluded)."""
  winners = sum(1 for t in sells if t.is_winner is True)
  losers = sum(1 for t in sells if t.is_winner is False)
  decided = winners + losers
  return winners / decided if decided else 0.0
