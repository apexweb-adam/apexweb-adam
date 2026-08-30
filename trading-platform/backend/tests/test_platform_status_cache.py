import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.engines import platform_status


@pytest.fixture(autouse=True)
def _clear_platform_status_cache():
  platform_status.clear_platform_status_cache()
  yield
  platform_status.clear_platform_status_cache()


def test_build_platform_status_uses_short_ttl_cache():
  async def run():
    session = AsyncMock()
    payload = {"platform": "Apex Trading Platform", "stats": {"total_trades": 1}}
    with patch(
      "app.engines.platform_status._build_platform_status_uncached",
      new=AsyncMock(return_value=payload),
    ) as builder:
      first = await platform_status.build_platform_status(session)
      second = await platform_status.build_platform_status(session)
      assert builder.await_count == 1
      assert first["status_cache_hit"] is False
      assert second["status_cache_hit"] is True
      assert second["status_cache_age_seconds"] >= 0

  asyncio.run(run())


def test_dashboard_url_from_deploy_prefers_verified_when_stale():
  deploy = {
    "vercel_bundle_stale": True,
    "verified_dashboard_url": "https://verified.example",
    "dashboard_url": "https://prod.example",
  }
  assert platform_status._dashboard_url_from_deploy(deploy) == "https://verified.example"


def test_dashboard_url_from_deploy_uses_prod_when_fresh():
  deploy = {
    "vercel_bundle_stale": False,
    "verified_dashboard_url": "https://verified.example",
    "dashboard_url": "https://prod.example",
  }
  assert platform_status._dashboard_url_from_deploy(deploy) == "https://prod.example"


def test_platform_status_cache_ttl_extended_during_cme_weekend():
  with patch(
    "app.engines.gate_entry_guard.commodities_futures_weekend_closed",
    return_value=True,
  ):
    assert platform_status._platform_status_cache_ttl_seconds() == 60


_CHECKLIST_SUMMARIES = {
  "cme_reopen": {
    "ready": True,
    "phase": "preflight",
    "open_ready_symbols": [],
    "auto_entry_queued": False,
    "critical_failures": [],
    "has_burst_scan": False,
    "has_auto_entry": False,
  },
  "us_stocks_open": {
    "ready": True,
    "phase": "preflight",
    "open_ready_symbols": [],
    "auto_entry_queued": False,
    "critical_failures": [],
    "has_burst_scan": False,
    "has_auto_entry": False,
  },
}


def test_platform_status_cache_ttl_short_outside_cme_weekend():
  with patch(
    "app.engines.gate_entry_guard.commodities_futures_weekend_closed",
    return_value=False,
  ):
    assert platform_status._platform_status_cache_ttl_seconds() == 45


def test_build_platform_status_includes_per_bot_gate():
  async def run():
    session = AsyncMock()
    gate_payload = {
      "profitability_gate": {"total_trades": 40},
      "per_bot_gate": {
        "commodities": {"graduation_ready": False, "total_trades": 40},
        "crypto": {"paused": True, "graduation_progress": {"overall_pct": 0.4}},
      },
      "gate_entry_tightening": {"active": True},
      "bot_sessions": {},
    }
    with patch(
      "app.engines.platform_status._fetch_stats",
      new=AsyncMock(return_value={"total_trades": 40}),
    ):
      with patch(
        "app.engines.platform_status._fetch_bot_states",
        new=AsyncMock(return_value=[]),
      ):
        with patch(
          "app.engines.platform_status._fetch_learning_counts",
          new=AsyncMock(return_value={}),
        ):
          with patch(
            "app.engines.platform_status.build_gate_ws_payload",
            new=AsyncMock(return_value=gate_payload),
          ):
            with patch(
              "app.engines.platform_status.build_monday_recovery_summary",
              new=AsyncMock(return_value={"open_ready": [], "near_floor": []}),
            ):
              with patch(
                "app.engines.platform_status.build_intel_sources",
                new=AsyncMock(return_value=[]),
              ):
                with patch(
                  "app.engines.platform_status.build_deploy_status",
                  new=AsyncMock(return_value={}),
                ):
                  with patch(
                    "app.engines.platform_status.recommended_dashboard_url",
                    new=AsyncMock(return_value="https://example.com"),
                  ):
                    with patch(
                      "app.engines.platform_status.get_session_open_events",
                      new=AsyncMock(return_value=[]),
                    ):
                      with patch(
                        "app.engines.session_open_checklist_summary.build_session_open_checklist_summaries",
                        new=AsyncMock(return_value=_CHECKLIST_SUMMARIES),
                      ):
                        with patch(
                          "app.engines.platform_status.get_fomo_bearer_status",
                          new=AsyncMock(return_value={}),
                        ):
                          with patch(
                            "app.engines.platform_status.get_axiom_session_status",
                            new=AsyncMock(return_value={}),
                          ):
                            with patch(
                              "app.engines.platform_status.build_crm_content_study_highlights",
                              new=AsyncMock(
                                return_value={"insights_applied": 10, "recent": []}
                              ),
                            ):
                              result = await platform_status.build_platform_status(session)
    assert result["per_bot_gate"]["commodities"]["total_trades"] == 40
    assert result["per_bot_gate"]["crypto"]["paused"] is True
    assert result["content_study"]["insights_applied"] == 10


