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
  assert "newsapi" in LIVE_INTEL_SOURCES
  assert "hyperliquid" in LIVE_INTEL_SOURCES
  assert "wallet_tracker" in LIVE_INTEL_SOURCES


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


def test_extract_newsapi_bearish_impact():
  impact, confidence = _extract_live_intel_impact(
    "newsapi",
    "Fed signals higher rates for longer",
    "macro headline pressure on risk assets",
    "SPY",
    -0.42,
    0.78,
  )
  assert impact is not None
  assert "news headline" in impact.lower()
  assert "bearish" in impact.lower()
  assert confidence >= 0.55


def test_study_live_intel_sources_applies_newsapi_item():
  item = SimpleNamespace(
    id=4,
    source="newsapi",
    title="Oil prices surge on supply shock",
    content="energy markets rally",
    url="https://news.example/oil",
    symbols_mentioned="CL=F",
    sentiment=0.38,
    relevance_score=0.76,
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
  assert "commodities bot" in call_kwargs["impact"].lower()
  assert "news headline" in call_kwargs["impact"].lower()


def test_study_live_intel_sources_applies_reddit_item():
  item = SimpleNamespace(
    id=5,
    source="reddit",
    title="WSB yolo on NVDA",
    content="wallstreetbets bullish thread",
    url="https://reddit.example/nvda",
    symbols_mentioned="NVDA",
    sentiment=0.36,
    relevance_score=0.68,
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
  assert "reddit" in call_kwargs["impact"].lower()


def test_study_live_intel_sources_applies_tradingview_item():
  item = SimpleNamespace(
    id=6,
    source="tradingview",
    title="TradingView alert: AAPL buy",
    content="strategy order buy signal",
    url="https://tradingview.example/aapl",
    symbols_mentioned="AAPL",
    sentiment=0.25,
    relevance_score=0.82,
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
  assert "tradingview" in call_kwargs["impact"].lower()


def test_extract_hyperliquid_perp_momentum_impact():
  impact, confidence = _extract_live_intel_impact(
    "hyperliquid",
    "Hyperliquid perp momentum on WIF",
    "funding positive, open interest rising",
    "WIFUSDT",
    0.28,
    0.8,
  )
  assert impact is not None
  assert "hyperliquid" in impact.lower()
  assert "crypto bot" in impact.lower()
  assert confidence >= 0.6


def test_study_live_intel_sources_applies_hyperliquid_item():
  item = SimpleNamespace(
    id=7,
    source="hyperliquid",
    title="Hyperliquid perp momentum on WIF",
    content="funding positive, open interest rising",
    url="https://hyperliquid.example/wif",
    symbols_mentioned="WIFUSDT",
    sentiment=0.32,
    relevance_score=0.81,
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
  assert "hyperliquid" in call_kwargs["impact"].lower()
  assert "crypto bot" in call_kwargs["impact"].lower()
