"""Tests for verified dashboard URL discovery and recommended_dashboard_url fallback."""

import asyncio
from unittest.mock import AsyncMock, patch

from app.engines import deploy_status


def test_verified_candidates_probe_configured_first():
  with patch.dict(
    "os.environ",
    {
      "VERIFIED_DASHBOARD_URL": "https://example-verified.vercel.app",
      "VERIFIED_DASHBOARD_FALLBACKS": "",
    },
    clear=False,
  ):
    candidates = deploy_status.verified_dashboard_candidates()
  assert candidates[0] == "https://example-verified.vercel.app"
  assert candidates[-1] == "https://apex-trading-dashboard-git-main-apexweb-adams-projects.vercel.app"


def test_discover_skips_stale_git_main_when_configured_is_newer():
  configured_url = "https://apex-trading-dashboard-73nruanbo-apexweb-adams-projects.vercel.app"
  git_main = "https://apex-trading-dashboard-git-main-apexweb-adams-projects.vercel.app"

  async def fake_probe(url: str):
    if url == configured_url:
      return {"bundleRevision": "2026-08-28-r25", "features": {"activeGate": True}}
    if url == git_main:
      return {"bundleRevision": "2026-08-28-r21", "features": {"activeGate": True}}
    return None

  with patch.object(deploy_status, "probe_dashboard_config", side_effect=fake_probe):
    with patch.object(deploy_status, "verified_dashboard_candidates", return_value=[configured_url, git_main]):
      result = asyncio.run(deploy_status.discover_verified_dashboard())

  assert result["verified_dashboard_url"] == configured_url
  assert result["vercel_bundle_revision"] == "2026-08-28-r25"


def test_recommended_dashboard_url_uses_configured_probe():
  configured_url = "https://apex-trading-dashboard-73nruanbo-apexweb-adams-projects.vercel.app"

  with patch.object(deploy_status, "configured_public_dashboard_url", return_value=None):
    with patch.object(
      deploy_status,
      "probe_configured_verified_dashboard",
      AsyncMock(
        return_value={
          "verified_dashboard_url": configured_url,
          "vercel_bundle_revision": "2026-08-28-r25",
          "discovered": False,
        }
      ),
    ):
      url = asyncio.run(deploy_status.recommended_dashboard_url())

  assert url == configured_url
