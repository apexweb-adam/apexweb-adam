"""Tests for commodities pre-CME-session TradingView prep."""

from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

from app.workers.scheduler import commodities_pre_session_prep_job


@contextmanager
def _mock_scheduler_session():
  mock_session = AsyncMock()
  mock_cm = AsyncMock()
  mock_cm.__aenter__.return_value = mock_session
  mock_cm.__aexit__.return_value = None
  with patch("app.workers.scheduler.SessionLocal", return_value=mock_cm):
    yield mock_session


def test_commodities_prep_skips_when_in_session():
  with patch(
    "app.engines.gate_entry_guard.commodities_session_info",
    return_value={"in_session": True, "minutes_until_open": 0},
  ):
    with patch(
      "app.engines.integration_signals.refresh_tradingview_signals",
      new_callable=AsyncMock,
    ) as mock_refresh:
      import asyncio

      asyncio.run(commodities_pre_session_prep_job())
      mock_refresh.assert_not_called()


def test_commodities_prep_refreshes_within_prep_window():
  with patch(
    "app.engines.gate_entry_guard.commodities_session_info",
    return_value={
      "in_session": False,
      "minutes_until_open": 60,
      "mode": "pre_session",
    },
  ):
    with patch(
      "app.engines.gate_entry_guard.get_proven_winner_symbols",
      new_callable=AsyncMock,
      return_value=frozenset({"CL=F"}),
    ):
      with patch(
        "app.engines.gate_entry_guard.get_chronic_loser_symbols",
        new_callable=AsyncMock,
        return_value=frozenset(),
      ):
        with patch(
          "app.engines.integration_signals.refresh_tradingview_signals",
          new_callable=AsyncMock,
          return_value=["CL=F", "SI=F"],
        ) as mock_refresh:
          with patch("app.ws_manager.push_live_update", new_callable=AsyncMock):
            with patch(
              "app.engines.profitability_gate.ProfitabilityGate.evaluate_per_bot",
              new_callable=AsyncMock,
              return_value={"commodities": {"win_rate": 0.44, "profit_factor": 1.2, "total_pnl": 10}},
            ):
              with patch(
                "app.engines.gate_entry_guard.in_shadow_graduation_nudge",
                return_value=False,
              ):
                with _mock_scheduler_session():
                  import asyncio

                  asyncio.run(commodities_pre_session_prep_job())
            mock_refresh.assert_called_once()
            symbols = mock_refresh.call_args[0][1]
            assert "CL=F" in symbols
            assert "SI=F" in symbols


def test_commodities_prep_includes_chronic_recovery_futures():
  with patch(
    "app.engines.gate_entry_guard.commodities_session_info",
    return_value={
      "in_session": False,
      "minutes_until_open": 45,
      "mode": "pre_session",
    },
  ):
    with patch(
      "app.engines.gate_entry_guard.get_proven_winner_symbols",
      new_callable=AsyncMock,
      return_value=frozenset(),
    ):
      with patch(
        "app.engines.gate_entry_guard.get_chronic_loser_symbols",
        new_callable=AsyncMock,
        return_value=frozenset({"SI=F", "XAUUSDT"}),
      ):
        with patch(
          "app.engines.integration_signals.refresh_tradingview_signals",
          new_callable=AsyncMock,
          return_value=["SI=F"],
        ) as mock_refresh:
          with patch("app.ws_manager.push_live_update", new_callable=AsyncMock):
            with patch(
              "app.engines.profitability_gate.ProfitabilityGate.evaluate_per_bot",
              new_callable=AsyncMock,
              return_value={"commodities": {"win_rate": 0.44, "profit_factor": 1.2, "total_pnl": 10}},
            ):
              with patch(
                "app.engines.gate_entry_guard.in_shadow_graduation_nudge",
                return_value=False,
              ):
                with _mock_scheduler_session():
                  import asyncio

                  asyncio.run(commodities_pre_session_prep_job())
            symbols = mock_refresh.call_args[0][1]
            assert "SI=F" in symbols
            assert "XAUUSDT" not in symbols


def test_commodities_prep_refreshes_within_graduation_extended_window():
  with patch(
    "app.engines.gate_entry_guard.commodities_session_info",
    return_value={
      "in_session": False,
      "minutes_until_open": 3000,
      "mode": "weekend_closed",
    },
  ):
    with patch(
      "app.engines.gate_entry_guard.get_proven_winner_symbols",
      new_callable=AsyncMock,
      return_value=frozenset({"CL=F"}),
    ):
      with patch(
        "app.engines.gate_entry_guard.get_chronic_loser_symbols",
        new_callable=AsyncMock,
        return_value=frozenset({"SI=F"}),
      ):
        with patch(
          "app.engines.integration_signals.refresh_tradingview_signals",
          new_callable=AsyncMock,
          return_value=["SI=F"],
        ) as mock_refresh:
          with patch("app.ws_manager.push_live_update", new_callable=AsyncMock):
            with patch(
              "app.engines.profitability_gate.ProfitabilityGate.evaluate_per_bot",
              new_callable=AsyncMock,
              return_value={"commodities": {"win_rate": 0.44, "profit_factor": 1.2, "total_pnl": 10}},
            ):
              with patch(
                "app.engines.gate_entry_guard.in_shadow_graduation_nudge",
                return_value=True,
              ):
                with _mock_scheduler_session():
                  import asyncio

                  asyncio.run(commodities_pre_session_prep_job())
            mock_refresh.assert_called_once()
            symbols = mock_refresh.call_args[0][1]
            assert symbols[0] == "NG=F"
            assert "SI=F" in symbols


