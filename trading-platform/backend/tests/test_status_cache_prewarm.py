from unittest.mock import patch

from app.engines.gate_entry_guard import status_cache_prewarm_active


def test_status_cache_prewarm_active_during_cme_weekend():
  with patch(
    "app.engines.gate_entry_guard.commodities_futures_weekend_closed",
    return_value=True,
  ):
    assert status_cache_prewarm_active() is True


def test_status_cache_prewarm_active_during_stocks_prep():
  with patch(
    "app.engines.gate_entry_guard.commodities_futures_weekend_closed",
    return_value=False,
  ):
    with patch(
      "app.engines.gate_entry_guard.stocks_session_info",
      return_value={"in_session": False, "minutes_until_open": 600},
    ):
      assert status_cache_prewarm_active() is True


def test_status_cache_prewarm_inactive_outside_prep_windows():
  with patch(
    "app.engines.gate_entry_guard.commodities_futures_weekend_closed",
    return_value=False,
  ):
    with patch(
      "app.engines.gate_entry_guard.stocks_session_info",
      return_value={"in_session": False, "minutes_until_open": 5000},
    ):
      assert status_cache_prewarm_active() is False
