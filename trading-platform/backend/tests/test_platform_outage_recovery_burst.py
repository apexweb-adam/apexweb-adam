"""Tests for post-outage recovery burst scans on startup."""

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workers import scheduler as sched


@pytest.fixture(autouse=True)
def _reset_scheduler_outage_state():
  original_event = sched._startup_outage_event
  original_bots = sched.bots
  yield
  sched._startup_outage_event = original_event
  sched.bots = original_bots


@contextmanager
def _mock_scheduler_session(*, prep_state: dict | None = None):
  mock_session = AsyncMock()
  mock_cm = AsyncMock()
  mock_cm.__aenter__.return_value = mock_session
  mock_cm.__aexit__.return_value = None
  prep = prep_state if prep_state is not None else {}
  with patch("app.workers.scheduler.SessionLocal", return_value=mock_cm):
    with patch(
      "app.engines.session_open_log.get_prep_phase_state",
      new_callable=AsyncMock,
      return_value=prep,
    ):
      yield mock_session


def test_run_post_outage_recovery_bursts_skips_without_startup_event():
  sched._startup_outage_event = None
  with patch(
    "app.engines.session_open_log.needs_session_open_burst_recovery",
    new_callable=AsyncMock,
  ) as mock_needs:
    import asyncio

    asyncio.run(sched.run_post_outage_recovery_bursts())
    mock_needs.assert_not_called()


def test_run_post_outage_recovery_bursts_scans_stocks_when_window_active():
  bot = MagicMock()
  bot.scan_and_trade = AsyncMock(return_value=[])

  sched._startup_outage_event = {"gap_minutes": 120}
  sched.bots = {"stocks_futures": bot}

  with patch(
    "app.engines.gate_entry_guard.stocks_session_info",
    return_value={"in_session": True, "minutes_since_open": 150},
  ):
    with patch(
      "app.engines.gate_entry_guard.commodities_session_info",
      return_value={"in_session": False},
    ):
      with patch(
        "app.engines.session_open_log.needs_session_open_burst_recovery",
        new_callable=AsyncMock,
        return_value=True,
      ):
        with patch(
          "app.engines.session_open_log.platform_outage_burst_recovery_active",
          new_callable=AsyncMock,
          return_value=True,
        ):
          with _mock_scheduler_session():
            with patch(
              "app.ws_manager.push_live_update",
              new_callable=AsyncMock,
            ):
              import asyncio

              asyncio.run(sched.run_post_outage_recovery_bursts())

  bot.scan_and_trade.assert_awaited_once()
  assert bot._session_open_outage_recovery is False


def test_run_post_outage_recovery_bursts_scans_crypto_when_held():
  crypto_bot = MagicMock()
  crypto_bot.scan_and_trade = AsyncMock(return_value=[])

  sched._startup_outage_event = {
    "gap_minutes": 90,
    "held_open_positions": [
      {"bot_type": "crypto", "symbol": "BTC-USD"},
      {"bot_type": "stocks_futures", "symbol": "AAPL"},
    ],
  }
  sched.bots = {"crypto": crypto_bot}

  with patch(
    "app.engines.gate_entry_guard.stocks_session_info",
    return_value={"in_session": False},
  ):
    with patch(
      "app.engines.gate_entry_guard.commodities_session_info",
      return_value={"in_session": False},
    ):
      with patch(
        "app.ws_manager.push_live_update",
        new_callable=AsyncMock,
      ) as mock_push:
        with _mock_scheduler_session():
          import asyncio

          asyncio.run(sched.run_post_outage_recovery_bursts())

  crypto_bot.scan_and_trade.assert_awaited_once()
  mock_push.assert_awaited_once()


def test_run_post_outage_recovery_bursts_skips_crypto_without_held():
  crypto_bot = MagicMock()
  crypto_bot.scan_and_trade = AsyncMock(return_value=[])

  sched._startup_outage_event = {"gap_minutes": 90, "held_open_positions": []}
  sched.bots = {"crypto": crypto_bot}

  with patch(
    "app.engines.gate_entry_guard.stocks_session_info",
    return_value={"in_session": False},
  ):
    with patch(
      "app.engines.gate_entry_guard.commodities_session_info",
      return_value={"in_session": False},
    ):
      with patch(
        "app.ws_manager.push_live_update",
        new_callable=AsyncMock,
      ) as mock_push:
        import asyncio

        asyncio.run(sched.run_post_outage_recovery_bursts())

  crypto_bot.scan_and_trade.assert_not_called()
  mock_push.assert_not_called()


def test_run_post_outage_recovery_bursts_scans_commodities_when_held():
  commodities_bot = MagicMock()
  commodities_bot.scan_and_trade = AsyncMock(return_value=[])

  sched._startup_outage_event = {
    "gap_minutes": 90,
    "held_open_positions": [
      {"bot_type": "commodities", "symbol": "GC=F"},
      {"bot_type": "commodities", "symbol": "EURUSD=X"},
    ],
  }
  sched.bots = {"commodities": commodities_bot}

  with patch(
    "app.engines.gate_entry_guard.stocks_session_info",
    return_value={"in_session": False},
  ):
    with patch(
      "app.engines.gate_entry_guard.commodities_session_info",
      return_value={"in_session": False},
    ):
      with patch(
        "app.ws_manager.push_live_update",
        new_callable=AsyncMock,
      ) as mock_push:
        with _mock_scheduler_session():
          import asyncio

          asyncio.run(sched.run_post_outage_recovery_bursts())

  commodities_bot.scan_and_trade.assert_awaited_once()
  mock_push.assert_awaited_once()


