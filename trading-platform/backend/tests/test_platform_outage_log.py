import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.engines.platform_outage_log import (
  PLATFORM_LAST_ONLINE_KEY,
  PLATFORM_OUTAGE_EVENTS_KEY,
  detect_and_log_platform_outage,
  get_platform_outage_events,
  record_platform_online_heartbeat,
)
from app.engines.platform_settings import set_platform_setting
from app.engines.session_open_log import get_session_open_events


@pytest.fixture
async def session():
  engine = create_async_engine("sqlite+aiosqlite:///:memory:")
  async with engine.begin() as conn:
    await conn.run_sync(Base.metadata.create_all)
  factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
  async with factory() as db:
    yield db
  await engine.dispose()


@pytest.mark.asyncio
async def test_record_platform_online_heartbeat(session: AsyncSession):
  await record_platform_online_heartbeat(session)
  from app.engines.platform_settings import get_platform_setting

  raw = await get_platform_setting(session, PLATFORM_LAST_ONLINE_KEY)
  assert raw


@pytest.mark.asyncio
async def test_detect_and_log_platform_outage_on_gap(session: AsyncSession):
  last = (datetime.utcnow() - timedelta(minutes=95)).isoformat()
  await set_platform_setting(session, PLATFORM_LAST_ONLINE_KEY, last)
  await set_platform_setting(
    session,
    "prep_phase_state",
    json.dumps({"us_stocks_open": {"open_ready_symbols": ["AAPL"]}}),
  )

  event = await detect_and_log_platform_outage(session)
  assert event is not None
  assert event["gap_minutes"] >= 94
  assert event["us_open_ready_symbols"] == ["AAPL"]

  events = await get_platform_outage_events(session)
  assert len(events) == 1

  session_events = await get_session_open_events(session)
  assert any(e.get("event_type") == "platform_outage" for e in session_events)


@pytest.mark.asyncio
async def test_detect_skips_short_gap(session: AsyncSession):
  last = (datetime.utcnow() - timedelta(minutes=5)).isoformat()
  await set_platform_setting(session, PLATFORM_LAST_ONLINE_KEY, last)

  event = await detect_and_log_platform_outage(session)
  assert event is None
  assert await get_platform_outage_events(session) == []
