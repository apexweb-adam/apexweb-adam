"""Tests for intel scan heartbeat tracking."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from app.intelligence.scan_heartbeats import (
  INTEL_SCAN_HEARTBEATS_KEY,
  get_intel_scan_heartbeats,
  record_intel_scan_heartbeats,
)


def test_record_and_read_intel_scan_heartbeats():
  async def run():
    row = MagicMock()
    row.value = None
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=row)))

    await record_intel_scan_heartbeats(session, "youtube", "x")
    assert row.value is not None
    assert "youtube" in row.value
    assert "x" in row.value

    row.value = row.value
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=row)))
    heartbeats = await get_intel_scan_heartbeats(session)
    assert "youtube" in heartbeats
    assert "x" in heartbeats
    assert datetime.utcnow() - heartbeats["youtube"] < timedelta(minutes=1)

  asyncio.run(run())


def test_get_intel_scan_heartbeats_empty_when_missing():
  async def run():
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
    heartbeats = await get_intel_scan_heartbeats(session)
    assert heartbeats == {}

  asyncio.run(run())
