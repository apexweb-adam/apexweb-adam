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
  assert "https://apex-trading-dashboard-git-main-apexweb-adams-projects.vercel.app" in candidates
  assert candidates[-1] == "https://apex-trading-dashboard-apexweb-adams-projects.vercel.app"


def test_discover_skips_stale_git_main_when_configured_is_newer():
  deploy_status.clear_discover_verified_dashboard_cache()
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


def test_verified_candidates_include_r31_recovery_preview():
  candidates = deploy_status.verified_dashboard_candidates()
  assert "https://apex-trading-dashboard-4am3sz5kv-apexweb-adams-projects.vercel.app" in candidates


def test_discover_prefers_r31_over_stale_git_main():
  deploy_status.clear_discover_verified_dashboard_cache()
  r31 = "https://apex-trading-dashboard-4am3sz5kv-apexweb-adams-projects.vercel.app"
  git_main = "https://apex-trading-dashboard-git-main-apexweb-adams-projects.vercel.app"

  async def fake_probe(url: str):
    if url == r31:
      return {"bundleRevision": "2026-08-29-r31", "features": {"activeGate": True}}
    if url == git_main:
      return {"bundleRevision": "2026-08-28-r29", "features": {"activeGate": True}}
    return None

  with patch.object(deploy_status, "probe_dashboard_config", side_effect=fake_probe):
    with patch.object(deploy_status, "configured_verified_dashboard_url", return_value=r31):
      with patch.object(deploy_status, "verified_dashboard_candidates", return_value=[r31, git_main]):
        result = asyncio.run(deploy_status.discover_verified_dashboard())

  assert result["verified_dashboard_url"] == r31
  assert result["vercel_bundle_revision"] == "2026-08-29-r31"


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


def test_discover_verified_dashboard_uses_cache():
  deploy_status.clear_discover_verified_dashboard_cache()
  cached = {
    "verified_dashboard_url": "https://cached.example",
    "vercel_bundle_revision": "2026-08-29-r67",
    "discovered": False,
  }
  deploy_status._discover_verified_cache = dict(cached)
  deploy_status._discover_verified_cached_at = __import__("time").monotonic()

  with patch.object(deploy_status, "probe_configured_verified_dashboard", AsyncMock()) as probe:
    result = asyncio.run(deploy_status.discover_verified_dashboard())

  assert result == cached
  probe.assert_not_called()


def test_dashboard_url_from_deploy_prefers_verified_when_stale():
  deploy = {
    "vercel_bundle_stale": True,
    "verified_dashboard_url": "https://verified.example",
    "dashboard_url": "https://prod.example",
  }
  assert deploy_status.dashboard_url_from_deploy(deploy) == "https://verified.example"


def test_resolve_vercel_promote_deployment_id_uses_verified_url():
  verified = "https://apex-trading-dashboard-git-main-apexweb-adams-projects.vercel.app"

  class FakeResponse:
    status_code = 200

    def json(self):
      return {"id": "dpl_FapXAbo4Dv8WKU8ZEtDYtC7FryU7"}

  class FakeClient:
    async def __aenter__(self):
      return self

    async def __aexit__(self, *args):
      return None

    async def get(self, url, params=None, headers=None):
      assert params["url"] == "apex-trading-dashboard-git-main-apexweb-adams-projects.vercel.app"
      return FakeResponse()

  with patch.dict("os.environ", {"VERCEL_TOKEN": "test-token"}, clear=False):
    with patch("app.engines.deploy_status.httpx.AsyncClient", return_value=FakeClient()):
      result = asyncio.run(deploy_status.resolve_vercel_promote_deployment_id(verified))

  assert result == "dpl_FapXAbo4Dv8WKU8ZEtDYtC7FryU7"


def test_resolve_vercel_promote_deployment_id_falls_back_without_token():
  with patch.dict("os.environ", {"VERCEL_TOKEN": ""}, clear=False):
    result = asyncio.run(
      deploy_status.resolve_vercel_promote_deployment_id(
        "https://apex-trading-dashboard-git-main-apexweb-adams-projects.vercel.app"
      )
    )
  assert result == deploy_status.DEFAULT_VERIFIED_DEPLOYMENT_ID
  assert result == "dpl_FapXAbo4Dv8WKU8ZEtDYtC7FryU7"


def test_fetch_vercel_behind_expected_uses_verified_promote_id():
  prod_cfg = {"bundleRevision": "2026-08-29-r67", "features": {"activeGate": True}}
  verified_url = "https://apex-trading-dashboard-git-main-apexweb-adams-projects.vercel.app"

  with patch.object(deploy_status, "probe_dashboard_config", AsyncMock(return_value=prod_cfg)):
    with patch.object(deploy_status, "probe_production_proxy_operational", AsyncMock(return_value=True)):
      with patch.object(
        deploy_status,
        "discover_verified_dashboard",
        AsyncMock(
          return_value={
            "verified_dashboard_url": verified_url,
            "vercel_bundle_revision": "2026-08-29-r98",
            "discovered": True,
          }
        ),
      ):
        with patch.object(
          deploy_status,
          "resolve_vercel_promote_deployment_id",
          AsyncMock(return_value="dpl_FapXAbo4Dv8WKU8ZEtDYtC7FryU7"),
        ) as resolve:
          result = asyncio.run(deploy_status.fetch_vercel_dashboard_bundle())

  resolve.assert_awaited_once_with(verified_url)
  assert result["vercel_promote_deployment_id"] == "dpl_FapXAbo4Dv8WKU8ZEtDYtC7FryU7"
  assert result["verified_bundle_revision"] == "2026-08-29-r98"


def test_resolve_crm_dashboard_url_reuses_deploy_snapshot():
  deploy = {
    "vercel_bundle_stale": True,
    "verified_dashboard_url": "https://verified.example",
    "dashboard_url": "https://prod.example",
  }

  with patch.object(deploy_status, "build_deploy_status", AsyncMock()) as build:
    with patch.object(deploy_status, "configured_public_dashboard_url", return_value=None):
      url = asyncio.run(deploy_status.resolve_crm_dashboard_url(deploy))

  assert url == "https://verified.example"
  build.assert_not_called()
