"""Tests for CME deploy urgency and window helpers."""

from app.engines.deploy_status import build_cme_deploy_urgency, build_cme_deploy_window


def test_build_cme_deploy_urgency_none_when_revision_current():
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
