"""Tests for post-mortem idempotency and bot-specific rules."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.engines.learning_engine import LearningEngine


def _trade(**overrides):
  trade = MagicMock()
  trade.id = 99
  trade.bot_type = "stocks_futures"
  trade.symbol = "AAPL"
  trade.pnl = -2.0
  trade.pnl_pct = -0.8
  trade.signal_score = 0.42
  trade.sentiment_score = 0.1
  trade.side = "long"
  trade.reason = "Sell signal: MACD bearish crossover"
  trade.executed_at = datetime(2026, 8, 29, 20, 0, 0)
  for key, value in overrides.items():
    setattr(trade, key, value)
  return trade


def test_analyze_losing_trade_returns_existing_analysis():
  prior = MagicMock()
  session = AsyncMock()
  session.execute = AsyncMock(
    return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=prior))
  )

  learner = LearningEngine(session)
  result = asyncio.run(learner.analyze_losing_trade(_trade()))

  assert result is prior


def test_analyze_losing_trade_flags_stocks_macd_bearish():
  session = AsyncMock()
  session.execute = AsyncMock(
    side_effect=[
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ]
  )
  session.commit = AsyncMock()
  session.add = MagicMock()

  learner = LearningEngine(session)
  learner._get_market_context = AsyncMock(return_value="context")
  learner._had_source_intel = AsyncMock(return_value=False)
  learner._apply_adjustments = AsyncMock()
  learner.run_daily_review = AsyncMock(return_value=MagicMock())

  with patch("app.ws_manager.push_live_update", new_callable=AsyncMock):
    analysis = asyncio.run(learner.analyze_losing_trade(_trade()))

  assert "macd" in analysis.root_cause.lower()
  learner._apply_adjustments.assert_awaited_once()


def test_analyze_losing_trade_flags_commodities_weekend():
  session = AsyncMock()
  session.execute = AsyncMock(
    side_effect=[
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ]
  )
  session.commit = AsyncMock()
  session.add = MagicMock()

  trade = _trade(
    bot_type="commodities",
    symbol="GC=F",
    reason="Weekend gap exit on gold futures",
  )

  learner = LearningEngine(session)
  learner._get_market_context = AsyncMock(return_value="context")
  learner._had_source_intel = AsyncMock(return_value=False)
  learner._apply_adjustments = AsyncMock()
  learner.run_daily_review = AsyncMock(return_value=MagicMock())

  with patch("app.ws_manager.push_live_update", new_callable=AsyncMock):
    analysis = asyncio.run(learner.analyze_losing_trade(trade))

  assert "weekend" in analysis.root_cause.lower()


def test_analyze_losing_trade_flags_polymarket_overbought():
  session = AsyncMock()
  session.execute = AsyncMock(
    side_effect=[
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ]
  )
  session.commit = AsyncMock()
  session.add = MagicMock()

  trade = _trade(
    bot_type="polymarket",
    symbol="PM:trump-tariff",
    reason="PM:Yes price overbought (>0.72); Intel bullish (+0.35)",
    signal_score=0.38,
  )

  learner = LearningEngine(session)
  learner._get_market_context = AsyncMock(return_value="context")
  learner._had_fomo_intel = AsyncMock(return_value=False)
  learner._had_source_intel = AsyncMock(return_value=False)
  learner._apply_adjustments = AsyncMock()
  learner.run_daily_review = AsyncMock(return_value=MagicMock())

  with patch("app.ws_manager.push_live_update", new_callable=AsyncMock):
    analysis = asyncio.run(learner.analyze_losing_trade(trade))

  assert "overbought" in analysis.root_cause.lower()
  assert "0.72" in analysis.strategy_adjustment


def test_analyze_losing_trade_flags_stocks_monday_gate_skip():
  session = AsyncMock()
  session.execute = AsyncMock(
    side_effect=[
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ]
  )
  session.commit = AsyncMock()
  session.add = MagicMock()

  trade = _trade(
    reason="[shadow] Signal:0.42 Sentiment:0.35 | RSI oversold | monday_gate_skip | session_open_burst",
  )

  learner = LearningEngine(session)
  learner._get_market_context = AsyncMock(return_value="context")
  learner._had_source_intel = AsyncMock(return_value=False)
  learner._apply_adjustments = AsyncMock()
  learner.run_daily_review = AsyncMock(return_value=MagicMock())

  with patch("app.ws_manager.push_live_update", new_callable=AsyncMock):
    analysis = asyncio.run(learner.analyze_losing_trade(trade))

  assert "gate-skip" in analysis.root_cause.lower() or "session-open" in analysis.root_cause.lower()
  assert "MACD" in analysis.strategy_adjustment


def test_analyze_losing_trade_flags_commodities_monday_futures_gate_skip():
  session = AsyncMock()
  session.execute = AsyncMock(
    side_effect=[
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ]
  )
  session.commit = AsyncMock()
  session.add = MagicMock()

  trade = _trade(
    bot_type="commodities",
    symbol="NG=F",
    reason="[shadow] Signal:0.44 Sentiment:0.2 | momentum buy | monday_futures_gate_skip",
  )

  learner = LearningEngine(session)
  learner._get_market_context = AsyncMock(return_value="context")
  learner._had_source_intel = AsyncMock(return_value=False)
  learner._apply_adjustments = AsyncMock()
  learner.run_daily_review = AsyncMock(return_value=MagicMock())

  with patch("app.ws_manager.push_live_update", new_callable=AsyncMock):
    analysis = asyncio.run(learner.analyze_losing_trade(trade))

  assert "cme" in analysis.root_cause.lower() or "gate-skip" in analysis.root_cause.lower()


def test_analyze_losing_trade_flags_political_intel_on_polymarket():
  session = AsyncMock()
  session.execute = AsyncMock(
    side_effect=[
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ]
  )
  session.commit = AsyncMock()
  session.add = MagicMock()

  trade = _trade(
    bot_type="polymarket",
    symbol="FED-RATE-CUT",
    sentiment_score=-0.3,
    reason="Yes entry on macro market",
  )

  learner = LearningEngine(session)
  learner._get_market_context = AsyncMock(return_value="context")
  learner._had_source_intel = AsyncMock(
    side_effect=lambda symbol, at_time, source: source == "political"
  )
  learner._apply_adjustments = AsyncMock()
  learner.run_daily_review = AsyncMock(return_value=MagicMock())

  with patch("app.ws_manager.push_live_update", new_callable=AsyncMock):
    analysis = asyncio.run(learner.analyze_losing_trade(trade))

  assert "political" in analysis.root_cause.lower()
  assert "macro" in analysis.lessons_learned.lower()


def test_analyze_losing_trade_flags_political_intel_on_commodities():
  session = AsyncMock()
  session.execute = AsyncMock(
    side_effect=[
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ]
  )
  session.commit = AsyncMock()
  session.add = MagicMock()

  trade = _trade(
    bot_type="commodities",
    symbol="GC=F",
    sentiment_score=-0.25,
    reason="Stop hit on gold long",
  )

  learner = LearningEngine(session)
  learner._get_market_context = AsyncMock(return_value="context")
  learner._had_source_intel = AsyncMock(
    side_effect=lambda symbol, at_time, source: source == "political"
  )
  learner._apply_adjustments = AsyncMock()
  learner.run_daily_review = AsyncMock(return_value=MagicMock())

  with patch("app.ws_manager.push_live_update", new_callable=AsyncMock):
    analysis = asyncio.run(learner.analyze_losing_trade(trade))

  assert "political" in analysis.root_cause.lower()
  assert "geopolitical" in analysis.lessons_learned.lower()


def test_analyze_losing_trade_flags_political_intel_on_crypto():
  session = AsyncMock()
  session.execute = AsyncMock(
    side_effect=[
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ]
  )
  session.commit = AsyncMock()
  session.add = MagicMock()

  trade = _trade(
    bot_type="crypto",
    symbol="BTCUSDT",
    sentiment_score=-0.2,
    reason="Stop hit on BTC long",
  )

  learner = LearningEngine(session)
  learner._get_market_context = AsyncMock(return_value="context")
  learner._had_source_intel = AsyncMock(
    side_effect=lambda symbol, at_time, source: source == "political"
  )
  learner._apply_adjustments = AsyncMock()
  learner.run_daily_review = AsyncMock(return_value=MagicMock())

  with patch("app.ws_manager.push_live_update", new_callable=AsyncMock):
    analysis = asyncio.run(learner.analyze_losing_trade(trade))

  assert "political" in analysis.root_cause.lower()
  assert "geopolitical" in analysis.lessons_learned.lower()


def test_analyze_losing_trade_flags_tiktok_intel_on_crypto():
  session = AsyncMock()
  session.execute = AsyncMock(
    side_effect=[
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ]
  )
  session.commit = AsyncMock()
  session.add = MagicMock()

  trade = _trade(
    bot_type="crypto",
    symbol="PEPEUSDT",
    signal_score=0.42,
    sentiment_score=0.3,
    reason="Social momentum buy",
  )

  learner = LearningEngine(session)
  learner._get_market_context = AsyncMock(return_value="context")
  learner._had_source_intel = AsyncMock(
    side_effect=lambda symbol, at_time, source: source == "tiktok"
  )
  learner._apply_adjustments = AsyncMock()
  learner.run_daily_review = AsyncMock(return_value=MagicMock())

  with patch("app.ws_manager.push_live_update", new_callable=AsyncMock):
    analysis = asyncio.run(learner.analyze_losing_trade(trade))

  assert "tiktok" in analysis.root_cause.lower()
  assert "volume" in analysis.lessons_learned.lower()


def test_analyze_losing_trade_flags_reddit_intel_on_crypto():
  session = AsyncMock()
  session.execute = AsyncMock(
    side_effect=[
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ]
  )
  session.commit = AsyncMock()
  session.add = MagicMock()

  trade = _trade(
    bot_type="crypto",
    symbol="DOGEUSDT",
    signal_score=0.44,
    sentiment_score=0.28,
    reason="Retail buzz entry",
  )

  learner = LearningEngine(session)
  learner._get_market_context = AsyncMock(return_value="context")
  learner._had_source_intel = AsyncMock(
    side_effect=lambda symbol, at_time, source: source == "reddit"
  )
  learner._apply_adjustments = AsyncMock()
  learner.run_daily_review = AsyncMock(return_value=MagicMock())

  with patch("app.ws_manager.push_live_update", new_callable=AsyncMock):
    analysis = asyncio.run(learner.analyze_losing_trade(trade))

  assert "reddit" in analysis.root_cause.lower()
  assert "hype" in analysis.lessons_learned.lower() or "ta" in analysis.lessons_learned.lower()


def test_analyze_losing_trade_flags_tradingview_bearish_alert():
  session = AsyncMock()
  session.execute = AsyncMock(
    side_effect=[
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ]
  )
  session.commit = AsyncMock()
  session.add = MagicMock()

  trade = _trade(
    bot_type="stocks_futures",
    symbol="AAPL",
    sentiment_score=-0.3,
    reason="TradingView sell alert ignored",
  )

  learner = LearningEngine(session)
  learner._get_market_context = AsyncMock(return_value="context")
  learner._had_source_intel = AsyncMock(return_value=False)
  learner._apply_adjustments = AsyncMock()
  learner.run_daily_review = AsyncMock(return_value=MagicMock())

  with patch("app.ws_manager.push_live_update", new_callable=AsyncMock):
    analysis = asyncio.run(learner.analyze_losing_trade(trade))

  assert "tradingview" in analysis.root_cause.lower()
  assert "bearish" in analysis.root_cause.lower() or "exit" in analysis.lessons_learned.lower()


def test_analyze_losing_trade_flags_tradingview_weak_signal():
  session = AsyncMock()
  session.execute = AsyncMock(
    side_effect=[
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ]
  )
  session.commit = AsyncMock()
  session.add = MagicMock()

  trade = _trade(
    bot_type="commodities",
    symbol="GC=F",
    signal_score=0.41,
    sentiment_score=0.2,
    reason="Webhook buy on gold",
  )

  learner = LearningEngine(session)
  learner._get_market_context = AsyncMock(return_value="context")
  learner._had_source_intel = AsyncMock(
    side_effect=lambda symbol, at_time, source: source == "tradingview"
  )
  learner._apply_adjustments = AsyncMock()
  learner.run_daily_review = AsyncMock(return_value=MagicMock())

  with patch("app.ws_manager.push_live_update", new_callable=AsyncMock):
    analysis = asyncio.run(learner.analyze_losing_trade(trade))

  assert "tradingview" in analysis.root_cause.lower()
  assert "composite" in analysis.root_cause.lower() or "signal" in analysis.strategy_adjustment.lower()


def test_analyze_losing_trade_flags_youtube_intel_weak_signal():
  session = AsyncMock()
  session.execute = AsyncMock(
    side_effect=[
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ]
  )
  session.commit = AsyncMock()
  session.add = MagicMock()

  trade = _trade(
    bot_type="crypto",
    symbol="ETHUSDT",
    signal_score=0.38,
    reason="Breakout setup from study",
  )

  learner = LearningEngine(session)
  learner._get_market_context = AsyncMock(return_value="context")
  learner._had_source_intel = AsyncMock(
    side_effect=lambda symbol, at_time, source: source == "youtube"
  )
  learner._apply_adjustments = AsyncMock()
  learner.run_daily_review = AsyncMock(return_value=MagicMock())

  with patch("app.ws_manager.push_live_update", new_callable=AsyncMock):
    analysis = asyncio.run(learner.analyze_losing_trade(trade))

  assert "youtube" in analysis.root_cause.lower()
  assert "playbook" in analysis.lessons_learned.lower() or "study" in analysis.strategy_adjustment.lower()


def test_analyze_losing_trade_flags_tiktok_intel_on_stocks():
  session = AsyncMock()
  session.execute = AsyncMock(
    side_effect=[
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ]
  )
  session.commit = AsyncMock()
  session.add = MagicMock()

  trade = _trade(
    bot_type="stocks_futures",
    symbol="NVDA",
    signal_score=0.43,
    sentiment_score=0.3,
    reason="Viral momentum entry",
  )

  learner = LearningEngine(session)
  learner._get_market_context = AsyncMock(return_value="context")
  learner._had_source_intel = AsyncMock(
    side_effect=lambda symbol, at_time, source: source == "tiktok"
  )
  learner._apply_adjustments = AsyncMock()
  learner.run_daily_review = AsyncMock(return_value=MagicMock())

  with patch("app.ws_manager.push_live_update", new_callable=AsyncMock):
    analysis = asyncio.run(learner.analyze_losing_trade(trade))

  assert "tiktok" in analysis.root_cause.lower()
  assert "macd" in analysis.strategy_adjustment.lower() or "volume" in analysis.strategy_adjustment.lower()


def test_analyze_losing_trade_flags_x_bearish_intel():
  session = AsyncMock()
  session.execute = AsyncMock(
    side_effect=[
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ]
  )
  session.commit = AsyncMock()
  session.add = MagicMock()

  trade = _trade(
    bot_type="crypto",
    symbol="SOLUSDT",
    sentiment_score=-0.35,
    reason="Long on social buzz",
  )

  learner = LearningEngine(session)
  learner._get_market_context = AsyncMock(return_value="context")
  learner._had_source_intel = AsyncMock(
    side_effect=lambda symbol, at_time, source: source == "x"
  )
  learner._apply_adjustments = AsyncMock()
  learner.run_daily_review = AsyncMock(return_value=MagicMock())

  with patch("app.ws_manager.push_live_update", new_callable=AsyncMock):
    analysis = asyncio.run(learner.analyze_losing_trade(trade))

  assert "x/twitter" in analysis.root_cause.lower() or "twitter" in analysis.root_cause.lower()
  assert "bearish" in analysis.root_cause.lower() or "sentiment" in analysis.strategy_adjustment.lower()


def test_analyze_losing_trade_flags_polymarket_account_hook():
  session = AsyncMock()
  session.execute = AsyncMock(
    side_effect=[
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ]
  )
  session.commit = AsyncMock()
  session.add = MagicMock()

  trade = _trade(
    bot_type="polymarket",
    symbol="PM:fed-rate-cut",
    signal_score=0.41,
    sentiment_score=0.32,
    reason="Mirrored PM account Yes position",
  )

  learner = LearningEngine(session)
  learner._get_market_context = AsyncMock(return_value="context")
  learner._had_source_intel = AsyncMock(
    side_effect=lambda symbol, at_time, source: source == "polymarket_account"
  )
  learner._apply_adjustments = AsyncMock()
  learner.run_daily_review = AsyncMock(return_value=MagicMock())

  with patch("app.ws_manager.push_live_update", new_callable=AsyncMock):
    analysis = asyncio.run(learner.analyze_losing_trade(trade))

  assert "polymarket account" in analysis.root_cause.lower()
  assert "macro" in analysis.lessons_learned.lower() or "intel" in analysis.lessons_learned.lower()


def test_analyze_losing_trade_flags_newsapi_bearish_intel():
  session = AsyncMock()
  session.execute = AsyncMock(
    side_effect=[
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ]
  )
  session.commit = AsyncMock()
  session.add = MagicMock()

  trade = _trade(
    bot_type="stocks_futures",
    symbol="NVDA",
    sentiment_score=-0.28,
    signal_score=0.58,
    reason="Long on earnings momentum",
  )

  learner = LearningEngine(session)
  learner._get_market_context = AsyncMock(return_value="context")
  learner._had_source_intel = AsyncMock(
    side_effect=lambda symbol, at_time, source: source == "newsapi"
  )
  learner._apply_adjustments = AsyncMock()
  learner.run_daily_review = AsyncMock(return_value=MagicMock())

  with patch("app.ws_manager.push_live_update", new_callable=AsyncMock):
    analysis = asyncio.run(learner.analyze_losing_trade(trade))

  assert "news headline" in analysis.root_cause.lower()
  assert "bearish" in analysis.root_cause.lower() or "sentiment" in analysis.strategy_adjustment.lower()


def test_analyze_losing_trade_flags_newsapi_weak_signal():
  session = AsyncMock()
  session.execute = AsyncMock(
    side_effect=[
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ]
  )
  session.commit = AsyncMock()
  session.add = MagicMock()

  trade = _trade(
    bot_type="commodities",
    symbol="GC=F",
    signal_score=0.44,
    sentiment_score=0.2,
    reason="newsapi headline breakout",
  )

  learner = LearningEngine(session)
  learner._get_market_context = AsyncMock(return_value="context")
  learner._had_source_intel = AsyncMock(return_value=False)
  learner._apply_adjustments = AsyncMock()
  learner.run_daily_review = AsyncMock(return_value=MagicMock())

  with patch("app.ws_manager.push_live_update", new_callable=AsyncMock):
    analysis = asyncio.run(learner.analyze_losing_trade(trade))

  assert "news headline" in analysis.root_cause.lower()
  assert "technical" in analysis.root_cause.lower() or "confirmation" in analysis.lessons_learned.lower()


def test_analyze_losing_trade_flags_dexscreener_intel_on_crypto():
  session = AsyncMock()
  session.execute = AsyncMock(
    side_effect=[
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ]
  )
  session.commit = AsyncMock()
  session.add = MagicMock()

  trade = _trade(
    bot_type="crypto",
    symbol="WIFUSDT",
    signal_score=0.42,
    sentiment_score=0.2,
    reason="DexScreener boost entry",
  )

  learner = LearningEngine(session)
  learner._get_market_context = AsyncMock(return_value="context")
  learner._had_source_intel = AsyncMock(
    side_effect=lambda symbol, at_time, source: source == "dexscreener"
  )
  learner._apply_adjustments = AsyncMock()
  learner.run_daily_review = AsyncMock(return_value=MagicMock())

  with patch("app.ws_manager.push_live_update", new_callable=AsyncMock):
    analysis = asyncio.run(learner.analyze_losing_trade(trade))

  assert "dexscreener" in analysis.root_cause.lower()
  assert "volume" in analysis.strategy_adjustment.lower() or "liquidity" in analysis.strategy_adjustment.lower()


def test_analyze_losing_trade_flags_phantom_intel_on_crypto():
  session = AsyncMock()
  session.execute = AsyncMock(
    side_effect=[
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
      MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
      MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
    ]
  )
  session.commit = AsyncMock()
  session.add = MagicMock()

  trade = _trade(
    bot_type="crypto",
    symbol="SOLUSDT",
    signal_score=0.62,
    reason="Phantom portfolio mirror",
  )

  learner = LearningEngine(session)
  learner._get_market_context = AsyncMock(return_value="context")
  learner._had_source_intel = AsyncMock(
    side_effect=lambda symbol, at_time, source: source == "phantom"
  )
  learner._apply_adjustments = AsyncMock()
  learner.run_daily_review = AsyncMock(return_value=MagicMock())

  with patch("app.ws_manager.push_live_update", new_callable=AsyncMock):
    analysis = asyncio.run(learner.analyze_losing_trade(trade))

  assert "phantom" in analysis.root_cause.lower()
  assert "confirmation" in analysis.strategy_adjustment.lower() or "sentiment" in analysis.lessons_learned.lower()
