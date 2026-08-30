"""Tests for parallel /crm landing context loader."""

import asyncio
from unittest.mock import AsyncMock, patch

from app.engines import crm_landing_context


def test_build_crm_landing_context_runs_parallel_path_on_postgres():
  expected = {
    "gate": {"recommendation": "hold"},
    "per_bot": {},
    "monday_recovery": {},
    "learning": {},
    "content_study": {},
    "intel_sources": [],
    "live_snapshot": {"positions": []},
    "integrations": {},
    "session_open_events": [],
    "cme_checklist": None,
    "us_stocks_checklist": None,
  }

  with patch("app.database.is_postgres", return_value=True):
    with patch.object(
      crm_landing_context,
      "_build_crm_landing_context_parallel",
      AsyncMock(return_value=expected),
    ) as parallel:
      with patch.object(
        crm_landing_context,
        "_build_crm_landing_context_sequential",
        AsyncMock(),
      ) as sequential:
        result = asyncio.run(crm_landing_context.build_crm_landing_context())

  parallel.assert_called_once()
  sequential.assert_not_called()
  assert result == expected


def test_build_crm_landing_context_uses_sequential_on_sqlite():
  with patch("app.database.is_postgres", return_value=False):
    with patch.object(
      crm_landing_context,
      "_build_crm_landing_context_sequential",
      AsyncMock(return_value={"gate": {}, "per_bot": {}, "session_open_events": []}),
    ) as sequential:
      with patch.object(crm_landing_context, "_build_crm_landing_context_parallel", AsyncMock()) as parallel:
        asyncio.run(crm_landing_context.build_crm_landing_context())

  sequential.assert_called_once()
  parallel.assert_not_called()
