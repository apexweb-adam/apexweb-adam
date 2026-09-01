"""Tests for political intel ingestion in extended scanners."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.intelligence.extended_scanners import ExtendedIntelligenceScanner


def test_add_political_item_classifies_tariff_and_persists():
  session = AsyncMock()
  session.execute = AsyncMock(
    return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
  )
  session.add = MagicMock()

  scanner = ExtendedIntelligenceScanner(session)
  added = asyncio.run(
    scanner._add_political_item(
      "US announces new tariff on steel imports",
      "trade war escalation raises commodity risk",
      "https://news.example/tariff-1",
    )
  )

  assert added is True
  session.add.assert_called_once()
  item = session.add.call_args[0][0]
  assert item.source == "political"
  assert item.category == "political:tariff"
  assert "commodities" in item.content
  assert "GC" in (item.symbols_mentioned or "")


def test_add_political_item_skips_duplicate_url():
  session = AsyncMock()
  session.execute = AsyncMock(
    return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=object()))
  )

  scanner = ExtendedIntelligenceScanner(session)
  added = asyncio.run(
    scanner._add_political_item(
      "Duplicate headline",
      "body",
      "https://news.example/dup",
    )
  )

  assert added is False
  session.add.assert_not_called()
