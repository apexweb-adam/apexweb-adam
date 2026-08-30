"""Tests for CME deploy reminder scheduler job."""

import asyncio
import time
from unittest.mock import AsyncMock, patch

from app.workers import scheduler as sched

_URGENCY = {
  "active": True,
  "minutes_until_open": 120,
  "message": "CME reopen in 2h 0m — deploy before open",
  "deploy_command": "TRIGGER_DEPLOY=true bash trading-platform/scripts/sync-render-env.sh",
}


def test_cme_deploy_reminder_logs_and_pushes_when_urgency_active():
  sched._cme_deploy_reminder_last_at = 0.0

  with patch.object(sched, "_resolve_cme_deploy_reminder", return_value=_URGENCY):
    with patch.object(
      sched,
      "_push_cme_deploy_live_update",
      new_callable=AsyncMock,
    ) as push:
      asyncio.run(sched.cme_deploy_reminder_job())

  push.assert_awaited_once()
  sched._cme_deploy_reminder_last_at = 0.0


def test_cme_deploy_reminder_skips_when_no_urgency():
  sched._cme_deploy_reminder_last_at = 0.0

  with patch.object(sched, "_resolve_cme_deploy_reminder", return_value=None):
    with patch.object(
      sched,
      "_push_cme_deploy_live_update",
      new_callable=AsyncMock,
    ) as push:
      asyncio.run(sched.cme_deploy_reminder_job())

  push.assert_not_awaited()
  sched._cme_deploy_reminder_last_at = 0.0


def test_cme_deploy_reminder_rate_limited():
  sched._cme_deploy_reminder_last_at = time.monotonic()

  with patch.object(sched, "_resolve_cme_deploy_reminder", return_value=_URGENCY):
    with patch.object(
      sched,
      "_push_cme_deploy_live_update",
      new_callable=AsyncMock,
    ) as push:
      asyncio.run(sched.cme_deploy_reminder_job())

  push.assert_not_awaited()
  sched._cme_deploy_reminder_last_at = 0.0
