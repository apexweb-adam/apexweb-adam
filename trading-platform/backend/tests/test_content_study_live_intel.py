"""Tests for live intel → content study insight extraction."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.intelligence.content_study import (
  LIVE_INTEL_SOURCES,
  ContentStudyEngine,
  _extract_live_intel_impact,
  _extract_youtube_impact,
)


def test_live_intel_sources_include_political_and_tradingview():
  assert "political" in LIVE_INTEL_SOURCES
  assert "tradingview" in LIVE_INTEL_SOURCES
  assert "tiktok" in LIVE_INTEL_SOURCES


def test_extract_youtube_rsi_divergence_impact():
  impact, confidence = _extract_youtube_impact(
    "RSI divergence trading strategy",
    "how to spot bullish divergence",
  )
  assert impact is not None
  assert "rsi" in impact.lower()
  assert confidence >= 0.75


def test_extract_youtube_gold_commodities_impact():
  impact, confidence = _extract_youtube_impact(
    "Gold trading strategy 2024",
    "commodities breakout playbook",
  )
  assert impact is not None
  assert "commodities" in impact.lower()
  assert confidence >= 0.7


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


def test_study_live_intel_sources_applies_political_item():
  item = SimpleNamespace(
    id=2,
    source="political",
    title="US imposes new tariff on steel imports",
    content="trade war escalation",
    url="https://news.example/tariff",
    symbols_mentioned="GC=F",
    sentiment=0.35,
    relevance_score=0.72,
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
  assert "tariff" in call_kwargs["impact"].lower()
  assert "commodities" in call_kwargs["impact"].lower()


def test_study_live_intel_sources_applies_tiktok_item():
  item = SimpleNamespace(
    id=3,
    source="tiktok",
    title="PEPE pump viral on TikTok",
    content="memecoin crypto trading trend",
    url="https://news.example/tiktok-pepe",
    symbols_mentioned="PEPEUSDT",
    sentiment=0.4,
    relevance_score=0.72,
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
  call_kwargs = learner.apply_external_insight.await_args.kwargs
  assert "crypto bot" in call_kwargs["impact"].lower()
  assert "tiktok" in call_kwargs["impact"].lower()


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


def test_extract_tiktok_stock_sentiment_impact():
  impact, confidence = _extract_live_intel_impact(
    "tiktok",
    "AAPL day trading strategy viral on TikTok",
    "stock picks earnings play",
    "AAPL",
    0.3,
    0.7,
  )
  assert impact is not None
  assert "stocks_futures bot" in impact.lower()
  assert confidence >= 0.59


def test_extract_political_tariff_impact():
  impact, confidence = _extract_live_intel_impact(
    "political",
    "US imposes new tariff on steel imports",
    "trade war escalation",
    "GC=F",
    0.25,
    0.72,
  )
  assert impact is not None
  assert "tariff" in impact.lower()
  assert "commodities" in impact.lower()
  assert confidence >= 0.55
