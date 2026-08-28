"""Tests for memecoin integration confluence boost."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from app.engines.integration_signals import get_integration_boost
from app.models.entities import IntelligenceItem


def _item(source: str, sentiment: float, symbol: str = "WIFUSDT") -> IntelligenceItem:
  return IntelligenceItem(
    source=source,
    category="crypto",
    title=f"{source} signal",
    content=f"{symbol} move",
    url=f"{source}:test",
    sentiment=sentiment,
    relevance_score=0.8,
    symbols_mentioned=symbol,
    fetched_at=datetime.utcnow(),
  )


def test_memecoin_confluence_boost_when_dex_and_hl_bullish():
  session = AsyncMock()
  items = [
    _item("dexscreener", 0.45),
    _item("hyperliquid", 0.35),
  ]
  session.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=items)))))

  boost, reason = asyncio.run(get_integration_boost(session, "WIFUSDT"))
  assert boost > 0.05
  assert "memecoin_confluence" in reason
