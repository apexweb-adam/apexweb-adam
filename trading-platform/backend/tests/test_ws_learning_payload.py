"""Tests for WebSocket learning payload fields."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.ws_manager import build_live_payload


def _empty_scalars():
  result = MagicMock()
  result.all = lambda: []
  result.scalars = lambda: MagicMock(all=lambda: [])
  result.scalar_one_or_none = lambda: None
  return result


def test_build_live_payload_includes_learning_fields():
  session = AsyncMock()
  session.execute = AsyncMock(return_value=_empty_scalars())

  async def fake_gate_payload(s):
    return {
      "profitability_gate": {"win_rate": 0.5},
      "gate_entry_tightening": {"active": True},
      "bot_sessions": {},
    }

  import app.engines.gate_entry_guard as gate_mod
  import app.engines.scan_preview as scan_mod
  import app.engines.session_open_log as session_log_mod
  import app.engines.session_open_checklist_summary as checklist_mod

  orig = gate_mod.build_gate_ws_payload
  orig_summary = scan_mod.build_monday_recovery_summary
  orig_events = session_log_mod.get_session_open_events
  orig_checklists = checklist_mod.build_session_open_checklist_summaries
  gate_mod.build_gate_ws_payload = fake_gate_payload
  scan_mod.build_monday_recovery_summary = AsyncMock(
    return_value={"bots": {}, "all": [], "recovery_candidates": []},
  )
  session_log_mod.get_session_open_events = AsyncMock(return_value=[])
  checklist_mod.build_session_open_checklist_summaries = AsyncMock(
    return_value={
      "cme_reopen": {"ready": True, "open_ready_symbols": [], "auto_entry_queued": False, "critical_failures": [], "has_burst_scan": False, "has_auto_entry": False},
      "us_stocks_open": {"ready": True, "open_ready_symbols": [], "auto_entry_queued": False, "critical_failures": [], "has_burst_scan": False, "has_auto_entry": False},
    },
  )
  try:
    payload = asyncio.run(build_live_payload(session))
    assert "analyses" in payload
    assert "reviews" in payload
    assert "insights" in payload
    assert "intel_sources" in payload
    assert "strategies" in payload
    assert "verification_history" in payload
    assert "monday_recovery" in payload
    assert "session_prep" in payload
    assert "next_session_events" in payload
    assert "cme_reopen" in payload["next_session_events"]
    assert "session_open_events" in payload
    assert isinstance(payload["session_open_events"], list)
    assert "session_open_checklists" in payload
    assert "cme_reopen" in payload["session_open_checklists"]
    assert "deploy" in payload
    assert "cme_deploy_urgency" in payload["deploy"]
    assert "content_study" in payload
    assert isinstance(payload["analyses"], list)
    assert isinstance(payload["reviews"], list)
    assert isinstance(payload["insights"], list)
    assert isinstance(payload["intel_sources"], list)
    assert isinstance(payload["strategies"], list)
  finally:
    gate_mod.build_gate_ws_payload = orig
    scan_mod.build_monday_recovery_summary = orig_summary
    session_log_mod.get_session_open_events = orig_events
    checklist_mod.build_session_open_checklist_summaries = orig_checklists
