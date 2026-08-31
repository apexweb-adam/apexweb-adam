import asyncio
from unittest.mock import AsyncMock, patch

from app.engines.gate_entry_guard import STATUS_CACHE_WATCH_TTL_SECONDS
from app.workers import scheduler as scheduler_mod
from app.workers.scheduler import warm_status_caches_job


def test_refresh_status_caches_scheduler_interval_matches_watch_ttl():
  source = open(scheduler_mod.__file__).read()
  assert "seconds=STATUS_CACHE_WATCH_TTL_SECONDS" in source
  assert STATUS_CACHE_WATCH_TTL_SECONDS == 15


def test_warm_status_caches_job_builds_both_payloads():
  async def run():
    with patch(
      "app.workers.scheduler.SessionLocal",
    ) as session_local:
      session = AsyncMock()
      session.__aenter__ = AsyncMock(return_value=session)
      session.__aexit__ = AsyncMock(return_value=None)
      session_local.return_value = session
      with patch(
        "app.engines.platform_status.build_platform_status",
        new=AsyncMock(return_value={"platform": "ok"}),
      ) as platform_builder:
        with patch(
          "app.engines.gate_prep_status.build_gate_prep_status",
          new=AsyncMock(return_value={"commodities": {}}),
        ) as prep_builder:
          await warm_status_caches_job()
          platform_builder.assert_awaited_once_with(session)
          prep_builder.assert_awaited_once_with(session)

  asyncio.run(run())


def test_refresh_status_caches_job_skips_when_fresh():
  async def run():
    with patch(
      "app.engines.gate_entry_guard.status_cache_prewarm_active",
      return_value=True,
    ):
      with patch(
        "app.engines.platform_status.platform_status_cache_fresh",
        return_value=True,
      ):
        with patch(
          "app.engines.gate_prep_status.gate_prep_status_cache_fresh",
          return_value=True,
        ):
          with patch(
            "app.engines.scan_preview.monday_recovery_cache_fresh",
            return_value=True,
          ):
            with patch(
              "app.engines.platform_status.build_platform_status",
              new=AsyncMock(),
            ) as platform_builder:
              from app.workers.scheduler import refresh_status_caches_job

              await refresh_status_caches_job()
              platform_builder.assert_not_awaited()

  asyncio.run(run())


def test_refresh_status_caches_job_uses_dynamic_ttl_during_us_stocks_watch():
  async def run():
    with patch(
      "app.engines.gate_entry_guard.status_cache_prewarm_active",
      return_value=True,
    ):
      with patch(
        "app.engines.platform_status._platform_status_cache_ttl_seconds",
        return_value=15,
      ):
        with patch(
          "app.engines.gate_prep_status._gate_prep_status_cache_ttl_seconds",
          return_value=15,
        ):
          with patch(
            "app.engines.scan_preview._monday_recovery_cache_ttl_seconds",
            return_value=15,
          ):
            with patch(
              "app.engines.platform_status.platform_status_cache_fresh",
              side_effect=lambda ttl: ttl != 15,
            ) as platform_fresh:
              with patch(
                "app.engines.gate_prep_status.gate_prep_status_cache_fresh",
                return_value=True,
              ):
                with patch(
                  "app.engines.scan_preview.monday_recovery_cache_fresh",
                  return_value=True,
                ):
                  with patch("app.workers.scheduler.SessionLocal") as session_local:
                    session = AsyncMock()
                    session.__aenter__ = AsyncMock(return_value=session)
                    session.__aexit__ = AsyncMock(return_value=None)
                    session_local.return_value = session
                    with patch(
                      "app.engines.platform_status.build_platform_status",
                      new=AsyncMock(return_value={"platform": "ok"}),
                    ) as platform_builder:
                      from app.workers.scheduler import refresh_status_caches_job

                      await refresh_status_caches_job()
                      platform_fresh.assert_called_once_with(15)
                      platform_builder.assert_awaited_once_with(session)

  asyncio.run(run())


def test_refresh_status_caches_job_rebuilds_monday_recovery_when_only_recovery_stale():
  async def run():
    with patch(
      "app.engines.gate_entry_guard.status_cache_prewarm_active",
      return_value=True,
    ):
      with patch(
        "app.engines.platform_status.platform_status_cache_fresh",
        return_value=True,
      ):
        with patch(
          "app.engines.gate_prep_status.gate_prep_status_cache_fresh",
          return_value=True,
        ):
          with patch(
            "app.engines.scan_preview.monday_recovery_cache_fresh",
            return_value=False,
          ):
            with patch("app.workers.scheduler.SessionLocal") as session_local:
              session = AsyncMock()
              session.__aenter__ = AsyncMock(return_value=session)
              session.__aexit__ = AsyncMock(return_value=None)
              session_local.return_value = session
              with patch(
                "app.engines.platform_status.build_platform_status",
                new=AsyncMock(),
              ) as platform_builder:
                with patch(
                  "app.engines.scan_preview.build_monday_recovery_summary",
                  new=AsyncMock(return_value={"open_ready": []}),
                ) as recovery_builder:
                  from app.workers.scheduler import refresh_status_caches_job

                  await refresh_status_caches_job()
                  platform_builder.assert_not_awaited()
                  recovery_builder.assert_awaited_once_with(session)

  asyncio.run(run())


def test_refresh_status_caches_job_rebuilds_platform_when_stale():
  async def run():
    with patch(
      "app.engines.gate_entry_guard.status_cache_prewarm_active",
      return_value=True,
    ):
      with patch(
        "app.engines.platform_status.platform_status_cache_fresh",
        return_value=False,
      ):
        with patch(
          "app.engines.gate_prep_status.gate_prep_status_cache_fresh",
          return_value=True,
        ):
          with patch(
            "app.engines.scan_preview.monday_recovery_cache_fresh",
            return_value=True,
          ):
            with patch("app.workers.scheduler.SessionLocal") as session_local:
              session = AsyncMock()
              session.__aenter__ = AsyncMock(return_value=session)
              session.__aexit__ = AsyncMock(return_value=None)
              session_local.return_value = session
              with patch(
                "app.engines.platform_status.build_platform_status",
                new=AsyncMock(return_value={"platform": "ok"}),
              ) as platform_builder:
                with patch(
                  "app.engines.gate_prep_status.build_gate_prep_status",
                  new=AsyncMock(),
                ) as prep_builder:
                  from app.workers.scheduler import refresh_status_caches_job

                  await refresh_status_caches_job()
                  platform_builder.assert_awaited_once_with(session)
                  prep_builder.assert_not_awaited()

  asyncio.run(run())
