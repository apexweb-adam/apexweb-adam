"""Tests for live intel → content study insight extraction."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.intelligence.content_study import (
  ContentStudyEngine,
  _extract_live_intel_impact,
)


def test_extract_fomo_buy_impact_targets_crypto():
  impact, confidence = _extract_live_intel_impact(
    "fomo",
    "legend bought PEPE",
    "rank 3 trader opened PEPE",
    "PEPEUSDT",
    0.62,
    0.75,
  )
  assert impact is not None
  assert "crypto bot" in impact.lower()
  assert "fomo" in impact.lower()
  assert confidence >= 0.6


def test_extract_dexscreener_boost_impact():
  impact, confidence = _extract_live_intel_impact(
    "dexscreener",
    "[DexScreener boost] WIF trending",
    "boost=5000",
    "WIFUSDT",
    0.35,
    0.72,
  )
  assert impact is not None
  assert "dexscreener" in impact.lower()
  assert "crypto bot" in impact.lower()
  assert confidence >= 0.6


def test_extract_wallet_whale_sell_impact():
  impact, _ = _extract_live_intel_impact(
    "wallet_tracker",
    "Whale sell ETH",
    "large distribution detected",
    "ETHUSDT",
    -0.4,
    0.7,
  )
  assert impact is not None
  assert "whale" in impact.lower()
  assert "tighten" in impact.lower()


def test_study_live_intel_sources_applies_fomo_item():
  item = SimpleNamespace(
    id=1,
    source="fomo",
    title="top trader buy WIF",
    content="leaderboard entry",
    url="https://fomo.family/trade/1",
    symbols_mentioned="WIFUSDT",
    sentiment=0.55,
    relevance_score=0.8,
    applied=False,
  )

  session = AsyncMock()
  session.execute = AsyncMock(
    return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[item]))))
  )
  session.commit = AsyncMock()

  insight = MagicMock(applied=True)
  learner = MagicMock()
  learner.apply_external_insight = AsyncMock(return_value=insight)

  engine = ContentStudyEngine(session)
  engine.learner = learner

  applied = asyncio.run(engine._study_live_intel_sources())

  assert applied == 1
  learner.apply_external_insight.assert_awaited_once()
  assert item.applied is True
  call_kwargs = learner.apply_external_insight.await_args.kwargs
  assert "crypto bot" in call_kwargs["impact"].lower()


def test_extract_x_crypto_bullish_impact():
  impact, confidence = _extract_live_intel_impact(
    "x",
    "Bitcoin breaking out",
    "BTC momentum on X",
    "BTCUSDT",
    0.45,
    0.7,
  )
  assert impact is not None
  assert "crypto bot" in impact.lower()
  assert confidence >= 0.55


def test_extract_tradingview_alert_impact():
  impact, confidence = _extract_live_intel_impact(
    "tradingview",
    "TradingView alert: AAPL buy",
    "strategy order buy",
    "AAPL",
    0.3,
    0.85,
  )
  assert impact is not None
  assert "tradingview" in impact.lower()
  assert "technical_weight" in impact.lower()
  assert confidence >= 0.6


def test_extract_reddit_wsb_impact():
  impact, _ = _extract_live_intel_impact(
    "reddit",
    "WSB yolo on PEPE",
    "wallstreetbets discussion",
    "PEPEUSDT",
    0.35,
    0.65,
  )
  assert impact is not None
  assert "reddit" in impact.lower()
  assert "crypto bot" in impact.lower()
