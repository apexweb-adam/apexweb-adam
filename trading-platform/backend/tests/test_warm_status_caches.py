import asyncio
from unittest.mock import AsyncMock, patch

from app.workers.scheduler import warm_status_caches_job


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
      "app.engines.gate_entry_guard.commodities_futures_weekend_closed",
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
            "app.engines.platform_status.build_platform_status",
            new=AsyncMock(),
          ) as platform_builder:
            from app.workers.scheduler import refresh_status_caches_job

            await refresh_status_caches_job()
            platform_builder.assert_not_awaited()

  asyncio.run(run())


def test_refresh_status_caches_job_rebuilds_when_stale():
  async def run():
    with patch(
      "app.engines.gate_entry_guard.commodities_futures_weekend_closed",
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