def test_build_platform_status_includes_content_study():
  async def run():
    session = AsyncMock()
    gate_payload = {
      "profitability_gate": {},
      "per_bot_gate": {},
      "gate_entry_tightening": {"active": False},
      "bot_sessions": {},
    }
    highlights = {"insights_applied": 42, "recent": [{"title": "Risk mgmt", "applied": True}]}
    with patch(
      "app.engines.platform_status._fetch_stats",
      new=AsyncMock(return_value={}),
    ):
      with patch(
        "app.engines.platform_status._fetch_bot_states",
        new=AsyncMock(return_value=[]),
      ):
        with patch(
          "app.engines.platform_status._fetch_learning_counts",
          new=AsyncMock(return_value={}),
        ):
          with patch(
            "app.engines.platform_status.build_gate_ws_payload",
            new=AsyncMock(return_value=gate_payload),
          ):
            with patch(
              "app.engines.platform_status.build_monday_recovery_summary",
              new=AsyncMock(return_value={"open_ready": [], "near_floor": []}),
            ):
              with patch(
                "app.engines.platform_status.build_intel_sources",
                new=AsyncMock(return_value=[]),
              ):
                with patch(
                  "app.engines.platform_status.build_deploy_status",
                  new=AsyncMock(return_value={}),
                ):
                  with patch(
                    "app.engines.platform_status.recommended_dashboard_url",
                    new=AsyncMock(return_value="https://example.com"),
                  ):
                    with patch(
                      "app.engines.platform_status.get_session_open_events",
                      new=AsyncMock(return_value=[]),
                    ):
                      with patch(
                        "app.engines.session_open_checklist_summary.build_session_open_checklist_summaries",
                        new=AsyncMock(return_value=_CHECKLIST_SUMMARIES),
                      ):
                        with patch(
                          "app.engines.platform_status.get_fomo_bearer_status",
                          new=AsyncMock(return_value={}),
                        ):
                          with patch(
                            "app.engines.platform_status.get_axiom_session_status",
                            new=AsyncMock(return_value={}),
                          ):
                            with patch(
                              "app.engines.platform_status.build_crm_content_study_highlights",
                              new=AsyncMock(return_value=highlights),
                            ):
                              result = await platform_status.build_platform_status(session)
    assert result["content_study"] == highlights

  asyncio.run(run())


def test_build_platform_status_deploy_includes_bundle_behind_expected():
  async def run():
    session = AsyncMock()
    gate_payload = {
      "profitability_gate": {},
      "per_bot_gate": {},
      "gate_entry_tightening": {"active": False},
      "bot_sessions": {},
    }
    deploy_info = {
      "vercel_bundle_stale": False,
      "vercel_bundle_behind_expected": True,
      "vercel_bundle_revision": "2026-08-29-r67",
      "expected_dashboard_bundle": "2026-08-29-r98",
      "dashboard_bundle_verify_command": "bash trading-platform/scripts/verify-dashboard-bundle.sh",
      "weekend_ops_verify_command": "bash trading-platform/scripts/verify-weekend-ops.sh",
      "platform_revision_current": False,
    }
    with patch(
      "app.engines.platform_status._fetch_stats",
      new=AsyncMock(return_value={}),
    ):
      with patch(
        "app.engines.platform_status._fetch_bot_states",
        new=AsyncMock(return_value=[]),
      ):
        with patch(
          "app.engines.platform_status._fetch_learning_counts",
          new=AsyncMock(return_value={}),
        ):
          with patch(
            "app.engines.platform_status.build_gate_ws_payload",
            new=AsyncMock(return_value=gate_payload),
          ):
            with patch(
              "app.engines.platform_status.build_monday_recovery_summary",
              new=AsyncMock(return_value={"open_ready": [], "near_floor": []}),
            ):
              with patch(
                "app.engines.platform_status.build_intel_sources",
                new=AsyncMock(return_value=[]),
              ):
                with patch(
                  "app.engines.platform_status.build_deploy_status",
                  new=AsyncMock(return_value=deploy_info),
                ):
                  with patch(
                    "app.engines.platform_status.recommended_dashboard_url",
                    new=AsyncMock(return_value="https://example.com"),
                  ):
                    with patch(
                      "app.engines.platform_status.get_session_open_events",
                      new=AsyncMock(return_value=[]),
                    ):
                      with patch(
                        "app.engines.session_open_checklist_summary.build_session_open_checklist_summaries",
                        new=AsyncMock(return_value=_CHECKLIST_SUMMARIES),
                      ):
                        with patch(
                          "app.engines.platform_status.get_fomo_bearer_status",
                          new=AsyncMock(return_value={}),
                        ):
                          with patch(
                            "app.engines.platform_status.get_axiom_session_status",
                            new=AsyncMock(return_value={}),
                          ):
                            with patch(
                              "app.engines.platform_status.build_crm_content_study_highlights",
                              new=AsyncMock(return_value={"insights_applied": 0, "recent": []}),
                            ):
                              result = await platform_status.build_platform_status(session)
    deploy = result["deploy"]
    assert deploy["vercel_bundle_behind_expected"] is True
    assert deploy["expected_dashboard_bundle"] == "2026-08-29-r98"
    assert "verify-weekend-ops" in deploy["weekend_ops_verify_command"]

  asyncio.run(run())
