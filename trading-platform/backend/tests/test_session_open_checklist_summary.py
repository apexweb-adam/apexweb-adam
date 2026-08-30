"""Tests for session-open checklist summaries."""

from app.engines.session_open_checklist_summary import summarize_session_open_checklist


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
  assert summary["near_floor_symbols"] == ["CL=F"]
  assert summary["near_floor_gaps"] == {"CL=F": 0.014}
  assert summary["release_margin"] == 0.02
  assert summary["critical_failures"] == ["deploy_current"]
