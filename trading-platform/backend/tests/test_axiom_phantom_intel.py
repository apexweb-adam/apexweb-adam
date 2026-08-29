"""Tests for axiom.trade and Phantom wallet intel pipelines."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.intelligence.axiom_tracker import (
  axiom_configured,
  axiom_multi_wallet_ready,
  ingest_axiom_webhook,
  normalize_axiom_feed_response,
  wallet_track_relevance,
)
from app.intelligence.phantom_tracker import ingest_phantom_webhook, phantom_configured
from app.intelligence.content_study import _extract_live_intel_impact
from app.intelligence.memecoin_whales import DEFAULT_SOLANA_WHALE_ADDRESSES


def test_default_solana_whale_count_at_least_eight():
  assert len(DEFAULT_SOLANA_WHALE_ADDRESSES) >= 8


def test_axiom_configured_with_webhook_secret():
  with patch("app.intelligence.axiom_tracker.settings") as mock_settings:
    mock_settings.axiom_enabled = True
    mock_settings.axiom_session_token = ""
    mock_settings.tradingview_webhook_secret = "secret"
    assert axiom_configured() is True


def test_ingest_axiom_webhook_buy():
  session = AsyncMock()
  session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
  session.commit = AsyncMock()

  result = asyncio.run(
    ingest_axiom_webhook(
      session,
      {
        "symbol": "BONK",
        "action": "buy",
        "wallet_label": "smart_wallet",
        "wallet_address": "5tzFkiKscXHK5ZXCGbXZxdw7gTjjD1mBwuoFbhUvuAi9",
        "amount_usd": 5000,
        "wallets_watching": 8,
      },
    )
  )
  assert result["status"] == "received"
  assert result["source"] == "axiom"
  assert result["symbol"] == "BONKUSDT"


def test_ingest_phantom_webhook_portfolio():
  session = AsyncMock()
  session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
  session.commit = AsyncMock()

  result = asyncio.run(
    ingest_phantom_webhook(
      session,
      {
        "event_type": "portfolio",
        "symbol": "SOL",
        "wallet_address": "test_wallet_address_1234567890",
        "balance_usd": 12000,
      },
    )
  )
  assert result["status"] == "received"
  assert result["source"] == "phantom"


def test_extract_axiom_buy_impact():
  impact, confidence = _extract_live_intel_impact(
    "axiom",
    "[axiom] smart_wallet buy BONK",
    "multi-wallet watch",
    "BONKUSDT",
    0.6,
    0.85,
  )
  assert impact is not None
  assert "axiom" in impact.lower()
  assert "crypto bot" in impact.lower()
  assert confidence >= 0.7


def test_extract_phantom_accumulation_impact():
  impact, _ = _extract_live_intel_impact(
    "phantom",
    "[phantom] portfolio SOL",
    "wallet accumulation",
    "SOLUSDT",
    0.35,
    0.8,
  )
  assert impact is not None
  assert "phantom" in impact.lower()


def test_normalize_axiom_feed_response():
  payload = {"trades": [{"id": "1", "symbol": "WIF"}]}
  rows = normalize_axiom_feed_response(payload)
  assert len(rows) == 1
  assert rows[0]["symbol"] == "WIF"


def test_wallet_track_relevance_top_wallet():
  assert wallet_track_relevance("alpha_wallet", 3) >= 0.95


def test_axiom_multi_wallet_ready():
  with patch("app.intelligence.solana_wallet_tracker.tracked_solana_addresses", return_value=["a"] * 8):
    with patch("app.intelligence.axiom_tracker.settings") as mock_settings:
      mock_settings.wallet_tracker_min_wallets = 8
      assert axiom_multi_wallet_ready() is True


def test_phantom_configured_with_addresses():
  with patch("app.intelligence.phantom_tracker.settings") as mock_settings:
    mock_settings.phantom_enabled = True
    mock_settings.phantom_wallet_addresses = "wallet1,wallet2"
    mock_settings.tradingview_webhook_secret = ""
    assert phantom_configured() is True
