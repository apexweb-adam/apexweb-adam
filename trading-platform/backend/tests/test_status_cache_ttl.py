from unittest.mock import patch

from app.engines.gate_entry_guard import status_cache_ttl_seconds


def test_status_cache_ttl_default_outside_prewarm():
  with patch(
    "app.engines.gate_entry_guard.commodities_futures_weekend_closed",
    return_value=False,
  ):
    with patch(
      "app.engines.gate_entry_guard.stocks_session_info",
      return_value={"in_session": False, "minutes_until_open": 120},
    ):
      with patch(
        "app.engines.gate_entry_guard.status_cache_prewarm_active",
        return_value=False,
      ):
        assert status_cache_ttl_seconds(default_ttl=45) == 45


def test_status_cache_ttl_prep_during_us_stocks_window():
  with patch(
    "app.engines.gate_entry_guard.commodities_futures_weekend_closed",
    return_value=False,
  ):
    with patch(
      "app.engines.gate_entry_guard.stocks_session_info",
      return_value={"in_session": False, "minutes_until_open": 120},
    ):
      with patch(
        "app.engines.gate_entry_guard.status_cache_prewarm_active",
        return_value=True,
      ):
        assert status_cache_ttl_seconds(default_ttl=45, prep_ttl=60) == 60


def test_status_cache_ttl_watch_during_cme_imminent_window():
  with patch(
    "app.engines.gate_entry_guard.commodities_futures_weekend_closed",
    return_value=True,
  ):
    with patch(
      "app.engines.gate_entry_guard.commodities_session_info",
      return_value={"minutes_until_open": 120},
    ):
      assert status_cache_ttl_seconds(default_ttl=45, prep_ttl=60, watch_ttl=15) == 15


def test_status_cache_ttl_watch_during_us_stocks_imminent_window():
  with patch(
    "app.engines.gate_entry_guard.commodities_futures_weekend_closed",
    return_value=False,
  ):
    with patch(
      "app.engines.gate_entry_guard.stocks_session_info",
      return_value={"in_session": False, "minutes_until_open": 20},
    ):
      assert status_cache_ttl_seconds(default_ttl=45, prep_ttl=60, watch_ttl=15) == 15


def test_status_cache_ttl_prep_outside_us_stocks_imminent_window():
  with patch(
    "app.engines.gate_entry_guard.commodities_futures_weekend_closed",
    return_value=False,
  ):
    with patch(
      "app.engines.gate_entry_guard.stocks_session_info",
      return_value={"in_session": False, "minutes_until_open": 120},
    ):
      with patch(
        "app.engines.gate_entry_guard.status_cache_prewarm_active",
        return_value=True,
      ):
        assert status_cache_ttl_seconds(default_ttl=45, prep_ttl=60, watch_ttl=15) == 60
