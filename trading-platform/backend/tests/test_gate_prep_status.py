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


def test_gate_prep_status_cache_ttl_extended_during_prewarm():
  with patch(
    "app.engines.gate_entry_guard.status_cache_prewarm_active",
    return_value=True,
  ):
    assert gate_prep_status._gate_prep_status_cache_ttl_seconds() == 60


def test_build_gate_prep_status_serves_stale_while_rebuild_in_progress():
  async def run():
    session = AsyncMock()
    payload = {"commodities": {"prep_phase": "extended"}, "next_session_events": {}}
    build_started = asyncio.Event()
    release_build = asyncio.Event()
    build_count = 0

    async def slow_build(_session):
      nonlocal build_count
      build_count += 1
      if build_count == 1:
        return dict(payload)
      build_started.set()
      await release_build.wait()
      return {**payload, "commodities": {"prep_phase": "imminent"}}

    with patch(
      "app.engines.gate_prep_status._build_gate_prep_status_uncached",
      new=AsyncMock(side_effect=slow_build),
    ) as builder:
      await gate_prep_status.build_gate_prep_status(session)
      gate_prep_status._gate_prep_cached_at = 0.0
      rebuild_task = asyncio.create_task(gate_prep_status.build_gate_prep_status(session))
      await build_started.wait()
      stale = await gate_prep_status.build_gate_prep_status(session)
      release_build.set()
      rebuilt = await rebuild_task

    assert builder.await_count == 2
    assert stale["prep_cache_stale"] is True
    assert stale["prep_cache_hit"] is False
    assert stale["commodities"]["prep_phase"] == "extended"
    assert rebuilt["commodities"]["prep_phase"] == "imminent"

  asyncio.run(run())


def test_gate_prep_status_cache_ttl_extended_during_cme_weekend():
  with patch(
    "app.engines.gate_entry_guard.commodities_futures_weekend_closed",
    return_value=True,
  ):
    assert gate_prep_status._gate_prep_status_cache_ttl_seconds() == 60


def test_gate_prep_status_cache_ttl_short_during_cme_prep_watch():
  with patch(
    "app.engines.gate_entry_guard.commodities_futures_weekend_closed",
    return_value=True,
  ):
    with patch(
      "app.engines.gate_entry_guard.commodities_session_info",
      return_value={"minutes_until_open": 120},
    ):
      assert gate_prep_status._gate_prep_status_cache_ttl_seconds() == 15


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


def test_enrich_prep_with_session_events_surfaces_cap_pressure():
  session_prep = {
    "commodities": {
      "prep_phase": "open",
      "open_count": 4,
      "effective_open_cap": 4,
      "cap_pressure_active": True,
    },
    "stocks_futures": {"prep_phase": "extended"},
  }
  next_session_events = {"cme_reopen": {}, "us_stocks_open": {}}
  enriched = gate_prep_status._enrich_prep_with_session_events(session_prep, next_session_events)
  assert enriched["commodities"]["open_count"] == 4
  assert enriched["commodities"]["effective_open_cap"] == 4
  assert enriched["commodities"]["cap_pressure_active"] is True
