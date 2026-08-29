"""Tests for fomo.family social copy-trading intel."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.engines.integration_signals import get_integration_boost
from app.intelligence.fomo_tracker import (
  ingest_fomo_webhook,
  normalize_fomo_symbol,
  trader_relevance,
)
from app.models.entities import IntelligenceItem


def test_normalize_fomo_symbol_memecoins():
  assert normalize_fomo_symbol("wif") == "WIFUSDT"
  assert normalize_fomo_symbol("BONK") == "BONKUSDT"
  assert normalize_fomo_symbol("PEPEUSDT") == "PEPEUSDT"


def test_trader_relevance_top_rank():
  assert trader_relevance(3) >= 0.94
  assert trader_relevance(25) >= 0.85
  assert trader_relevance(500) < 0.85


def test_ingest_fomo_webhook_buy():
  session = AsyncMock()
  session.execute = AsyncMock(
    return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
  )
  session.commit = AsyncMock()

  result = asyncio.run(
    ingest_fomo_webhook(
      session,
      {
        "symbol": "WIF",
        "action": "buy",
        "trader_name": "legend",
        "trader_rank": 2,
        "trader_pnl_pct": 150,
        "chain": "solana",
        "amount_usd": 3000,
      },
    )
  )
  assert result["status"] == "received"
  assert result["symbol"] == "WIFUSDT"
  assert result["source"] == "fomo"
  assert result["relevance"] >= 0.9
  session.add.assert_called_once()
  item = session.add.call_args[0][0]
  assert item.source == "fomo"
  assert item.sentiment > 0.5


def test_fomo_leader_confluence_boost():
  session = AsyncMock()
  items = [
    IntelligenceItem(
      source="fomo",
      category="crypto",
      title="fomo buy",
      content="WIFUSDT",
      url="fomo:1",
      sentiment=0.6,
      relevance_score=0.92,
      symbols_mentioned="WIFUSDT",
      fetched_at=datetime.utcnow(),
    ),
    IntelligenceItem(
      source="dexscreener",
      category="crypto",
      title="dex pump",
      content="WIFUSDT",
      url="dex:1",
      sentiment=0.45,
      relevance_score=0.8,
      symbols_mentioned="WIFUSDT",
      fetched_at=datetime.utcnow(),
    ),
  ]
  session.execute = AsyncMock(
    return_value=MagicMock(
      scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=items)))
    )
  )

  boost, reason = asyncio.run(get_integration_boost(session, "WIFUSDT"))
  assert boost > 0.08
  assert "fomo_leader_confluence" in reason


def test_get_fomo_hot_symbols():
  from app.intelligence.fomo_tracker import get_fomo_hot_symbols

  session = AsyncMock()
  item = IntelligenceItem(
    source="fomo",
    category="crypto",
    title="hot",
    content="NEWCOIN",
    url="fomo:hot",
    sentiment=0.55,
    relevance_score=0.9,
    symbols_mentioned="NEWCOIN",
    fetched_at=datetime.utcnow(),
  )
  session.execute = AsyncMock(
    return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[item]))))
  )

  with patch("app.intelligence.fomo_tracker.settings") as mock_settings:
    mock_settings.fomo_hot_symbols_enabled = True
    mock_settings.crypto_symbols = "BTCUSDT,ETHUSDT"
    mock_settings.fomo_hot_symbol_min_relevance = 0.8
    mock_settings.fomo_hot_symbols_max = 8
    hot = asyncio.run(get_fomo_hot_symbols(session))

  assert hot == ["NEWCOINUSDT"]


def test_trade_row_to_payload_maps_fomo_trade():
  from app.intelligence.fomo_tracker import trade_row_to_payload

  payload = trade_row_to_payload(
    {
      "id": "trade-123",
      "side": "buy",
      "totalUsd": 4200,
      "networkId": 1399811149,
      "token": {"symbol": "WIF", "address": "So111"},
      "user": {"id": "u1", "handle": "legend", "rank": 4, "pnlPct": 180},
    }
  )
  assert payload["symbol"] == "WIF"
  assert payload["action"] == "buy"
  assert payload["trader_name"] == "legend"
  assert payload["trader_rank"] == 4
  assert payload["chain"] == "solana"
  assert payload["url"] == "fomo:trade:trade-123"
  assert payload["relevance"] >= 0.9
