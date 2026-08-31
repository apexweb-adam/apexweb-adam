"""Tests for platform status integration payloads."""

from unittest.mock import patch

from app.engines.platform_status import _build_integrations_payload


def test_build_integrations_payload_includes_polymarket_fields():
  with patch("app.engines.platform_status.settings") as mock_settings:
    mock_settings.tradingview_webhook_secret = ""
    mock_settings.polymarket_wallet_address = "0xabc"
    mock_settings.polymarket_deposit_address = ""
    mock_settings.polymarket_api_key = ""
    mock_settings.polymarket_profile_url = "https://polymarket.com/@apexweb"
    mock_settings.fomo_enabled = False
    mock_settings.hyperliquid_enabled = True
    mock_settings.reddit_client_id = ""
    mock_settings.reddit_client_secret = ""
    mock_settings.newsapi_key = ""
    mock_settings.twitter_bearer_token = ""

    payload = _build_integrations_payload({}, {}, 0, pm_intel_items=42, pm_account_items=3)

  assert payload["polymarket_market_scanner"] is True
  assert payload["polymarket_account_hook"] is True
  assert payload["polymarket_api_key"] is False
  assert payload["polymarket_intel_items"] == 42
  assert payload["polymarket_account_items"] == 3
  assert payload["polymarket_profile_url"] == "https://polymarket.com/@apexweb"
  assert payload["polymarket_setup"] is not None
  assert "POLYMARKET_API_KEY" in payload["polymarket_setup"]


def test_build_integrations_payload_polymarket_setup_when_unconfigured():
  with patch("app.engines.platform_status.settings") as mock_settings:
    mock_settings.tradingview_webhook_secret = ""
    mock_settings.polymarket_wallet_address = ""
    mock_settings.polymarket_deposit_address = ""
    mock_settings.polymarket_api_key = ""
    mock_settings.polymarket_profile_url = ""
    mock_settings.fomo_enabled = False
    mock_settings.hyperliquid_enabled = False
    mock_settings.reddit_client_id = ""
    mock_settings.reddit_client_secret = ""
    mock_settings.newsapi_key = ""
    mock_settings.twitter_bearer_token = ""

    payload = _build_integrations_payload({}, {}, 0)

  assert payload["polymarket_account_hook"] is False
  assert payload["polymarket_api_key"] is False
  assert "POLYMARKET_API_KEY" in (payload["polymarket_setup"] or "")
  assert "POLYMARKET_WALLET_ADDRESS" in (payload["polymarket_setup"] or "")
