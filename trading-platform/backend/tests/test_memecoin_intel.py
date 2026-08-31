"""Tests for memecoin intelligence scanners."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import asyncio

from app.intelligence.memecoin_scanner import (
  _map_dex_chain_symbol,
  _sanitize_dex_symbol,
  scan_hyperliquid_memecoins,
)
from app.intelligence.memecoin_whales import DEFAULT_ETH_WHALE_ADDRESSES, DEFAULT_SOLANA_WHALE_ADDRESSES


def test_default_whale_address_lists_nonempty():
  assert len(DEFAULT_ETH_WHALE_ADDRESSES) >= 10
  assert len(DEFAULT_SOLANA_WHALE_ADDRESSES) >= 3
  assert all(a.startswith("0x") for a in DEFAULT_ETH_WHALE_ADDRESSES)
  assert all(not a.startswith("0x") for a in DEFAULT_SOLANA_WHALE_ADDRESSES)


def test_map_dex_chain_symbol_wif():
  assert _map_dex_chain_symbol("solana", "mint", "dogwifhat trending") == "WIFUSDT"


def test_sanitize_dex_symbol_rejects_spam():
  assert _sanitize_dex_symbol("WIF") == "WIF"
  assert _sanitize_dex_symbol("BTC" * 50) is None
  assert _sanitize_dex_symbol("") is None


def test_scan_hyperliquid_memecoins_mock():
  session = AsyncMock()
  session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
  session.add = MagicMock()

  mock_response = MagicMock()
  mock_response.status_code = 200
  mock_response.json.return_value = [
    {"universe": [{"name": "WIF"}, {"name": "BTC"}]},
    [
      {"funding": "0.0001", "prevDayPx": "1.0", "markPx": "1.1", "openInterest": "100"},
      {"funding": "0", "prevDayPx": "50000", "markPx": "50100", "openInterest": "1000"},
    ],
  ]

  mock_post = AsyncMock(return_value=mock_response)
  mock_client = MagicMock()
  mock_client.__aenter__ = AsyncMock(return_value=mock_client)
  mock_client.__aexit__ = AsyncMock(return_value=None)
  mock_client.post = mock_post

  with patch("app.intelligence.memecoin_scanner.settings") as mock_settings:
    mock_settings.hyperliquid_enabled = True
    with patch("app.intelligence.memecoin_scanner.httpx.AsyncClient", return_value=mock_client):
      count = asyncio.run(scan_hyperliquid_memecoins(session))
  assert count >= 1
  session.add.assert_called()


def test_scan_hyperliquid_memecoins_refreshes_existing_item():
  existing = MagicMock()
  existing.url = "hyperliquid:perp:WIF"
  existing.fetched_at = datetime.utcnow() - timedelta(days=3)

  session = AsyncMock()
  session.execute = AsyncMock(
    return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=existing))
  )
  session.add = MagicMock()

  mock_response = MagicMock()
  mock_response.status_code = 200
  mock_response.json.return_value = [
    {"universe": [{"name": "WIF"}]},
    [{"funding": "0.0001", "prevDayPx": "1.0", "markPx": "1.2", "openInterest": "100"}],
  ]

  mock_post = AsyncMock(return_value=mock_response)
  mock_client = MagicMock()
  mock_client.__aenter__ = AsyncMock(return_value=mock_client)
  mock_client.__aexit__ = AsyncMock(return_value=None)
  mock_client.post = mock_post

  with patch("app.intelligence.memecoin_scanner.settings") as mock_settings:
    mock_settings.hyperliquid_enabled = True
    with patch("app.intelligence.memecoin_scanner.httpx.AsyncClient", return_value=mock_client):
      count = asyncio.run(scan_hyperliquid_memecoins(session))

  assert count == 1
  session.add.assert_not_called()
  assert existing.fetched_at > datetime.utcnow() - timedelta(minutes=1)
  assert "[Hyperliquid] WIF" in existing.title
