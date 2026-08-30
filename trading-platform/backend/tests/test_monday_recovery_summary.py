"""Tests for cross-bot Monday recovery summary."""

from unittest.mock import AsyncMock, patch

import pytest

from app.engines.scan_preview import (
  build_monday_recovery_summary,
  clear_monday_recovery_cache,
)


@pytest.fixture(autouse=True)
def _reset_monday_recovery_cache():
  clear_monday_recovery_cache()
  yield
  clear_monday_recovery_cache()


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
              "monday_gate_skip_ready": True,
              "direction": "buy",
              "macd": "bullish",
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
              "monday_gate_skip_ready": True,
              "direction": "buy",
              "macd": "bullish",
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
  assert result["open_ready"][0]["minutes_until_open"] == 120
  assert result["open_ready"][0]["monday_gate_skip_ready"] is True
  assert result["open_ready"][0]["direction"] == "buy"
  assert result["open_ready"][0]["macd"] == "bullish"
  assert result["open_ready"][1]["minutes_until_open"] == 3000
  assert result["open_ready"][1]["monday_gate_skip_ready"] is True


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


def test_build_monday_recovery_summary_uses_short_ttl_cache():
  async def _run():
    session = AsyncMock()
    preview = AsyncMock(
      return_value={
        "recovery_candidates": [],
        "graduation_nudge": False,
        "symbols": [],
      }
    )
    with patch("app.engines.scan_preview.build_scan_preview", preview):
      first = await build_monday_recovery_summary(session)
      second = await build_monday_recovery_summary(session)
      return first, second, preview.await_count

  import asyncio

  first, second, call_count = asyncio.run(_run())
  assert first == second
  assert call_count == 2
