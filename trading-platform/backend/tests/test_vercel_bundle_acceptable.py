"""Tests for Vercel bundle stale vs behind-expected detection."""

import asyncio
from unittest.mock import AsyncMock, patch

from app.engines import deploy_status


def test_fetch_vercel_not_stale_when_acceptable_and_proxy_ok():
  prod_cfg = {"bundleRevision": "2026-08-29-r39", "features": {"activeGate": True}}

  with patch.object(deploy_status, "probe_dashboard_config", AsyncMock(return_value=prod_cfg)):
    with patch.object(deploy_status, "probe_production_proxy_operational", AsyncMock(return_value=True)):
      with patch.object(
        deploy_status,
        "discover_verified_dashboard",
        AsyncMock(
          return_value={
            "verified_dashboard_url": "https://apex-trading-dashboard-o7tb7wydk-apexweb-adams-projects.vercel.app",
            "vercel_bundle_revision": "2026-08-29-r67",
            "discovered": True,
          }
        ),
      ):
        result = asyncio.run(deploy_status.fetch_vercel_dashboard_bundle())

  assert result["vercel_bundle_stale"] is False
  assert result["vercel_bundle_behind_expected"] is True
  assert result["vercel_bundle_revision"] == "2026-08-29-r39"
  assert result["verified_dashboard_url"].endswith("vercel.app")
  assert result["verified_bundle_revision"] == "2026-08-29-r67"


def test_fetch_vercel_stale_when_not_acceptable():
  prod_cfg = {"bundleRevision": "2026-08-27-r8", "features": {"activeGate": True}}

  with patch.object(deploy_status, "probe_dashboard_config", AsyncMock(return_value=prod_cfg)):
    with patch.object(deploy_status, "probe_production_proxy_operational", AsyncMock(return_value=True)):
      with patch.object(
        deploy_status,
        "discover_verified_dashboard",
        AsyncMock(
          return_value={
            "verified_dashboard_url": "https://example.vercel.app",
            "vercel_bundle_revision": "2026-08-29-r39",
            "discovered": True,
          }
        ),
      ):
        result = asyncio.run(deploy_status.fetch_vercel_dashboard_bundle())

  assert result["vercel_bundle_stale"] is True
