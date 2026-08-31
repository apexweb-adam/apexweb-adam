"""Tests for WebSocket learning payload fields."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

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
  import app.engines.platform_outage_log as outage_mod
  import app.intelligence.fomo_tracker as fomo_mod

  orig = gate_mod.build_gate_ws_payload
  orig_summary = scan_mod.build_monday_recovery_summary
  orig_events = session_log_mod.get_session_open_events
  orig_checklists = checklist_mod.build_session_open_checklist_summaries
  orig_outage = outage_mod.get_platform_outage_events
  orig_fomo = fomo_mod.get_fomo_bearer_status
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
  outage_mod.get_platform_outage_events = AsyncMock(return_value=[])
  fomo_mod.get_fomo_bearer_status = AsyncMock(
    return_value={"configured": True, "polling_active": False, "minutes_remaining": -10},
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
    assert "platform_outage_events" in payload
    assert isinstance(payload["platform_outage_events"], list)
    assert "session_open_checklists" in payload
    assert "cme_reopen" in payload["session_open_checklists"]
    assert "deploy" in payload
    assert "cme_deploy_urgency" in payload["deploy"]
    assert "cme_deploy_window" in payload["deploy"]
    assert "deploy_credentials_warnings" in payload["deploy"]
    assert payload["deploy"]["deploy_credentials_ready"] is False
    assert "content_study" in payload
    assert "learning" in payload
    assert "intel_pattern_alerts" in payload["learning"]
    assert payload.get("paper_trading_only") is True
    assert "integrations" in payload
    assert "polymarket_market_scanner" in payload["integrations"]
    assert "x_intel_collection_mode" in payload["integrations"]
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
    outage_mod.get_platform_outage_events = orig_outage
    fomo_mod.get_fomo_bearer_status = orig_fomo


def test_build_live_payload_content_study_includes_source_labels():
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
  import app.engines.platform_outage_log as outage_mod
  import app.intelligence.fomo_tracker as fomo_mod

  orig = gate_mod.build_gate_ws_payload
  orig_summary = scan_mod.build_monday_recovery_summary
  orig_events = session_log_mod.get_session_open_events
  orig_checklists = checklist_mod.build_session_open_checklist_summaries
  orig_outage = outage_mod.get_platform_outage_events
  orig_fomo = fomo_mod.get_fomo_bearer_status
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
  outage_mod.get_platform_outage_events = AsyncMock(return_value=[])
  fomo_mod.get_fomo_bearer_status = AsyncMock(
    return_value={"configured": True, "polling_active": False, "minutes_remaining": -10},
  )

  content_study = {
    "insights_applied": 5,
    "recent": [
      {
        "source_type": "newsapi",
        "source_label": "News",
        "title": "Fed signals higher rates",
        "impact": "stocks_futures bot: tighten sentiment gate",
        "confidence": 0.71,
        "applied": True,
      },
      {
        "source_type": "political",
        "source_label": "Political",
        "title": "US tariff on steel imports",
        "impact": "commodities bot: tighten sentiment gate",
        "confidence": 0.74,
        "applied": True,
      },
    ],
  }

  with patch(
    "app.engines.learning_engine.build_crm_content_study_highlights",
    new_callable=AsyncMock,
    return_value=content_study,
  ):
    try:
      payload = asyncio.run(build_live_payload(session))
      labels = [row["source_label"] for row in payload["content_study"]["recent"]]
      assert labels == ["News", "Political"]
    finally:
      gate_mod.build_gate_ws_payload = orig
      scan_mod.build_monday_recovery_summary = orig_summary
      session_log_mod.get_session_open_events = orig_events
      checklist_mod.build_session_open_checklist_summaries = orig_checklists
      outage_mod.get_platform_outage_events = orig_outage
      fomo_mod.get_fomo_bearer_status = orig_fomo
