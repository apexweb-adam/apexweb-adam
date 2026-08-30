"""Pytest configuration for backend unit tests."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure `app` package resolves when running from repo root or backend dir.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
  sys.path.insert(0, str(BACKEND_ROOT))

WEEKEND_COMMODITIES_SESSION = {
  "in_session": False,
  "minutes_until_open": 200,
  "minutes_since_open": 0,
  "mode": "weekend_closed",
  "session_open_utc": "2026-08-30T22:00:00",
}


@pytest.fixture
def weekend_commodities_session():
  """Pin commodities session to pre-CME reopen so Sunday-night CI stays stable."""
  with patch(
    "app.engines.gate_entry_guard.commodities_session_info",
    return_value=WEEKEND_COMMODITIES_SESSION,
  ):
    yield
