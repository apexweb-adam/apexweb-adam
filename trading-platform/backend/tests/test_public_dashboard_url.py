"""Public tunnel dashboard URL routing."""

import asyncio
import os
from unittest.mock import AsyncMock, patch

from app.engines.deploy_status import configured_public_dashboard_url, recommended_dashboard_url


def test_configured_public_dashboard_url_from_env(monkeypatch):
  monkeypatch.setenv("PUBLIC_DASHBOARD_URL", "https://example.trycloudflare.com")
  assert configured_public_dashboard_url() == "https://example.trycloudflare.com"


def test_recommended_dashboard_prefers_public_tunnel(monkeypatch):
  from app.engines import deploy_status

  deploy_status.clear_recommended_dashboard_cache()
  monkeypatch.setenv("PUBLIC_DASHBOARD_URL", "https://tunnel.example.com")
  cfg = {"bundleRevision": "2026-08-28-r25", "features": {"activeGate": True}}

  async def run():
    with patch("app.engines.deploy_status.probe_dashboard_config", new=AsyncMock(return_value=cfg)):
      return await recommended_dashboard_url()

  url = asyncio.run(run())
  assert url == "https://tunnel.example.com"
  deploy_status.clear_recommended_dashboard_cache()
