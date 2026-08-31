"""Tests for cross-bot Monday recovery summary."""

from unittest.mock import AsyncMock, patch

import pytest

from app.engines.scan_preview import (
  _monday_recovery_cache_ttl_seconds,
  build_monday_recovery_summary,
  clear_monday_recovery_cache,
)


@pytest.fixture(autouse=True)
def _reset_monday_recovery_cache():
  clear_monday_recovery_cache()
  yield
  clear_monday_recovery_cache()


@pytest.fixture(autouse=True)
def _mock_prep_phase_state():
  with patch(
    "app.engines.session_open_log.get_prep_phase_state",
    new=AsyncMock(return_value={}),
  ):
    yield


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


def test_build_monday_recovery_summary_keeps_sticky_open_ready(weekend_commodities_session):
  async def _run():
    session = AsyncMock()

    async def fake_preview(_session, bot_type):
      if bot_type == "commodities":
        return {
          "recovery_candidates": [],
          "graduation_nudge": True,
          "shadow_mode": False,
          "session": {"mode": "weekend_closed", "minutes_until_open": 900},
          "symbols": [
            {
              "symbol": "NG=F",
              "composite": 0.64,
              "monday_open_ready": True,
              "monday_gate_skip_ready": True,
              "direction": "buy",
              "macd": "bullish",
              "blockers": ["weekend_futures_closed"],
            },
            {
              "symbol": "CL=F",
              "composite": 0.41,
              "monday_open_ready": False,
              "monday_gate_skip_ready": True,
              "direction": "buy",
              "macd": "bullish",
              "blockers": ["weekend_futures_closed"],
            },
          ],
          "open_ready_candidates": ["NG=F"],
        }
      return {
        "recovery_candidates": [],
        "stocks_trade_count_nudge": False,
        "symbols": [],
      }

    with patch(
      "app.engines.scan_preview.build_scan_preview",
      side_effect=fake_preview,
    ):
      with patch(
        "app.engines.session_open_log.get_prep_phase_state",
        new=AsyncMock(
          return_value={
            "cme_reopen": {"open_ready_symbols": ["NG=F", "CL=F"]},
          }
        ),
      ):
        return await build_monday_recovery_summary(session)

  import asyncio

  result = asyncio.run(_run())
  symbols = [row["symbol"] for row in result["open_ready"] if row["bot_type"] == "commodities"]
  assert symbols == ["NG=F", "CL=F"]
  clf = next(row for row in result["open_ready"] if row["symbol"] == "CL=F")
  assert clf.get("sticky_queue") is True


def test_build_monday_recovery_summary_keeps_sticky_stocks_open_ready():
  from app.engines.gate_entry_guard import STOCKS_PROVEN_RECOVERY_MIN_COMPOSITE

  async def _run():
    session = AsyncMock()

    async def fake_preview(_session, bot_type):
      if bot_type == "stocks_futures":
        return {
          "recovery_candidates": [],
          "stocks_trade_count_nudge": False,
          "graduation_nudge": False,
          "shadow_mode": True,
          "shadow_bot_wr": 0.6,
          "total_trades": 40,
          "proven_winners": ["AAPL", "MSFT"],
          "session": {"mode": "outside_session", "minutes_until_open": 1800},
          "symbols": [
            {
              "symbol": "AAPL",
              "composite": 0.5,
              "monday_open_ready": True,
              "monday_gate_skip_ready": True,
              "direction": "buy",
              "macd": "bullish",
              "blockers": ["gate_skip"],
            },
            {
              "symbol": "MSFT",
              "composite": STOCKS_PROVEN_RECOVERY_MIN_COMPOSITE - 0.01,
              "monday_open_ready": False,
              "monday_gate_skip_ready": True,
              "direction": "buy",
              "macd": "bullish",
              "blockers": ["gate_skip"],
            },
          ],
        }
      return {
        "recovery_candidates": [],
        "graduation_nudge": False,
        "shadow_mode": False,
        "symbols": [],
      }

    with patch(
      "app.engines.scan_preview.build_scan_preview",
      side_effect=fake_preview,
    ):
      with patch(
        "app.engines.session_open_log.get_prep_phase_state",
        new=AsyncMock(
          return_value={
            "us_stocks_open": {"open_ready_symbols": ["AAPL", "MSFT"]},
          }
        ),
      ):
        return await build_monday_recovery_summary(session)

  import asyncio

  result = asyncio.run(_run())
  stocks_rows = [row for row in result["open_ready"] if row["bot_type"] == "stocks_futures"]
  symbols = [row["symbol"] for row in stocks_rows]
  assert symbols == ["AAPL", "MSFT"]
  msft = next(row for row in stocks_rows if row["symbol"] == "MSFT")
  assert msft.get("sticky_queue") is True


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


