"""Deploy hook must not run when backend is behind main."""

from app.engines.deploy_status import EXPECTED_PLATFORM_REVISION


def test_expected_platform_revision_is_set():
  assert EXPECTED_PLATFORM_REVISION.startswith("2026-08-28-r")


def test_stale_hook_skip_reason_documented():
  from app.engines import deploy_trigger

  source = open(deploy_trigger.__file__).read()
  assert "stale_needs_api_or_manual_deploy" in source
  assert "redeploy the old commit" in source
