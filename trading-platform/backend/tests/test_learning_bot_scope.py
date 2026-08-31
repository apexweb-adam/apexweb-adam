"""Tests for bot-scoped insight application."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.engines.learning_engine import LearningEngine, _target_bot_types_from_impact


def test_target_bot_types_from_fomo_impact():
  targets = _target_bot_types_from_impact(
    "fomo.family leaderboard buy — crypto bot: require TA confirmation"
  )
  assert targets == {"crypto"}


def test_target_bot_types_from_gold_impact():
  targets = _target_bot_types_from_impact(
    "Weight geopolitical news higher for commodities bot"
  )
  assert targets == {"commodities"}


def test_target_bot_types_from_political_impact():
  targets = _target_bot_types_from_impact(
    "Political intel (tariff): favor cautious bias on GC=F — "
    "target bots: commodities, stocks_futures; weight geopolitical news"
  )
  assert targets == {"commodities", "stocks_futures"}


def test_target_bot_types_from_political_election_impact():
  targets = _target_bot_types_from_impact(
    "Political intel (election): favor long bias on POLITICAL — "
    "target bots: polymarket, stocks_futures"
  )
  assert targets == {"polymarket", "stocks_futures"}


def test_target_bot_types_generic_returns_none():
  targets = _target_bot_types_from_impact("Tighten stop-loss to 1.5-2% max")
  assert targets is None


def test_apply_insight_only_touches_crypto_config():
  crypto_cfg = MagicMock()
  crypto_cfg.bot_type = "crypto"
  crypto_cfg.rsi_oversold = 30
  crypto_cfg.stop_loss_pct = 0.02
  crypto_cfg.sentiment_weight = 0.2
  crypto_cfg.max_position_pct = 0.1
  crypto_cfg.version = 1

  stocks_cfg = MagicMock()
  stocks_cfg.bot_type = "stocks_futures"
  stocks_cfg.rsi_oversold = 30
  stocks_cfg.stop_loss_pct = 0.02
  stocks_cfg.sentiment_weight = 0.2
  stocks_cfg.max_position_pct = 0.1
  stocks_cfg.version = 1

  session = AsyncMock()
  session.execute = AsyncMock(
    return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[crypto_cfg, stocks_cfg]))))
  )

  learner = LearningEngine(session)
  impact = "DexScreener trending WIF — crypto bot: increase sentiment weight and tighten stop-loss"

  asyncio.run(learner._apply_insight_to_strategies(impact))

  assert crypto_cfg.sentiment_weight > 0.2
  assert stocks_cfg.sentiment_weight == 0.2
