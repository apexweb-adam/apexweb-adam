import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.engines import gate_prep_status


@pytest.fixture(autouse=True)
def _clear_gate_prep_cache():
  gate_prep_status.clear_gate_prep_status_cache()
  yield
  gate_prep_status.clear_gate_prep_status_cache()


def test_build_gate_prep_status_uses_short_ttl_cache():
  async def run():
    session = AsyncMock()
    payload = {
      "commodities": {"prep_phase": "extended"},
      "next_session_events": {},
    }
    with patch(
      "app.engines.gate_prep_status._build_gate_prep_status_uncached",
      new=AsyncMock(return_value=payload),
    ) as builder:
      first = await gate_prep_status.build_gate_prep_status(session)
      second = await gate_prep_status.build_gate_prep_status(session)
      assert builder.await_count == 1
      assert first["prep_cache_hit"] is False
      assert second["prep_cache_hit"] is True

  asyncio.run(run())


def test_build_session_prep_status_includes_prep_phase_fields():
  from app.engines.gate_entry_guard import build_session_prep_status

  status = build_session_prep_status(
    stocks_session={"in_session": False, "minutes_until_open": 3000, "mode": "weekend_closed"},
    commodities_session={"in_session": False, "minutes_until_open": 45, "mode": "weekend_closed"},
    stocks_trade_count_nudge=True,
    commodities_graduation_nudge=True,
  )
  assert status["commodities"]["prep_phase"] == "imminent"
  assert status["commodities"]["prep_scan_label"] == "5s"
  assert status["commodities"]["minutes_until_imminent_scan"] == 0
  assert status["stocks_futures"]["prep_phase"] == "extended"
  assert status["stocks_futures"]["prep_scan_label"] == "15s"
  assert status["stocks_futures"]["minutes_until_imminent_scan"] == 2970


def test_gate_prep_status_cache_ttl_extended_during_cme_weekend():
  with patch(
    "app.engines.gate_entry_guard.commodities_futures_weekend_closed",
    return_value=True,
  ):
    assert gate_prep_status._gate_prep_status_cache_ttl_seconds() == 60


def test_enrich_prep_with_session_events_surfaces_auto_entry():
  session_prep = {
    "commodities": {"prep_phase": "extended", "open_ready_symbols": ["NG=F"]},
    "stocks_futures": {"prep_phase": "extended"},
  }
  next_session_events = {
    "cme_reopen": {
      "auto_entry_queued": True,
      "composite_floor": 0.42,
      "open_ready_symbols": ["NG=F", "CL=F"],
      "open_ready_details": [{"symbol": "NG=F", "composite": 0.62}],
    },
    "us_stocks_open": {
      "auto_entry_queued": True,
      "open_ready_symbols": ["AAPL"],
    },
  }
  enriched = gate_prep_status._enrich_prep_with_session_events(session_prep, next_session_events)
  assert enriched["commodities"]["auto_entry_queued"] is True
  assert enriched["commodities"]["composite_floor"] == 0.42
  assert enriched["commodities"]["open_ready_symbols"] == ["NG=F", "CL=F"]
  assert enriched["stocks_futures"]["auto_entry_queued"] is True
  assert enriched["stocks_futures"]["open_ready_symbols"] == ["AAPL"]
