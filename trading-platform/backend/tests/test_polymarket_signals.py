"""Tests for Polymarket signal generation."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest

from app.engines.polymarket_signals import (
  PolymarketSignal,
  _price_momentum,
  analyze_polymarket,
)


def _price_df(prices: list[float]) -> pd.DataFrame:
  now = datetime.utcnow()
  return pd.DataFrame({
    "timestamp": [now] * len(prices),
    "open": prices,
    "high": prices,
    "low": prices,
    "close": prices,
    "volume": [1000] * len(prices),
  })


def test_price_momentum_requires_five_points():
  assert _price_momentum(_price_df([0.4, 0.41, 0.42, 0.43])) == 0.0
  mom = _price_momentum(_price_df([0.40, 0.41, 0.42, 0.43, 0.46]))
  assert mom == pytest.approx(0.15)


@pytest.mark.asyncio
async def test_analyze_polymarket_flags_overbought_sell():
  session = AsyncMock()
  session.execute = AsyncMock(
    return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
  )
  signal = await analyze_polymarket(
    session,
    "PM:trump-win",
    0.78,
    _price_df([0.70, 0.72, 0.74, 0.76, 0.78]),
    "Will Trump win?",
  )
  assert signal.direction == "sell"
  assert "overbought" in signal.reason.lower()


@pytest.mark.asyncio
async def test_analyze_polymarket_momentum_buy_in_value_zone():
  session = AsyncMock()
  session.execute = AsyncMock(
    return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
  )
  prices = [0.30, 0.31, 0.32, 0.33, 0.36]
  signal = await analyze_polymarket(
    session,
    "PM:fed-rate-cut",
    0.36,
    _price_df(prices),
    "Fed rate cut in 2025?",
  )
  assert signal.direction == "buy"
  assert "momentum" in signal.reason.lower()


@pytest.mark.asyncio
async def test_analyze_polymarket_holds_value_zone_with_bullish_intel():
  item = MagicMock()
  item.title = "Fed rate cut odds rise"
  item.content = "fed-rate-cut market pricing in September cut"
  item.url = ""
  item.sentiment = 0.35
  item.relevance_score = 0.8

  session = AsyncMock()
  session.execute = AsyncMock(
    return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[item]))))
  )
  signal = await analyze_polymarket(
    session,
    "PM:fed-rate-cut",
    0.48,
    _price_df([0.50, 0.49, 0.48, 0.47, 0.46]),
    "Fed rate cut in 2025?",
  )
  assert isinstance(signal, PolymarketSignal)
  assert signal.direction in ("hold", "buy")
  assert signal.direction != "sell"