def test_run_post_outage_recovery_bursts_prioritizes_stocks_when_us_queued():
  stocks_bot = MagicMock()
  stocks_bot.scan_and_trade = AsyncMock(return_value=[])
  commodities_bot = MagicMock()
  commodities_bot.scan_and_trade = AsyncMock(return_value=[])

  sched._startup_outage_event = {
    "gap_minutes": 120,
    "us_open_ready_symbols": ["AAPL"],
  }
  sched.bots = {"stocks_futures": stocks_bot, "commodities": commodities_bot}
  call_order: list[str] = []

  async def track_stocks():
    call_order.append("stocks_futures")
    return []

  async def track_commodities():
    call_order.append("commodities")
    return []

  stocks_bot.scan_and_trade = AsyncMock(side_effect=track_stocks)
  commodities_bot.scan_and_trade = AsyncMock(side_effect=track_commodities)

  session_info = {"in_session": True, "minutes_since_open": 150, "session_open_utc": "2026-08-31T13:30:00"}
  with patch(
    "app.engines.gate_entry_guard.stocks_session_info",
    return_value=session_info,
  ):
    with patch(
      "app.engines.gate_entry_guard.commodities_session_info",
      return_value=session_info,
    ):
      with patch(
        "app.engines.session_open_log.needs_session_open_burst_recovery",
        new_callable=AsyncMock,
        return_value=True,
      ):
        with patch(
          "app.engines.session_open_log.platform_outage_burst_recovery_active",
          new_callable=AsyncMock,
          return_value=True,
        ):
          with _mock_scheduler_session():
            with patch(
              "app.ws_manager.push_live_update",
              new_callable=AsyncMock,
            ):
              import asyncio

              asyncio.run(sched.run_post_outage_recovery_bursts())

  assert call_order == ["stocks_futures", "commodities"]


def test_run_post_outage_recovery_bursts_logs_outage_recovery_scan_for_us_queued():
  stocks_bot = MagicMock()
  stocks_bot.scan_and_trade = AsyncMock(return_value=[])

  sched._startup_outage_event = {
    "gap_minutes": 120,
    "us_open_ready_symbols": ["AAPL"],
    "held_open_positions": [],
  }
  sched.bots = {"stocks_futures": stocks_bot}
  recorded: list[dict] = []

  async def capture_event(session, **kwargs):
    recorded.append(kwargs)
    return kwargs

  with patch(
    "app.engines.gate_entry_guard.stocks_session_info",
    return_value={"in_session": False},
  ):
    with patch(
      "app.engines.gate_entry_guard.commodities_session_info",
      return_value={"in_session": False},
    ):
      with patch(
        "app.engines.session_open_log.record_session_open_event",
        new_callable=AsyncMock,
        side_effect=capture_event,
      ):
        with _mock_scheduler_session():
          with patch(
            "app.ws_manager.push_live_update",
            new_callable=AsyncMock,
          ):
            import asyncio

            asyncio.run(sched.run_post_outage_recovery_bursts())

  stocks_bot.scan_and_trade.assert_awaited_once()
  assert any(
    row.get("event_type") == "outage_recovery_scan" and row.get("symbols") == ["AAPL"]
    for row in recorded
  )


def test_run_post_outage_recovery_bursts_merges_current_prep_open_ready():
  """After startup prep jobs, merge live prep open-ready with outage snapshot."""
  stocks_bot = MagicMock()
  stocks_bot.scan_and_trade = AsyncMock(return_value=[])

  sched._startup_outage_event = {
    "gap_minutes": 120,
    "us_open_ready_symbols": [],
    "cme_open_ready_symbols": [],
    "held_open_positions": [],
  }
  sched.bots = {"stocks_futures": stocks_bot}
  recorded: list[dict] = []

  async def capture_event(session, **kwargs):
    recorded.append(kwargs)
    return kwargs

  with patch(
    "app.engines.gate_entry_guard.stocks_session_info",
    return_value={"in_session": False},
  ):
    with patch(
      "app.engines.gate_entry_guard.commodities_session_info",
      return_value={"in_session": False},
    ):
      with patch(
        "app.engines.session_open_log.record_session_open_event",
        new_callable=AsyncMock,
        side_effect=capture_event,
      ):
        with _mock_scheduler_session(
          prep_state={"us_stocks_open": {"open_ready_symbols": ["AAPL"]}}
        ):
          with patch(
            "app.ws_manager.push_live_update",
            new_callable=AsyncMock,
          ):
            import asyncio

            asyncio.run(sched.run_post_outage_recovery_bursts())

  stocks_bot.scan_and_trade.assert_awaited_once()
  assert any(
    row.get("event_type") == "outage_recovery_scan" and row.get("symbols") == ["AAPL"]
    for row in recorded
  )
