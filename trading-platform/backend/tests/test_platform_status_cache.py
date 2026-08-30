import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.engines import platform_status


@pytest.fixture(autouse=True)
def _clear_platform_status_cache():
  platform_status.clear_platform_status_cache()
  yield
  platform_status.clear_platform_status_cache()


def test_build_platform_status_uses_short_ttl_cache():
  async def run():
    session = AsyncMock()
    payload = {"platform": "Apex Trading Platform", "stats": {"total_trades": 1}}
    with patch(
      "app.engines.platform_status._build_platform_status_uncached",
      new=AsyncMock(return_value=payload),
    ) as builder:
      first = await platform_status.build_platform_status(session)
      second = await platform_status.build_platform_status(session)
      assert builder.await_count == 1
      assert first["status_cache_hit"] is False
      assert second["status_cache_hit"] is True
      assert second["status_cache_age_seconds"] >= 0

  asyncio.run(run())


def test_dashboard_url_from_deploy_prefers_verified_when_stale():
  deploy = {
    "vercel_bundle_stale": True,
    "verified_dashboard_url": "https://verified.example",
    "dashboard_url": "https://prod.example",
  }
  assert platform_status._dashboard_url_from_deploy(deploy) == "https://verified.example"


def test_dashboard_url_from_deploy_uses_prod_when_fresh():
  deploy = {
    "vercel_bundle_stale": False,
    "verified_dashboard_url": "https://verified.example",
    "dashboard_url": "https://prod.example",
  }
  assert platform_status._dashboard_url_from_deploy(deploy) == "https://prod.example"
