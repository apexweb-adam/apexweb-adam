"""Tests for cross-bot Monday recovery summary."""

from unittest.mock import AsyncMock, patch

from app.engines.scan_preview import build_monday_recovery_summary


def test_build_monday_recovery_summary_aggregates_bots():
  async def _run():
    session = AsyncMock()

    async def fake_preview(_session, bot_type):
      if bot_type == "commodities":
        return {
          "recovery_candidates": ["SI=F"],
          "graduation_nudge": True,
          "session": {"mode": "weekend_closed", "minutes_until_open": 120},
          "symbols": [
            {
              "symbol": "SI=F",
              "composite": 0.518,
              "recovery_ready": True,
              "monday_open_ready": False,
              "blockers": ["weekend_futures_closed", "signal_sell"],
            },
            {
              "symbol": "NG=F",
              "composite": 0.644,
              "recovery_ready": False,
              "monday_open_ready": True,
              "blockers": ["weekend_futures_closed"],
            },
          ],
          "open_ready_candidates": ["NG=F"],
        }
      if bot_type == "stocks_futures":
        return {
          "recovery_candidates": ["NVDA"],
          "stocks_trade_count_nudge": True,
          "session": {"mode": "outside_session", "minutes_until_open": 3000},
          "symbols": [
            {
              "symbol": "NVDA",
              "composite": 0.414,
              "recovery_ready": True,
              "monday_open_ready": False,
              "blockers": ["gate_skip", "signal_sell"],
            },
            {
              "symbol": "AAPL",
              "composite": 0.467,
              "recovery_ready": False,
              "monday_open_ready": True,
              "blockers": ["stocks_session_closed"],
            },
          ],
          "open_ready_candidates": ["AAPL"],
        }
      return {"error": "unknown"}

    with patch(
      "app.engines.scan_preview.build_scan_preview",
      side_effect=fake_preview,
    ):
      return await build_monday_recovery_summary(session)

  import asyncio

  result = asyncio.run(_run())
  assert result["recovery_candidates"] == ["SI=F", "NVDA"]
  assert result["stocks_trade_count_nudge"] is True
  assert result["commodities_graduation_nudge"] is True
  assert len(result["all"]) == 2
  assert "commodities" in result["bots"]
  assert "stocks_futures" in result["bots"]
  assert result["bots"]["commodities"]["recovery_candidates"] == ["SI=F"]
  assert result["open_ready_candidates"] == ["NG=F", "AAPL"]
  assert len(result["open_ready"]) == 2
  assert result["open_ready"][0]["symbol"] == "NG=F"


def test_build_monday_recovery_summary_nudge_without_recovery_candidates():
  async def _run():
    session = AsyncMock()

    async def fake_preview(_session, bot_type):
      if bot_type == "commodities":
        return {
          "recovery_candidates": [],
          "graduation_nudge": False,
          "symbols": [],
        }
      if bot_type == "stocks_futures":
        return {
          "recovery_candidates": [],
          "stocks_trade_count_nudge": True,
          "graduation_nudge": False,
          "session": {"mode": "outside_session"},
          "symbols": [],
        }
      return {"error": "unknown"}

    with patch(
      "app.engines.scan_preview.build_scan_preview",
      side_effect=fake_preview,
    ):
      return await build_monday_recovery_summary(session)

  import asyncio

  result = asyncio.run(_run())
  assert result["recovery_candidates"] == []
  assert result["stocks_trade_count_nudge"] is True
  assert "stocks_futures" in result["bots"]


def test_build_monday_recovery_summary_empty_when_no_candidates():
  async def _run():
    session = AsyncMock()
    with patch(
      "app.engines.scan_preview.build_scan_preview",
      new=AsyncMock(return_value={"recovery_candidates": [], "symbols": []}),
    ):
      return await build_monday_recovery_summary(session)

  import asyncio

  result = asyncio.run(_run())
  assert result["recovery_candidates"] == []
  assert result["bots"] == {}
