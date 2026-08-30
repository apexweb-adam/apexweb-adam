"""Tests for parallel /crm landing context loader."""

import asyncio
from unittest.mock import AsyncMock, patch

from app.engines import crm_landing_context


def test_build_crm_landing_context_runs_loaders_in_parallel_on_postgres():
  gate = {"recommendation": "hold", "paused_bots": []}
  per_bot = {"crypto": {"paused": True}}
  monday = {"recovery_candidates": []}
  learning = {"reviews": []}
  content = {"recent": []}
  intel = []
  live = {"positions": []}
  integrations = {"tradingview": {}}
  events = [{"event_type": "open_ready"}]
  cme = {"ready": True}
  stocks = {"ready": False}

  with patch.object(crm_landing_context, "is_postgres", return_value=True):
    with patch.object(crm_landing_context, "asyncio") as mock_asyncio:
      mock_asyncio.gather = AsyncMock(
        return_value=[
          (gate, per_bot),
          monday,
          learning,
          content,
          intel,
          live,
          integrations,
          events,
          cme,
          stocks,
        ]
      )
      result = asyncio.run(crm_landing_context.build_crm_landing_context())

  mock_asyncio.gather.assert_called_once()
  assert len(mock_asyncio.gather.call_args[0]) == 10
  assert result["gate"] == gate
  assert result["per_bot"] == per_bot
  assert result["monday_recovery"] == monday
  assert result["session_open_events"] == events
  assert result["cme_checklist"] == cme
  assert result["us_stocks_checklist"] == stocks


def test_build_crm_landing_context_uses_sequential_on_sqlite():
  with patch.object(crm_landing_context, "is_postgres", return_value=False):
    with patch.object(
      crm_landing_context,
      "_build_crm_landing_context_sequential",
      AsyncMock(return_value={"gate": {}, "per_bot": {}, "session_open_events": []}),
    ) as sequential:
      with patch.object(crm_landing_context, "_build_crm_landing_context_parallel", AsyncMock()) as parallel:
        asyncio.run(crm_landing_context.build_crm_landing_context())

  sequential.assert_called_once()
  parallel.assert_not_called()


def test_build_crm_landing_context_coalesces_failed_session_open_events():
  gate = {"recommendation": "hold", "paused_bots": []}
  per_bot = {}

  with patch.object(crm_landing_context, "is_postgres", return_value=True):
    with patch.object(crm_landing_context, "asyncio") as mock_asyncio:
      mock_asyncio.gather = AsyncMock(
        return_value=[
          (gate, per_bot),
          {},
          {},
          {},
          [],
          {"positions": []},
          {},
          None,
          None,
          None,
        ]
      )
      result = asyncio.run(crm_landing_context.build_crm_landing_context())

  assert result["session_open_events"] == []
  assert result["cme_checklist"] is None
