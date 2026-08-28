"""Tests for intelligence source weight adjustments."""

from unittest.mock import patch

from app.engines.intelligence_scoring import _proxy_source_multiplier


def test_proxy_multiplier_tiktok():
  assert _proxy_source_multiplier("tiktok") == 0.45


def test_proxy_multiplier_x_without_native_token():
  with patch("app.engines.intelligence_scoring.settings") as mock_settings:
    mock_settings.twitter_bearer_token = ""
    assert _proxy_source_multiplier("x") == 0.55


def test_proxy_multiplier_x_with_native_token():
  with patch("app.engines.intelligence_scoring.settings") as mock_settings:
    mock_settings.twitter_bearer_token = "token"
    assert _proxy_source_multiplier("x") == 1.0


def test_proxy_multiplier_news_unchanged():
  assert _proxy_source_multiplier("news") == 1.0
