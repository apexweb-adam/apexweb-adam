"""Tests for CME deploy reminder scheduler job."""

import asyncio
import time
from unittest.mock import AsyncMock, patch

from app.engines.deploy_status import EXPECTED_PLATFORM_REVISION
from app.workers import scheduler as sched


def test_cme_deploy_reminder_logs_and_pushes_when_urgency_active():
  sched._cme_deploy_reminder_last_at = 0.0
  cme_session = {"in_session": False, "minutes_until_open": 120}

  with patch(
    "app.engines.gate_entry_guard.commodities_futures_weekend_closed",
    return_value=True,
  ):
    with patch(
      "app.engines.gate_entry_guard.commodities_session_info",
      return_value=cme_session,
    ):
      with patch.dict("os.environ", {"PLATFORM_REVISION": "2026-08-29-r336"}, clear=False):
        with patch(
          "app.ws_manager.push_live_update",
          new_callable=AsyncMock,
        ) as push:
          asyncio.run(sched.cme_deploy_reminder_job())

  push.assert_awaited_once()
  sched._cme_deploy_reminder_last_at = 0.0


def test_cme_deploy_reminder_skips_when_revision_current():
  sched._cme_deploy_reminder_last_at = 0.0
  cme_session = {"in_session": False, "minutes_until_open": 120}

  with patch(
    "app.engines.gate_entry_guard.commodities_futures_weekend_closed",
    return_value=True,
  ):
    with patch(
      "app.engines.gate_entry_guard.commodities_session_info",
      return_value=cme_session,
    ):
      with patch.dict(
        "os.environ",
        {"PLATFORM_REVISION": EXPECTED_PLATFORM_REVISION},
        clear=False,
      ):
        with patch(
          "app.ws_manager.push_live_update",
          new_callable=AsyncMock,
        ) as push:
          asyncio.run(sched.cme_deploy_reminder_job())

  push.assert_not_awaited()
  sched._cme_deploy_reminder_last_at = 0.0


def test_cme_deploy_reminder_rate_limited():
  sched._cme_deploy_reminder_last_at = time.monotonic()
  cme_session = {"in_session": False, "minutes_until_open": 90}

  with patch(
    "app.engines.gate_entry_guard.commodities_futures_weekend_closed",
    return_value=True,
  ):
    with patch(
      "app.engines.gate_entry_guard.commodities_session_info",
      return_value=cme_session,
    ):
      with patch.dict("os.environ", {"PLATFORM_REVISION": "2026-08-29-r336"}, clear=False):
        with patch(
          "app.ws_manager.push_live_update",
          new_callable=AsyncMock,
        ) as push:
          asyncio.run(sched.cme_deploy_reminder_job())

  push.assert_not_awaited()
  sched._cme_deploy_reminder_last_at = 0.0
