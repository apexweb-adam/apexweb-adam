"""Tests for scan preview diagnostics."""

from unittest.mock import AsyncMock, MagicMock, patch

from app.engines.scan_preview import build_scan_preview


def test_build_scan_preview_unknown_bot():
  async def _run():
    return await build_scan_preview(AsyncMock(), "invalid")

  import asyncio

  result = asyncio.run(_run())
  assert "error" in result


def test_build_scan_preview_commodities_structure():
  async def _run():
    session = AsyncMock()
    bot = MagicMock()
    bot.get_symbols = AsyncMock(return_value=["GC=F"])
    bot.fetch_price_data = AsyncMock(return_value=(100.0, None))
    bot.get_sentiment_detail = AsyncMock(return_value=(0.1, "reddit"))
    signal = MagicMock(
      score=0.3,
      direction="buy",
      macd_signal="bullish",
      volume_confirmed=True,
      reason="test",
    )
    bot.signal_engine.analyze = MagicMock(return_value=signal)
    bot.signal_engine.composite_score = MagicMock(return_value=0.35)

    with patch("app.engines.scan_preview.BOT_CLASSES", {"commodities": MagicMock(return_value=bot)}):
      with patch("app.engines.scan_preview.is_bot_paused", return_value=True):
        with patch("app.engines.scan_preview.PaperTradingEngine") as EngineCls:
          strategy = MagicMock()
          strategy.min_signal_score = 0.28
          strategy.min_sentiment_score = 0.0
          strategy.rsi_oversold = 26
          strategy.rsi_overbought = 70
          strategy.technical_weight = 0.3
          strategy.sentiment_weight = 0.5
          strategy.momentum_weight = 0.4
          engine = EngineCls.return_value
          engine.get_strategy = AsyncMock(return_value=strategy)
          engine.get_open_positions = AsyncMock(return_value=[])
          with patch("app.engines.scan_preview.ProfitabilityGate") as GateCls:
            GateCls.return_value.evaluate_per_bot = AsyncMock(
              return_value={"commodities": {"win_rate": 0.5}}
            )
            with patch(
              "app.engines.scan_preview.get_gate_entry_tightening",
              return_value=MagicMock(active=False, blocked_new_entries=frozenset()),
            ):
              with patch(
                "app.engines.scan_preview.get_gate_skip_symbols",
                return_value=frozenset(),
              ):
                with patch(
                  "app.engines.scan_preview.get_proven_winner_symbols",
                  return_value=frozenset({"GC=F"}),
                ):
                  with patch(
                    "app.engines.scan_preview.get_integration_boost",
                    return_value=(0.0, ""),
                  ):
                    with patch(
                      "app.engines.scan_preview.is_price_sane",
                      return_value=True,
                    ):
                      return await build_scan_preview(session, "commodities")

  import asyncio

  result = asyncio.run(_run())
  assert result["graduation_nudge"] is True
  assert result["shadow_mode"] is True
  assert len(result["symbols"]) == 1
  assert result["symbols"][0]["would_enter"] is True
