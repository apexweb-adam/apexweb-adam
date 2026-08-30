"""Deploy hook must not run when backend is behind main."""

from app.engines.deploy_status import EXPECTED_PLATFORM_REVISION


def test_expected_platform_revision_is_set():
  assert EXPECTED_PLATFORM_REVISION.startswith("2026-08-29-r")
  assert EXPECTED_PLATFORM_REVISION.endswith("374")


def test_stale_hook_skip_reason_documented():
  from app.engines import deploy_trigger

  source = open(deploy_trigger.__file__).read()
  assert "stale_needs_api_or_manual_deploy" in source
  assert "allow_stale_hook" in source
  assert "render-hook-recovery" in source
  # Stale hook guard must not be bypassed by force alone
  stale_guard = source.split("Skip hook when stale", 1)[1].split("hook = await resolve_render_deploy_hook", 1)[0]
  assert "not allow_stale_hook" in stale_guard
  assert "not force" not in stale_guard
