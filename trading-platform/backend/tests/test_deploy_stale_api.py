"""Stale API redeploy bypasses DISABLE_AUTO_REDEPLOY when configured."""

from unittest.mock import AsyncMock, patch

from app.engines.deploy_trigger import maybe_trigger_stale_redeploy, stale_api_redeploy_enabled


def test_stale_api_redeploy_enabled_by_default():
  with patch.dict("os.environ", {}, clear=True):
    assert stale_api_redeploy_enabled() is True


def test_stale_api_redeploy_can_be_disabled():
  with patch.dict("os.environ", {"ALLOW_STALE_API_REDEPLOY": "false"}):
    assert stale_api_redeploy_enabled() is False


def test_stale_api_redeploy_when_auto_disabled():
  status = {"is_stale": True, "commits_behind": 1}

  async def _run():
    with patch.dict(
      "os.environ",
      {"DISABLE_AUTO_REDEPLOY": "true", "RENDER_API_KEY": "test-key"},
    ):
      with patch(
        "app.engines.deploy_trigger.build_deploy_status",
        new=AsyncMock(return_value=status),
      ):
        with patch(
          "app.engines.deploy_trigger.fetch_latest_render_deploy_status",
          new=AsyncMock(return_value=None),
        ):
          with patch(
            "app.engines.deploy_trigger.trigger_render_api_deploy",
            new=AsyncMock(return_value={"ok": True, "service_id": "srv-test"}),
          ):
            with patch(
              "app.engines.deploy_trigger.get_platform_setting",
              new=AsyncMock(return_value=None),
            ):
              with patch(
                "app.engines.deploy_trigger.set_platform_setting",
                new=AsyncMock(),
              ):
                with patch(
                  "app.engines.deploy_trigger.SessionLocal",
                ) as mock_session_local:
                  mock_session = AsyncMock()
                  mock_cm = AsyncMock()
                  mock_cm.__aenter__.return_value = mock_session
                  mock_cm.__aexit__.return_value = None
                  mock_session_local.return_value = mock_cm

                  return await maybe_trigger_stale_redeploy()

  import asyncio

  result = asyncio.run(_run())

  assert result["triggered"] is True
  assert result["reason"] == "stale_redeploy_api"
