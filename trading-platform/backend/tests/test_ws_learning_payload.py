"""Tests for WebSocket learning payload fields."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.ws_manager import build_live_payload


def _empty_scalars():
  return MagicMock(all=lambda: [], scalars=lambda: MagicMock(all=lambda: []))


def test_build_live_payload_includes_learning_fields():
  session = AsyncMock()
  session.execute = AsyncMock(return_value=_empty_scalars())

  async def fake_gate_payload(s):
    return {
      "profitability_gate": {"win_rate": 0.5},
      "gate_entry_tightening": {"active": True},
      "bot_sessions": {},
    }

  import app.ws_manager as ws_mod
  import app.engines.gate_entry_guard as gate_mod
  import app.engines.scan_preview as scan_mod

  orig = gate_mod.build_gate_ws_payload
  orig_summary = scan_mod.build_monday_recovery_summary
  gate_mod.build_gate_ws_payload = fake_gate_payload
  scan_mod.build_monday_recovery_summary = AsyncMock(
    return_value={"bots": {}, "all": [], "recovery_candidates": []},
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
    assert isinstance(payload["analyses"], list)
    assert isinstance(payload["reviews"], list)
    assert isinstance(payload["insights"], list)
    assert isinstance(payload["intel_sources"], list)
    assert isinstance(payload["strategies"], list)
  finally:
    gate_mod.build_gate_ws_payload = orig
    scan_mod.build_monday_recovery_summary = orig_summary
