"""Tests for post-outage recovery burst scans on startup."""

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from app.workers import scheduler as sched


@contextmanager
def _mock_scheduler_session():
  mock_session = AsyncMock()
  mock_cm = AsyncMock()
  mock_cm.__aenter__.return_value = mock_session
  mock_cm.__aexit__.return_value = None
  with patch("app.workers.scheduler.SessionLocal", return_value=mock_cm):
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
            import asyncio

            asyncio.run(sched.run_post_outage_recovery_bursts())

  bot.scan_and_trade.assert_awaited_once()
  assert bot._session_open_outage_recovery is False
