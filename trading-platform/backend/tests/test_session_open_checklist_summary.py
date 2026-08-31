"""Tests for session-open checklist summaries."""

from app.engines.session_open_checklist_summary import (
  format_checklist_queue_summary,
  summarize_session_open_checklist,
)


def test_format_checklist_queue_summary_near_floor_gap():
  summary = format_checklist_queue_summary(
    {"symbols": ["NG=F"], "composite_floor": 0.42, "sticky_symbols": ["CL=F"], "release_margin": 0.02},
    {
      "symbols": ["CL=F"],
      "details": [{"symbol": "CL=F", "composite": 0.406, "gap_to_floor": 0.014}],
    },
  )
  assert "NG=F" in summary
  assert "sticky CL=F" in summary
  assert "near floor CL=F +0.014" in summary


def test_summarize_session_open_checklist():
  summary = summarize_session_open_checklist(
    {
      "ready": False,
      "phase": "preflight",
      "prep_phase": "extended",
      "minutes_until_open": 900,
      "open_ready": {
        "symbols": ["NG=F"],
        "sticky_symbols": ["CL=F"],
        "auto_entry_queued": True,
        "composite_floor": 0.42,
        "release_margin": 0.02,
        "details": [
          {"symbol": "NG=F", "composite": 0.634},
          {"symbol": "CL=F", "composite": 0.406, "sticky_queue": True},
        ],
      },
      "near_floor": {
        "symbols": ["CL=F"],
        "details": [{"symbol": "CL=F", "composite": 0.406, "gap_to_floor": 0.014}],
      },
      "checks": [
        {"id": "deploy_current", "status": "fail", "critical": True},
        {"id": "auto_entry_queued", "status": "pass", "critical": True},
      ],
      "session_open_events": {"has_burst_scan": False, "has_auto_entry": False},
    }
  )
  assert summary["ready"] is False
  assert summary["open_ready_symbols"] == ["NG=F"]
  assert summary["sticky_symbols"] == ["CL=F"]
  assert summary["open_ready_composites"] == {"NG=F": 0.634, "CL=F": 0.406}
  assert summary["near_floor_symbols"] == ["CL=F"]
  assert summary["near_floor_gaps"] == {"CL=F": 0.014}
  assert summary["release_margin"] == 0.02
  assert summary["critical_failures"] == ["deploy_current"]


def test_summarize_session_open_checklist_includes_platform_outage_recovery():
  summary = summarize_session_open_checklist(
    {
      "ready": False,
      "phase": "post_open",
      "open_ready": {"symbols": ["AAPL"], "auto_entry_queued": True},
      "checks": [],
      "session_open_events": {"has_burst_scan": False, "has_auto_entry": False},
      "platform_outage_recovery": {
        "window_active": True,
        "logged": False,
        "grace_minutes_remaining": 165,
      },
    }
  )
  assert summary["platform_outage_recovery"]["window_active"] is True
  assert summary["platform_outage_recovery"]["grace_minutes_remaining"] == 165
