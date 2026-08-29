"""Tests for content study noise filtering."""

from app.intelligence.content_study import _is_trading_relevant_intel


def test_presidential_nomination_polymarket_is_noise():
  title = "Will Pete Hegseth win the 2028 Republican presidential nomination?"
  content = "Yes probability: 0.5%"
  assert _is_trading_relevant_intel(title, content, "polymarket") is False


def test_fed_rate_polymarket_is_relevant():
  title = "Fed rate hike in 2026?"
  content = "Yes probability: 66%"
  assert _is_trading_relevant_intel(title, content, "polymarket") is True


def test_dismiss_noise_band_covers_limbo_insights():
  from app.engines.learning_engine import LEARNING_NOISE_DISMISS_MAX_CONFIDENCE

  assert LEARNING_NOISE_DISMISS_MAX_CONFIDENCE > 0.52
  assert LEARNING_NOISE_DISMISS_MAX_CONFIDENCE < 0.55
