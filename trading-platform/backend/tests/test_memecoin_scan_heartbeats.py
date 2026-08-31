"""Memecoin scanner records dexscreener/hyperliquid scan heartbeats."""

import asyncio
from unittest.mock import AsyncMock, patch

from app.intelligence.extended_scanners import ExtendedIntelligenceScanner
from app.intelligence.scanner import IntelligenceScanner


def test_scan_all_records_memecoin_heartbeats():
  session = AsyncMock()
  scanner = ExtendedIntelligenceScanner(session)
  heartbeat_mock = AsyncMock()

  with patch("app.intelligence.extended_scanners.settings") as mock_settings, patch.object(
    IntelligenceScanner, "scan_all", AsyncMock(return_value=0)
  ), patch.object(scanner, "_scan_youtube", AsyncMock(return_value=0)), patch.object(
    scanner, "_scan_polymarket", AsyncMock(return_value=0)
  ), patch.object(scanner, "_scan_political", AsyncMock(return_value=0)), patch.object(
    scanner, "_scan_tiktok_news", AsyncMock(return_value=0)
  ), patch.object(scanner, "_scan_x_google_news_fallback", AsyncMock(return_value=0)), patch(
    "app.intelligence.wallet_tracker.scan_wallet_tracker", AsyncMock(return_value=0)
  ), patch(
    "app.intelligence.solana_wallet_tracker.scan_solana_wallets", AsyncMock(return_value=0)
  ), patch(
    "app.intelligence.memecoin_scanner.scan_memecoin_intel", AsyncMock(return_value=3)
  ), patch(
    "app.intelligence.fomo_tracker.scan_fomo_trades", AsyncMock(return_value=0)
  ), patch(
    "app.intelligence.axiom_tracker.scan_axiom_feed", AsyncMock(return_value=0)
  ), patch(
    "app.intelligence.phantom_tracker.scan_phantom_portfolios", AsyncMock(return_value=0)
  ), patch(
    "app.intelligence.scan_heartbeats.record_intel_scan_heartbeats", heartbeat_mock
  ):
    mock_settings.twitter_bearer_token = ""
    mock_settings.newsapi_key = ""
    mock_settings.polymarket_wallet_address = ""
    mock_settings.polymarket_deposit_address = ""
    mock_settings.hyperliquid_enabled = True

    asyncio.run(scanner.scan_all())

  recorded_sources = [call.args[-1] for call in heartbeat_mock.await_args_list if len(call.args) >= 2]
  assert "dexscreener" in recorded_sources
  assert "hyperliquid" in recorded_sources
