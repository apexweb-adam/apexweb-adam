import asyncio
from unittest.mock import AsyncMock, patch

from app.workers.scheduler import session_prep_queue_monitor_job


def test_session_prep_queue_monitor_runs_during_us_stocks_prep():
  async def run():
    with patch(
      "app.engines.gate_entry_guard.status_cache_prewarm_active",
      return_value=True,
    ):
      with patch("app.workers.scheduler.SessionLocal") as session_local:
        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        session_local.return_value = session
        with patch(
          "app.engines.session_open_log.monitor_open_ready_queue",
          new=AsyncMock(return_value=[]),
        ) as monitor:
          with patch(
            "app.engines.session_open_log.backfill_open_ready_queue_events",
            new=AsyncMock(return_value=[]),
          ):
            await session_prep_queue_monitor_job()
            monitor.assert_awaited_once_with(session)

  asyncio.run(run())


def test_session_prep_queue_monitor_skips_outside_prep_windows():
  async def run():
    with patch(
      "app.engines.gate_entry_guard.status_cache_prewarm_active",
      return_value=False,
    ):
      with patch(
        "app.engines.session_open_log.monitor_open_ready_queue",
        new=AsyncMock(),
      ) as monitor:
        await session_prep_queue_monitor_job()
        monitor.assert_not_awaited()

  asyncio.run(run())
