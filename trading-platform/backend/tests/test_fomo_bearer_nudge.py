"""Tests for fomo bearer pre-expiry nudge tiers."""

import asyncio
from unittest.mock import AsyncMock, patch

from app.engines.deploy_status import (
  fomo_bearer_nudge_message,
  resolve_fomo_bearer_nudge_tier,
)
from app.workers import scheduler


def test_resolve_fomo_bearer_nudge_tier_active():
  assert resolve_fomo_bearer_nudge_tier(polling_active=True, minutes_remaining=240) is None
  assert resolve_fomo_bearer_nudge_tier(polling_active=True, minutes_remaining=45) == "60"
  assert resolve_fomo_bearer_nudge_tier(polling_active=True, minutes_remaining=10) == "15"
  assert resolve_fomo_bearer_nudge_tier(polling_active=True, minutes_remaining=0) == "expired"
  assert resolve_fomo_bearer_nudge_tier(polling_active=False, minutes_remaining=120) == "expired"


def test_fomo_bearer_nudge_message():
  assert "expires in 42min" in fomo_bearer_nudge_message("60", minutes_remaining=42)
  assert "before deploy" in fomo_bearer_nudge_message("15", minutes_remaining=8)
  assert "expired" in fomo_bearer_nudge_message("expired")


def test_fomo_bearer_monitor_pushes_on_nudge_tier_change():
  async def run():
    scheduler._fomo_bearer_was_polling = True
    scheduler._fomo_bearer_last_nudge_tier = None
    with patch(
      "app.intelligence.fomo_tracker.get_fomo_bearer_status",
      new=AsyncMock(
        return_value={"configured": True, "polling_active": True, "minutes_remaining": 42}
      ),
    ):
      with patch("app.ws_manager.push_live_update", new=AsyncMock()) as push:
        await scheduler.fomo_bearer_monitor_job()
        push.assert_awaited_once()
    scheduler._fomo_bearer_was_polling = None
    scheduler._fomo_bearer_last_nudge_tier = None

  asyncio.run(run())
