import asyncio
from unittest.mock import AsyncMock, patch

from app.workers import scheduler


def test_fomo_bearer_monitor_pushes_on_expiry():
  async def run():
    scheduler._fomo_bearer_was_polling = True
    with patch(
      "app.intelligence.fomo_tracker.get_fomo_bearer_status",
      new=AsyncMock(return_value={"configured": True, "polling_active": False}),
    ):
      with patch(
        "app.ws_manager.push_live_update",
        new=AsyncMock(),
      ) as push:
        await scheduler.fomo_bearer_monitor_job()
        push.assert_awaited_once()
    scheduler._fomo_bearer_was_polling = None

  asyncio.run(run())


def test_fomo_bearer_monitor_skips_when_not_configured():
  async def run():
    scheduler._fomo_bearer_was_polling = None
    with patch(
      "app.intelligence.fomo_tracker.get_fomo_bearer_status",
      new=AsyncMock(return_value={"configured": False}),
    ):
      with patch(
        "app.ws_manager.push_live_update",
        new=AsyncMock(),
      ) as push:
        await scheduler.fomo_bearer_monitor_job()
        push.assert_not_awaited()

  asyncio.run(run())