def test_monday_recovery_cache_ttl_extended_during_us_stocks_prep():
  with patch(
    "app.engines.gate_entry_guard.commodities_futures_weekend_closed",
    return_value=False,
  ):
    with patch(
      "app.engines.gate_entry_guard.status_cache_prewarm_active",
      return_value=True,
    ):
      assert _monday_recovery_cache_ttl_seconds() == 60


def test_build_monday_recovery_summary_serves_stale_while_rebuild_in_progress():
  async def _run():
    session = AsyncMock()
    payload = {"recovery_candidates": [], "bots": {}, "open_ready": ["AAPL"]}
    build_started = asyncio.Event()
    release_build = asyncio.Event()
    build_count = 0

    async def slow_build(_session):
      nonlocal build_count
      build_count += 1
      if build_count == 1:
        return dict(payload)
      build_started.set()
      await release_build.wait()
      return {**payload, "open_ready": ["AAPL", "NVDA"]}

    with patch(
      "app.engines.scan_preview._build_monday_recovery_summary",
      new=AsyncMock(side_effect=slow_build),
    ) as builder:
      await build_monday_recovery_summary(session)
      scan_preview._monday_recovery_cached_at = 0.0
      rebuild_task = asyncio.create_task(build_monday_recovery_summary(session))
      await build_started.wait()
      stale = await build_monday_recovery_summary(session)
      release_build.set()
      rebuilt = await rebuild_task

    assert builder.await_count == 2
    assert stale.get("recovery_cache_stale") is True
    assert stale["open_ready"] == ["AAPL"]
    assert rebuilt["open_ready"] == ["AAPL", "NVDA"]

  import asyncio

  from app.engines import scan_preview

  asyncio.run(_run())


def test_monday_recovery_cache_ttl_extended_during_cme_weekend():
  with patch(
    "app.engines.gate_entry_guard.commodities_futures_weekend_closed",
    return_value=True,
  ):
    with patch(
      "app.engines.gate_entry_guard.commodities_session_info",
      return_value={"minutes_until_open": 500},
    ):
      assert _monday_recovery_cache_ttl_seconds() == 60


def test_monday_recovery_cache_ttl_short_during_cme_prep_watch():
  with patch(
    "app.engines.gate_entry_guard.commodities_futures_weekend_closed",
    return_value=True,
  ):
    with patch(
      "app.engines.gate_entry_guard.commodities_session_info",
      return_value={"minutes_until_open": 120},
    ):
      assert _monday_recovery_cache_ttl_seconds() == 15


def test_monday_recovery_cache_ttl_short_during_us_stocks_imminent_window():
  with patch(
    "app.engines.gate_entry_guard.commodities_futures_weekend_closed",
    return_value=False,
  ):
    with patch(
      "app.engines.gate_entry_guard.stocks_session_info",
      return_value={"in_session": False, "minutes_until_open": 20},
    ):
      assert _monday_recovery_cache_ttl_seconds() == 15


def test_build_monday_recovery_summary_runs_scan_previews_in_parallel():
  async def _run():
    session = AsyncMock()
    call_order: list[str] = []

    async def fake_preview(_session, bot_type):
      call_order.append(bot_type)
      return {
        "recovery_candidates": [],
        "graduation_nudge": bot_type == "commodities",
        "stocks_trade_count_nudge": bot_type == "stocks_futures",
        "symbols": [],
      }

    with patch("app.engines.scan_preview.build_scan_preview", side_effect=fake_preview):
      with patch("app.database.SessionLocal") as session_local:
        bot_session = AsyncMock()
        session_local.return_value.__aenter__.return_value = bot_session
        result = await build_monday_recovery_summary(session)
        return result, call_order

  import asyncio

  result, call_order = asyncio.run(_run())
  assert set(call_order) == {"commodities", "stocks_futures"}
  assert result["commodities_graduation_nudge"] is True


def test_monday_recovery_commodities_verification_nudge():
  async def _run():
    session = AsyncMock()

    async def fake_preview(_session, bot_type):
      if bot_type == "commodities":
        return {
          "recovery_candidates": ["CL=F"],
          "graduation_nudge": False,
          "commodities_verification_trade_count_nudge": True,
          "symbols": [
            {
              "symbol": "CL=F",
              "composite": 0.43,
              "recovery_ready": True,
              "blockers": ["volume"],
            },
          ],
        }
      return {"recovery_candidates": [], "symbols": []}

    with patch("app.engines.scan_preview.build_scan_preview", side_effect=fake_preview):
      return await build_monday_recovery_summary(session)

  import asyncio

  result = asyncio.run(_run())
  assert result["commodities_verification_trade_count_nudge"] is True
  assert result["commodities_graduation_nudge"] is True
  assert "commodities" in result["bots"]