def test_commodities_cme_reopen_wake_refreshes_pre_open():
  from app.workers.scheduler import commodities_cme_reopen_wake_job

  with patch(
    "app.engines.gate_entry_guard.commodities_session_info",
    return_value={
      "in_session": False,
      "minutes_until_open": 2,
      "minutes_since_open": 0,
      "mode": "pre_session",
    },
  ):
    with patch(
      "app.engines.gate_entry_guard.get_proven_winner_symbols",
      new_callable=AsyncMock,
      return_value=frozenset({"CL=F"}),
    ):
      with patch(
        "app.engines.gate_entry_guard.get_chronic_loser_symbols",
        new_callable=AsyncMock,
        return_value=frozenset({"SI=F"}),
      ):
        with patch(
          "app.engines.integration_signals.refresh_tradingview_signals",
          new_callable=AsyncMock,
          return_value=["NG=F"],
        ) as mock_refresh:
          with patch("app.ws_manager.push_live_update", new_callable=AsyncMock) as mock_push:
            with patch(
              "app.engines.scan_preview.build_monday_recovery_summary",
              new_callable=AsyncMock,
              return_value={"open_ready": []},
            ):
              with patch(
                "app.engines.profitability_gate.ProfitabilityGate.evaluate_per_bot",
                new_callable=AsyncMock,
                return_value={"commodities": {"win_rate": 0.5, "profit_factor": 1.2, "total_pnl": 20}},
              ):
                with patch(
                  "app.engines.gate_entry_guard.in_shadow_graduation_nudge",
                  return_value=True,
                ):
                  with _mock_scheduler_session():
                    import asyncio

                    asyncio.run(commodities_cme_reopen_wake_job())
            mock_refresh.assert_called_once()
            symbols = mock_refresh.call_args[0][1]
            assert symbols[0] == "NG=F"
            assert mock_refresh.call_args[1]["force_refresh"] is True
            mock_push.assert_called_once()


def test_commodities_cme_reopen_wake_runs_for_open_ready_without_graduation_nudge():
  from app.workers.scheduler import commodities_cme_reopen_wake_job

  with patch(
    "app.engines.gate_entry_guard.commodities_session_info",
    return_value={
      "in_session": False,
      "minutes_until_open": 2,
      "minutes_since_open": 0,
      "mode": "pre_session",
    },
  ):
    with patch(
      "app.engines.gate_entry_guard.get_proven_winner_symbols",
      new_callable=AsyncMock,
      return_value=frozenset(),
    ):
      with patch(
        "app.engines.gate_entry_guard.get_chronic_loser_symbols",
        new_callable=AsyncMock,
        return_value=frozenset(),
      ):
        with patch(
          "app.engines.scan_preview.build_monday_recovery_summary",
          new_callable=AsyncMock,
          return_value={
            "open_ready": [
              {"bot_type": "commodities", "symbol": "NG=F", "composite": 0.46},
            ],
          },
        ):
          with patch(
            "app.engines.integration_signals.refresh_tradingview_signals",
            new_callable=AsyncMock,
            return_value=["NG=F"],
          ) as mock_refresh:
            with patch("app.ws_manager.push_live_update", new_callable=AsyncMock):
              with patch(
                "app.engines.profitability_gate.ProfitabilityGate.evaluate_per_bot",
                new_callable=AsyncMock,
                return_value={"commodities": {"win_rate": 0.40, "profit_factor": 1.0, "total_pnl": 5}},
              ):
                with patch(
                  "app.engines.gate_entry_guard.in_shadow_graduation_nudge",
                  return_value=False,
                ):
                  with _mock_scheduler_session():
                    import asyncio

                    asyncio.run(commodities_cme_reopen_wake_job())
            mock_refresh.assert_called_once()
            assert "NG=F" in mock_refresh.call_args[0][1]


def test_commodities_cme_reopen_wake_skips_outside_window():
  from app.workers.scheduler import commodities_cme_reopen_wake_job

  with patch(
    "app.engines.gate_entry_guard.commodities_session_info",
    return_value={
      "in_session": False,
      "minutes_until_open": 30,
      "minutes_since_open": 0,
    },
  ):
    with patch(
      "app.engines.integration_signals.refresh_tradingview_signals",
      new_callable=AsyncMock,
    ) as mock_refresh:
      import asyncio

      asyncio.run(commodities_cme_reopen_wake_job())
      mock_refresh.assert_not_called()
