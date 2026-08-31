import asyncio
import json

import pytest
from unittest.mock import AsyncMock, patch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.engines.session_open_log import (
  SESSION_OPEN_EVENTS_KEY,
  get_session_open_events,
  needs_session_open_burst_recovery,
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
async def test_needs_session_open_burst_recovery_when_missing(session: AsyncSession):
  session_info = {
    "in_session": True,
    "minutes_since_open": 12,
    "session_open_utc": "2026-08-30T22:00:00",
  }
  assert await needs_session_open_burst_recovery(
    session,
    bot_type="commodities",
    session_info=session_info,
  )


@pytest.mark.asyncio
async def test_needs_session_open_burst_recovery_false_after_logged(session: AsyncSession):
  await record_session_open_event(
    session,
    bot_type="commodities",
    event_type="burst_scan",
    symbols=[],
    symbol_count=8,
    detail="Session open burst scan",
  )
  session_info = {
    "in_session": True,
    "minutes_since_open": 5,
    "session_open_utc": "2026-08-30T22:00:00",
  }
  assert not await needs_session_open_burst_recovery(
    session,
    bot_type="commodities",
    session_info=session_info,
  )


@pytest.mark.asyncio
async def test_needs_session_open_burst_recovery_false_outside_grace(session: AsyncSession):
  session_info = {
    "in_session": True,
    "minutes_since_open": 75,
    "session_open_utc": "2026-08-30T22:00:00",
  }
  assert not await needs_session_open_burst_recovery(
    session,
    bot_type="commodities",
    session_info=session_info,
  )


@pytest.mark.asyncio
async def test_needs_session_open_burst_recovery_platform_outage_with_queued(session: AsyncSession):
  from app.engines.platform_settings import set_platform_setting
  from app.engines.session_open_log import PREP_PHASE_STATE_KEY

  await set_platform_setting(
    session,
    PREP_PHASE_STATE_KEY,
    json.dumps(
      {
        "us_stocks_open": {
          "open_ready_symbols": ["AAPL"],
          "near_floor_symbols": [],
        },
      }
    ),
  )
  session_info = {
    "in_session": True,
    "minutes_since_open": 90,
    "session_open_utc": "2026-08-31T13:30:00",
  }
  assert await needs_session_open_burst_recovery(
    session,
    bot_type="stocks_futures",
    session_info=session_info,
  )


@pytest.mark.asyncio
async def test_platform_outage_burst_recovery_active(session: AsyncSession):
  from app.engines.platform_settings import set_platform_setting
  from app.engines.session_open_log import (
    PREP_PHASE_STATE_KEY,
    platform_outage_burst_recovery_active,
  )

  await set_platform_setting(
    session,
    PREP_PHASE_STATE_KEY,
    json.dumps({"us_stocks_open": {"open_ready_symbols": ["AAPL"]}}),
  )
  session_info = {
    "in_session": True,
    "minutes_since_open": 90,
    "session_open_utc": "2026-08-31T13:30:00",
  }
  assert await platform_outage_burst_recovery_active(
    session,
    bot_type="stocks_futures",
    session_info=session_info,
  )
  session_info["minutes_since_open"] = 30
  assert not await platform_outage_burst_recovery_active(
    session,
    bot_type="stocks_futures",
    session_info=session_info,
  )


@pytest.mark.asyncio
async def test_needs_session_open_burst_recovery_platform_outage_no_queue(session: AsyncSession):
  session_info = {
    "in_session": True,
    "minutes_since_open": 90,
    "session_open_utc": "2026-08-31T13:30:00",
  }
  assert not await needs_session_open_burst_recovery(
    session,
    bot_type="stocks_futures",
    session_info=session_info,
  )


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


def test_queue_delta():
  from app.engines.session_open_log import _queue_delta

  added, removed = _queue_delta(["NG=F"], ["NG=F", "CL=F"])
  assert added == ["CL=F"]
  assert removed == []
  added, removed = _queue_delta(["NG=F", "CL=F"], ["NG=F"])
  assert added == []
  assert removed == ["CL=F"]


def test_format_queue_symbols_includes_composite():
  from app.engines.session_open_log import _format_queue_symbols

  event = {
    "open_ready_details": [
      {"symbol": "NG=F", "composite": 0.624},
      {"symbol": "AAPL", "composite": 0.498},
    ]
  }
  assert _format_queue_symbols(event, ["NG=F", "AAPL"]) == "NG=F (0.624), AAPL (0.498)"
  assert _format_queue_symbols(event, ["CL=F"]) == "CL=F"


def test_monitor_open_ready_queue_logs_initial_baseline():
  async def run():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
      await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
      from app.engines.session_open_log import monitor_open_ready_queue

      with patch(
        "app.engines.scan_preview.build_monday_recovery_summary",
        new=AsyncMock(
          return_value={
            "stocks_trade_count_nudge": True,
            "commodities_graduation_nudge": True,
            "open_ready": [
              {
                "bot_type": "commodities",
                "symbol": "NG=F",
                "composite": 0.55,
                "monday_gate_skip_ready": True,
              },
              {
                "bot_type": "stocks_futures",
                "symbol": "AAPL",
                "composite": 0.47,
                "monday_gate_skip_ready": True,
              },
            ],
            "near_floor": [],
          }
        ),
      ):
        logged = await monitor_open_ready_queue(session)

      assert len(logged) == 2
      assert logged[0]["event_type"] == "queue_add"
      assert logged[0]["symbols"] == ["NG=F"]
      assert logged[1]["symbols"] == ["AAPL"]

      events = await get_session_open_events(session)
      assert any(e["symbols"] == ["NG=F"] for e in events)
      assert any(e["symbols"] == ["AAPL"] for e in events)
    await engine.dispose()

  asyncio.run(run())


def test_backfill_open_ready_queue_events_logs_missing_symbols():
  async def run():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
      await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
      await record_session_open_event(
        session,
        bot_type="commodities",
        event_type="queue_remove",
        symbols=["CL=F"],
        detail="cme_reopen: removed from queue — CL=F",
      )
      from app.engines.session_open_log import backfill_open_ready_queue_events

      with patch(
        "app.engines.scan_preview.build_monday_recovery_summary",
        new=AsyncMock(
          return_value={
            "stocks_trade_count_nudge": True,
            "commodities_graduation_nudge": True,
            "open_ready": [
              {
                "bot_type": "commodities",
                "symbol": "NG=F",
                "composite": 0.62,
                "monday_gate_skip_ready": True,
              },
              {
                "bot_type": "stocks_futures",
                "symbol": "AAPL",
                "composite": 0.49,
                "monday_gate_skip_ready": True,
              },
            ],
            "near_floor": [],
          }
        ),
      ):
        logged = await backfill_open_ready_queue_events(session)

      assert len(logged) == 2
      symbols = {tuple(entry["symbols"]) for entry in logged}
      assert ("NG=F",) in symbols
      assert ("AAPL",) in symbols
    await engine.dispose()

  asyncio.run(run())


def test_monitor_open_ready_queue_logs_remove_with_last_composite():
  async def run():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
      await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
      from app.engines.platform_settings import set_platform_setting
      from app.engines.session_open_log import PREP_PHASE_STATE_KEY, monitor_open_ready_queue

      await set_platform_setting(
        session,
        PREP_PHASE_STATE_KEY,
        json.dumps(
          {
            "cme_reopen": {
              "open_ready_symbols": ["NG=F", "CL=F"],
              "near_floor_symbols": [],
              "open_ready_composites": {"NG=F": 0.62, "CL=F": 0.41},
            },
            "us_stocks_open": {
              "open_ready_symbols": ["AAPL"],
              "near_floor_symbols": [],
            },
          }
        ),
      )

      with patch(
        "app.engines.scan_preview.build_monday_recovery_summary",
        new=AsyncMock(
          return_value={
            "stocks_trade_count_nudge": True,
            "commodities_graduation_nudge": True,
            "open_ready": [
              {
                "bot_type": "commodities",
                "symbol": "NG=F",
                "composite": 0.62,
                "monday_gate_skip_ready": True,
              },
              {
                "bot_type": "stocks_futures",
                "symbol": "AAPL",
                "composite": 0.49,
                "monday_gate_skip_ready": True,
              },
            ],
            "near_floor": [],
          }
        ),
      ):
        logged = await monitor_open_ready_queue(session)

      remove = next(entry for entry in logged if entry["event_type"] == "queue_remove")
      assert remove["symbols"] == ["CL=F"]
      assert "CL=F (last 0.410)" in (remove.get("detail") or "")
    await engine.dispose()

  asyncio.run(run())


def test_monitor_open_ready_queue_persists_extended_watch_after_remove():
  async def run():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
      await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
      from app.engines.platform_settings import set_platform_setting
      from app.engines.session_open_log import (
        PREP_PHASE_STATE_KEY,
        get_prep_phase_state,
        monitor_open_ready_queue,
      )

      await set_platform_setting(
        session,
        SESSION_OPEN_EVENTS_KEY,
        json.dumps(
          [
            {
              "timestamp": "2026-08-30T15:55:49.081957",
              "bot_type": "commodities",
              "event_type": "queue_add",
              "symbols": ["NG=F"],
              "detail": "cme_reopen: auto-entry queued — NG=F (0.448)",
            },
          ]
        ),
      )
      await set_platform_setting(
        session,
        PREP_PHASE_STATE_KEY,
        json.dumps(
          {
            "cme_reopen": {
              "open_ready_symbols": [],
              "near_floor_symbols": ["NG=F"],
              "open_ready_composites": {"NG=F": 0.397},
            },
          }
        ),
      )

      with patch(
        "app.engines.scan_preview.build_monday_recovery_summary",
        new=AsyncMock(
          return_value={
            "stocks_trade_count_nudge": False,
            "commodities_graduation_nudge": True,
            "open_ready": [],
            "near_floor": [
              {"bot_type": "commodities", "symbol": "NG=F", "composite": 0.397},
            ],
          }
        ),
      ):
        await monitor_open_ready_queue(session)

      state = await get_prep_phase_state(session)
      assert state["cme_reopen"]["extended_watch_symbols"] == ["NG=F"]
    await engine.dispose()

  asyncio.run(run())

