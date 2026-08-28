"""Tests for on-chain wallet tracker and webhook ingest."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.intelligence.wallet_tracker import (
  _transfer_sentiment,
  ingest_wallet_webhook,
  parse_wallet_addresses,
)


def test_parse_wallet_addresses():
  raw = "0xABC123, 0xdef456, not-an-address"
  assert parse_wallet_addresses(raw) == ["0xabc123", "0xdef456"]


def test_tracked_wallet_addresses_custom_overrides_defaults():
  from app.intelligence.wallet_tracker import tracked_wallet_addresses

  with patch("app.intelligence.wallet_tracker.settings") as mock_settings:
    mock_settings.wallet_tracker_addresses = "0xCustom123"
    mock_settings.wallet_tracker_use_defaults = True
    assert tracked_wallet_addresses() == ["0xcustom123"]


def test_tracked_wallet_addresses_defaults_when_enabled():
  from app.intelligence.memecoin_whales import DEFAULT_ETH_WHALE_ADDRESSES
  from app.intelligence.wallet_tracker import tracked_wallet_addresses

  with patch("app.intelligence.wallet_tracker.settings") as mock_settings:
    mock_settings.wallet_tracker_addresses = ""
    mock_settings.wallet_tracker_use_defaults = True
    assert tracked_wallet_addresses() == [a.lower() for a in DEFAULT_ETH_WHALE_ADDRESSES]


def test_wallet_tracker_configured():
  from app.intelligence.wallet_tracker import wallet_tracker_configured

  with patch("app.intelligence.wallet_tracker.settings") as mock_settings, patch(
    "app.intelligence.solana_wallet_tracker.tracked_solana_addresses",
    return_value=[],
  ):
    mock_settings.wallet_tracker_addresses = ""
    mock_settings.wallet_tracker_use_defaults = True
    mock_settings.helius_api_key = ""
    assert wallet_tracker_configured() is True
    mock_settings.wallet_tracker_use_defaults = False
    assert wallet_tracker_configured() is False


def test_transfer_sentiment_accumulation():
  watched = "0xwhale"
  assert _transfer_sentiment(
    watched=watched,
    from_addr="0xother",
    to_addr=watched,
    usd_estimate=50_000,
  ) > 0


def test_transfer_sentiment_distribution():
  watched = "0xwhale"
  assert _transfer_sentiment(
    watched=watched,
    from_addr=watched,
    to_addr="0xbinance",
    usd_estimate=50_000,
  ) < 0


def test_ingest_wallet_webhook_buy():
  session = AsyncMock()
  session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
  session.add = MagicMock()
  session.commit = AsyncMock()

  result = asyncio.run(
    ingest_wallet_webhook(
      session,
      {
        "symbol": "BTCUSDT",
        "action": "buy",
        "amount_usd": 100000,
        "address": "0xwhale",
        "tx_hash": "0xtesthash123",
      },
    )
  )
  assert result["status"] == "received"
  assert result["symbol"] == "BTCUSDT"
  session.add.assert_called_once()


def test_ingest_wallet_webhook_duplicate():
  session = AsyncMock()
  session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=object())))

  result = asyncio.run(
    ingest_wallet_webhook(
      session,
      {"symbol": "ETH", "action": "sell", "tx_hash": "0xdup"},
    )
  )
  assert result["status"] == "duplicate"
