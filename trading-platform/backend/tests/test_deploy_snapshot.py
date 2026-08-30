"""Tests for lightweight /api/deploy/snapshot."""

from unittest.mock import patch

from app.engines.deploy_status import (
  EXPECTED_PLATFORM_REVISION,
  build_deploy_snapshot,
)


def test_build_deploy_snapshot_includes_deploy_window_when_behind():
  with patch.dict("os.environ", {"PLATFORM_REVISION": "2026-08-29-r336"}, clear=False):
    with patch(
      "app.engines.gate_entry_guard.commodities_session_info",
      return_value={"minutes_until_open": 300, "in_session": False},
    ):
      snap = build_deploy_snapshot()
  assert snap["platform_revision"] == "2026-08-29-r336"
  assert snap["platform_revision_current"] is False
  assert snap["expected_platform_revision"] == EXPECTED_PLATFORM_REVISION
  assert snap["expected_dashboard_bundle"] == "2026-08-29-r98"
  assert "verify-dashboard-bundle" in snap["dashboard_bundle_verify_command"]
  assert "verify-weekend-ops" in snap["weekend_ops_verify_command"]
  assert "run-deploy-window" in snap["run_deploy_window_command"]
  assert "wait-for-render-deploy" in snap["wait_for_deploy_command"]
  window = snap["cme_deploy_window"]
  assert window is not None
  assert window.get("in_window") is True
  assert window.get("deploy_command")
  assert "run-deploy-window" in (window.get("run_deploy_window_command") or "")


def test_build_deploy_snapshot_no_window_when_current():
  with patch.dict("os.environ", {"PLATFORM_REVISION": EXPECTED_PLATFORM_REVISION}, clear=False):
    with patch(
      "app.engines.gate_entry_guard.commodities_session_info",
      return_value={"minutes_until_open": 500, "in_session": False},
    ):
      snap = build_deploy_snapshot()
  assert snap["platform_revision_current"] is True
  assert snap["cme_deploy_window"] is None


def test_deploy_snapshot_route():
  from fastapi.testclient import TestClient

  from app.main import app

  with patch(
    "app.engines.deploy_status.build_deploy_snapshot",
    return_value={
      "platform_revision": "2026-08-29-r336",
      "expected_platform_revision": EXPECTED_PLATFORM_REVISION,
      "platform_revision_current": False,
      "cme_deploy_window": {"in_window": False, "message": "opens soon"},
    },
  ):
    client = TestClient(app)
    resp = client.get("/api/deploy/snapshot")
  assert resp.status_code == 200
  body = resp.json()
  assert body["platform_revision"] == "2026-08-29-r336"
  assert body["cme_deploy_window"]["message"] == "opens soon"
