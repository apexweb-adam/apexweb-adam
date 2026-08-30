"""Synthetic TradingView intel must not inflate integration confluence."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.engines.integration_signals import (
  SYNTHETIC_INTEL_CATEGORY,
  get_integration_boost,
)
from app.models.entities import IntelligenceItem


def _tv_item(category: str, symbol: str = "NVDA") -> IntelligenceItem:
  return IntelligenceItem(
    source="tradingview",
    category=category,
    title=f"TradingView: buy {symbol}",
    content=f"buy {symbol}",
    url="tv:test",
    sentiment=0.5,
    relevance_score=0.9,
    symbols_mentioned=symbol,
    fetched_at=datetime.utcnow(),
  )


def test_synthetic_tradingview_excluded_from_boost():
  session = AsyncMock()
  items = [_tv_item(SYNTHETIC_INTEL_CATEGORY)]
  session.execute = AsyncMock(
    return_value=MagicMock(
      scalars=MagicMock(
        return_value=MagicMock(all=MagicMock(return_value=items))
      )
    )
  )

  with patch(
    "app.engines.integration_signals.get_intel_weight_multipliers",
    AsyncMock(return_value={}),
  ):
    boost, reason = asyncio.run(get_integration_boost(session, "NVDA"))
  assert boost == 0.0
  assert reason == ""


def test_real_tradingview_still_boosts():
  session = AsyncMock()
  items = [_tv_item("technical")]
  session.execute = AsyncMock(
    return_value=MagicMock(
      scalars=MagicMock(
        return_value=MagicMock(all=MagicMock(return_value=items))
      )
    )
  )

  with patch(
    "app.engines.integration_signals.get_intel_weight_multipliers",
    AsyncMock(return_value={}),
  ):
    boost, reason = asyncio.run(get_integration_boost(session, "NVDA"))
  assert boost > 0
  assert "tradingview" in reason
