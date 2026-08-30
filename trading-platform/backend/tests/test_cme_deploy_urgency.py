"""Tests for CME deploy urgency and window helpers."""

from app.engines.deploy_status import build_cme_deploy_urgency, build_cme_deploy_window


def test_format_dashboard_bundle_crm_html():
  from app.engines.deploy_status import format_dashboard_bundle_crm_html

  html = format_dashboard_bundle_crm_html(
    prod_bundle="2026-08-29-r67",
    expected_bundle="2026-08-29-r98",
    promote_id="dpl_test123",
  )
  assert "Dashboard bundle behind code" in html
  assert "2026-08-29-r67" in html
  assert "2026-08-29-r98" in html
  assert "verify-dashboard-bundle.sh" in html
  assert "dpl_test123" in html


def test_format_cme_deploy_window_crm_html():
  from app.engines.deploy_status import format_cme_deploy_window_crm_html

  html = format_cme_deploy_window_crm_html(
    {
      "in_window": False,
      "window_closed": False,
      "message": "Deploy window opens in 8h 20m (2026-08-30 16:00 UTC)",
      "verify_command": "bash trading-platform/scripts/verify-pre-deploy.sh",
      "deploy_command": "TRIGGER_DEPLOY=true bash trading-platform/scripts/sync-render-env.sh",
      "weekend_ops_command": "bash trading-platform/scripts/verify-weekend-ops.sh",
    }
  )
  assert "CME deploy window countdown" in html
  assert "16:00 UTC" in html
  assert "verify-pre-deploy.sh" in html
  assert "verify-weekend-ops.sh" in html
  assert (
    build_cme_deploy_urgency(
      platform_revision_current=True,
      cme_minutes_until_open=120,
    )
    is None
  )


def test_build_cme_deploy_urgency_none_when_cme_far():
  assert (
    build_cme_deploy_urgency(
      platform_revision_current=False,
      cme_minutes_until_open=500,
    )
    is None
  )


def test_build_cme_deploy_urgency_active_when_revision_behind_and_cme_near():
  result = build_cme_deploy_urgency(
    platform_revision_current=False,
    cme_minutes_until_open=180,
  )
  assert result is not None
  assert result["active"] is True
  assert result["minutes_until_open"] == 180
  assert "3h 0m" in result["message"]
  assert "sync-render-env.sh" in result["deploy_command"]


def test_build_cme_deploy_window_countdown_before_window():
  result = build_cme_deploy_window(
    platform_revision_current=False,
    cme_minutes_until_open=500,
  )
  assert result is not None
  assert result["in_window"] is False
  assert result["minutes_until_window_opens"] == 140
  assert "Deploy window opens in" in result["message"]
  assert result["window_opens_at_utc"] is not None


def test_build_cme_deploy_window_active_in_window():
  result = build_cme_deploy_window(
    platform_revision_current=False,
    cme_minutes_until_open=300,
  )
  assert result is not None
  assert result["in_window"] is True
  assert result["minutes_until_window_closes"] == 60
  assert "Deploy window active" in result["message"]


def test_build_cme_deploy_window_none_when_revision_current():
  assert (
    build_cme_deploy_window(
      platform_revision_current=True,
      cme_minutes_until_open=500,
    )
    is None
  )
