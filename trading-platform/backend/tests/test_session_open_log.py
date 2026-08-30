import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.engines.session_open_log import (
  SESSION_OPEN_EVENTS_KEY,
  get_session_open_events,
  record_session_open_event,
)
from app.models.entities import PlatformSetting


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
async def test_record_and_get_session_open_events(session: AsyncSession):
  await record_session_open_event(
    session,
    bot_type="commodities",
    event_type="burst_scan",
    symbols=[],
    symbol_count=12,
    detail="Session open burst scan — 12 symbols, no entry yet",
  )
  await record_session_open_event(
    session,
    bot_type="commodities",
    event_type="auto_entry",
    symbols=["NG=F"],
    symbol_count=12,
    detail="Session open auto-entry: NG=F",
  )
  events = await get_session_open_events(session)
  assert len(events) == 2
  assert events[0]["event_type"] == "auto_entry"
  assert events[0]["symbols"] == ["NG=F"]
  assert events[1]["event_type"] == "burst_scan"

  result = await session.execute(
    select(PlatformSetting).where(PlatformSetting.key == SESSION_OPEN_EVENTS_KEY)
  )
  row = result.scalar_one()
  stored = json.loads(row.value)
  assert isinstance(stored, list)
  assert stored[0]["bot_type"] == "commodities"
