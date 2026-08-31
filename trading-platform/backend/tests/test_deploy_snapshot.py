"""Tests for lightweight /api/deploy/snapshot."""

from unittest.mock import patch

from app.engines.deploy_status import (
  EXPECTED_DASHBOARD_BUNDLE,
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
  assert snap["expected_dashboard_bundle"] == EXPECTED_DASHBOARD_BUNDLE
  assert "verify-dashboard-bundle" in snap["dashboard_bundle_verify_command"]
  assert "verify-weekend-ops" in snap["weekend_ops_verify_command"]
  assert "verify-crm-learning" in snap["crm_learning_verify_command"]
  assert "run-deploy-window" in snap["run_deploy_window_command"]
  assert "wait-for-render-deploy" in snap["wait_for_deploy_command"]
  window = snap["cme_deploy_window"]
  assert window is not None
  assert window.get("in_window") is True
  assert window.get("deploy_command")
  assert "run-deploy-window" in (window.get("run_deploy_window_command") or "")


def test_build_deploy_snapshot_includes_github_token_flag():
  with patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_test", "PLATFORM_REVISION": "2026-08-29-r336"}, clear=False):
    with patch(
      "app.engines.gate_entry_guard.commodities_session_info",
      return_value={"minutes_until_open": 500, "in_session": False},
    ):
      snap = build_deploy_snapshot()
  assert snap["github_token_configured"] is True


def test_build_deploy_snapshot_includes_x_intel_collection_mode():
  with patch.dict("os.environ", {"PLATFORM_REVISION": "2026-08-29-r336"}, clear=False):
    with patch(
      "app.engines.gate_entry_guard.commodities_session_info",
      return_value={"minutes_until_open": 500, "in_session": False},
    ):
      with patch(
        "app.engines.intel_source_status.settings",
      ) as mock_settings:
        mock_settings.twitter_bearer_token = ""
        mock_settings.newsapi_key = ""
        snap = build_deploy_snapshot()
  assert snap["x_intel_collection_mode"] == "google_news_rss"


def test_build_deploy_snapshot_no_window_when_current():
  with patch.dict("os.environ", {"PLATFORM_REVISION": EXPECTED_PLATFORM_REVISION}, clear=False):
    with patch(
      "app.engines.gate_entry_guard.commodities_session_info",
      return_value={"minutes_until_open": 500, "in_session": False},
    ):
      snap = build_deploy_snapshot()
  assert snap["platform_revision_current"] is True
  assert snap["cme_deploy_window"] is None


def test_apply_fomo_bearer_github_missing_is_nudge_not_blocker():
  from app.engines.deploy_status import apply_fomo_bearer_to_snapshot

  snap = apply_fomo_bearer_to_snapshot(
    {"platform_revision": "2026-08-29-r336", "github_token_configured": False},
    {"configured": False, "polling_active": False, "minutes_remaining": None},
  )
  assert snap["deploy_credentials_ready"] is True
  assert any("GITHUB" in n for n in snap["deploy_credentials_nudges"])
  assert snap["deploy_credentials_warnings"] == []


def test_apply_fomo_bearer_to_snapshot_marks_expired():
  from app.engines.deploy_status import apply_fomo_bearer_to_snapshot

  snap = apply_fomo_bearer_to_snapshot(
    {"platform_revision": "2026-08-29-r336"},
    {"configured": True, "polling_active": False, "minutes_remaining": -120},
  )
  assert snap["fomo_bearer_configured"] is True
  assert snap["fomo_bearer_polling_active"] is False
  assert snap["fomo_bearer_minutes_remaining"] == -120
  assert snap["fomo_bearer_nudge_tier"] == "expired"
  assert "expired" in (snap.get("fomo_bearer_nudge_message") or "")
  assert "fomo-set-bearer" in snap["fomo_bearer_refresh_hint"]
  assert snap["deploy_credentials_ready"] is False
  assert any("fomo" in w for w in snap["deploy_credentials_warnings"])


def test_apply_fomo_bearer_to_snapshot_nudge_tier_60():
  from app.engines.deploy_status import apply_fomo_bearer_to_snapshot

  snap = apply_fomo_bearer_to_snapshot(
    {"platform_revision": "2026-08-29-r336", "github_token_configured": True},
    {"configured": True, "polling_active": True, "minutes_remaining": 42},
  )
  assert snap["fomo_bearer_nudge_tier"] == "60"
  assert "42min" in (snap.get("fomo_bearer_nudge_message") or "")
  assert snap["deploy_credentials_ready"] is True


def test_apply_fomo_bearer_to_snapshot_ready_when_polling():
  from app.engines.deploy_status import apply_fomo_bearer_to_snapshot

  snap = apply_fomo_bearer_to_snapshot(
    {"platform_revision": "2026-08-29-r336", "github_token_configured": True},
    {"configured": True, "polling_active": True, "minutes_remaining": 90},
  )
  assert snap["deploy_credentials_ready"] is True
  assert snap["deploy_credentials_warnings"] == []


def test_apply_learning_to_snapshot_merges_learning_and_content_study():
  from app.engines.deploy_status import apply_learning_to_snapshot

  snap = apply_learning_to_snapshot(
    {"platform_revision": "2026-08-29-r467"},
    learning={"trade_analyses": 12, "intel_pattern_count": 1},
    content_study={
      "insights_applied": 3,
      "recent": [{"source_type": "political", "source_label": "Political", "title": "Tariff"}],
    },
  )
  assert snap["learning"]["trade_analyses"] == 12
  assert snap["content_study"]["recent"][0]["source_label"] == "Political"


def test_deploy_snapshot_route():
  from unittest.mock import AsyncMock

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
    with patch(
      "app.intelligence.fomo_tracker.get_fomo_bearer_status",
      new_callable=AsyncMock,
      return_value={"configured": True, "polling_active": False, "minutes_remaining": -5},
    ):
      with patch(
        "app.engines.platform_status._fetch_learning_counts",
        new_callable=AsyncMock,
        return_value={
          "trade_analyses": 5,
          "daily_reviews": 2,
          "intel_pattern_count": 1,
          "intel_pattern_alerts": ["commodities: Political/macro intel"],
        },
      ):
        with patch(
          "app.engines.learning_engine.build_crm_content_study_highlights",
          new_callable=AsyncMock,
          return_value={
            "insights_applied": 4,
            "recent": [
              {
                "source_type": "newsapi",
                "source_label": "News",
                "title": "Fed signals higher rates",
                "applied": True,
              }
            ],
          },
        ):
          client = TestClient(app)
          resp = client.get("/api/deploy/snapshot")
  assert resp.status_code == 200
  body = resp.json()
  assert body["platform_revision"] == "2026-08-29-r336"
  assert body["cme_deploy_window"]["message"] == "opens soon"
  assert body["fomo_bearer_polling_active"] is False
  assert body["fomo_bearer_minutes_remaining"] == -5
  assert body["fomo_bearer_nudge_tier"] == "expired"
  assert body["learning"]["trade_analyses"] == 5
  assert body["content_study"]["recent"][0]["source_label"] == "News"
