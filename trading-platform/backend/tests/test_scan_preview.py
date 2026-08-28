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
      rsi=50,
      rsi_divergence=None,
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
            GateCls.return_value.evaluate = AsyncMock(
              return_value={"live_trading_ready": False, "total_trades": 5, "win_rate": 0.6}
            )
            GateCls.return_value.evaluate_per_bot = AsyncMock(
              return_value={"commodities": {"win_rate": 0.5}}
            )
            with patch(
              "app.engines.scan_preview.get_gate_entry_tightening",
              return_value=MagicMock(active=False, blocked_new_entries=frozenset()),
            ):
              with patch(
                "app.engines.scan_preview.get_chronic_loser_symbols",
                new=AsyncMock(return_value=frozenset()),
              ):
                with patch(
                  "app.engines.scan_preview.get_hard_gate_skip_symbols",
                  new=AsyncMock(return_value=frozenset()),
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
                        with patch(
                          "app.engines.scan_preview.is_symbol_in_trade_cooldown",
                          new=AsyncMock(return_value=False),
                        ):
                          return await build_scan_preview(session, "commodities")

  import asyncio

  result = asyncio.run(_run())
  assert result["graduation_nudge"] is True
  assert result["shadow_mode"] is True
  assert len(result["symbols"]) == 1
  assert result["symbols"][0]["would_enter"] is True


def test_build_scan_preview_commodities_intel_override_on_sell_signal():
  async def _run():
    session = AsyncMock()
    bot = MagicMock()
    bot.get_symbols = AsyncMock(return_value=["SI=F"])
    bot.fetch_price_data = AsyncMock(return_value=(69.0, None))
    bot.get_sentiment_detail = AsyncMock(return_value=(0.1, "news"))
    signal = MagicMock(
      score=-0.2,
      direction="sell",
      macd_signal="bearish",
      volume_confirmed=False,
      reason="bearish",
      rsi=50,
      rsi_divergence=None,
    )
    bot.signal_engine.analyze = MagicMock(return_value=signal)
    bot.signal_engine.composite_score = MagicMock(return_value=0.45)

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
            GateCls.return_value.evaluate = AsyncMock(
              return_value={"live_trading_ready": False, "total_trades": 5, "win_rate": 0.6}
            )
            GateCls.return_value.evaluate_per_bot = AsyncMock(
              return_value={"commodities": {"win_rate": 0.5}}
            )
            with patch(
              "app.engines.scan_preview.get_gate_entry_tightening",
              return_value=MagicMock(active=False, blocked_new_entries=frozenset()),
            ):
              with patch(
                "app.engines.scan_preview.get_chronic_loser_symbols",
                new=AsyncMock(return_value=frozenset()),
              ):
                with patch(
                  "app.engines.scan_preview.get_hard_gate_skip_symbols",
                  new=AsyncMock(return_value=frozenset()),
                ):
                  with patch(
                    "app.engines.scan_preview.get_proven_winner_symbols",
                    return_value=frozenset({"CL=F"}),
                  ):
                    with patch(
                      "app.engines.scan_preview.get_integration_boost",
                      return_value=(0.17, "polymarket"),
                    ):
                      with patch(
                        "app.engines.scan_preview.is_price_sane",
                        return_value=True,
                      ):
                        with patch(
                          "app.engines.scan_preview.is_symbol_in_trade_cooldown",
                          new=AsyncMock(return_value=False),
                        ):
                          return await build_scan_preview(session, "commodities")

  import asyncio

  result = asyncio.run(_run())
  row = result["symbols"][0]
  assert row["direction"] == "sell"
  assert row["would_enter"] is True
  assert "signal_sell" not in row["blockers"]


def test_build_scan_preview_commodities_chronic_loser_intel_bypass():
  async def _run():
    session = AsyncMock()
    bot = MagicMock()
    bot.get_symbols = AsyncMock(return_value=["SI=F"])
    bot.fetch_price_data = AsyncMock(return_value=(69.0, None))
    bot.get_sentiment_detail = AsyncMock(return_value=(0.1, "news"))
    signal = MagicMock(
      score=-0.2,
      direction="sell",
      macd_signal="bearish",
      volume_confirmed=False,
      reason="bearish",
      rsi=50,
      rsi_divergence=None,
    )
    bot.signal_engine.analyze = MagicMock(return_value=signal)
    bot.signal_engine.composite_score = MagicMock(return_value=0.45)

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
            GateCls.return_value.evaluate = AsyncMock(
              return_value={"live_trading_ready": False, "total_trades": 5, "win_rate": 0.6}
            )
            GateCls.return_value.evaluate_per_bot = AsyncMock(
              return_value={"commodities": {"win_rate": 0.5}}
            )
            with patch(
              "app.engines.scan_preview.get_gate_entry_tightening",
              return_value=MagicMock(active=False, blocked_new_entries=frozenset()),
            ):
              with patch(
                "app.engines.scan_preview.get_chronic_loser_symbols",
                new=AsyncMock(return_value=frozenset({"SI=F"})),
              ):
                with patch(
                  "app.engines.scan_preview.get_hard_gate_skip_symbols",
                  new=AsyncMock(return_value=frozenset()),
                ):
                  with patch(
                    "app.engines.scan_preview.get_proven_winner_symbols",
                    new=AsyncMock(return_value=frozenset({"CL=F"})),
                  ):
                    with patch(
                      "app.engines.scan_preview.get_integration_boost",
                      return_value=(0.17, "polymarket"),
                    ):
                      with patch(
                        "app.engines.scan_preview.is_price_sane",
                        return_value=True,
                      ):
                        with patch(
                          "app.engines.scan_preview.is_symbol_in_trade_cooldown",
                          new=AsyncMock(return_value=False),
                        ):
                          return await build_scan_preview(session, "commodities")

  import asyncio

  result = asyncio.run(_run())
  row = result["symbols"][0]
  assert row["would_enter"] is True
  assert "chronic_loser" not in row["blockers"]


def test_build_scan_preview_stocks_early_verification_volume_relax():
  async def _run():
    session = AsyncMock()
    bot = MagicMock()
    bot.get_symbols = AsyncMock(return_value=["NVDA"])
    bot.fetch_price_data = AsyncMock(return_value=(220.0, None))
    bot.get_sentiment_detail = AsyncMock(return_value=(0.15, "news"))
    signal = MagicMock(
      score=0.35,
      direction="buy",
      macd_signal="bullish",
      volume_confirmed=False,
      reason="test",
      rsi=55,
      rsi_divergence=None,
    )
    bot.signal_engine.analyze = MagicMock(return_value=signal)
    bot.signal_engine.composite_score = MagicMock(return_value=0.35)

    tightening = MagicMock(
      active=True,
      blocked_new_entries=frozenset(),
      require_macd_bullish=True,
      min_sentiment=0.04,
    )

    with patch("app.engines.scan_preview.BOT_CLASSES", {"stocks_futures": MagicMock(return_value=bot)}):
      with patch("app.engines.scan_preview.is_bot_paused", return_value=False):
        with patch("app.engines.scan_preview.PaperTradingEngine") as EngineCls:
          strategy = MagicMock()
          strategy.min_signal_score = 0.25
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
            GateCls.return_value.evaluate_per_bot = AsyncMock(return_value={})
            GateCls.return_value.evaluate = AsyncMock(
              return_value={
                "total_trades": 9,
                "win_rate": 0.75,
                "live_trading_ready": False,
              }
            )
            GateCls.MIN_WIN_RATE = 0.55
            with patch(
              "app.engines.scan_preview.get_gate_entry_tightening",
              return_value=tightening,
            ):
              with patch(
                "app.engines.scan_preview.get_chronic_loser_symbols",
                new=AsyncMock(return_value=frozenset()),
              ):
                with patch(
                  "app.engines.scan_preview.get_hard_gate_skip_symbols",
                  new=AsyncMock(return_value=frozenset()),
                ):
                  with patch(
                    "app.engines.scan_preview.get_proven_winner_symbols",
                    return_value=frozenset(),
                  ):
                    with patch(
                      "app.engines.scan_preview.get_integration_boost",
                      return_value=(0.17, "polymarket"),
                    ):
                      with patch(
                        "app.engines.scan_preview.is_price_sane",
                        return_value=True,
                      ):
                        with patch(
                          "app.engines.scan_preview.is_symbol_in_trade_cooldown",
                          new=AsyncMock(return_value=False),
                        ):
                          return await build_scan_preview(session, "stocks_futures")

  import asyncio

  result = asyncio.run(_run())
  assert result["early_verification_boost"] is True
  row = result["symbols"][0]
  assert row["volume_ok"] is True
  assert "volume" not in row["blockers"]
  assert row["would_enter"] is True


def test_build_scan_preview_crypto_intel_override_on_sell_signal():
  async def _run():
    session = AsyncMock()
    bot = MagicMock()
    bot.get_symbols = AsyncMock(return_value=["BTCUSDT"])
    bot.fetch_price_data = AsyncMock(return_value=(78000.0, None))
    bot.get_sentiment_detail = AsyncMock(return_value=(0.08, "news"))
    signal = MagicMock(
      score=-0.1,
      direction="sell",
      macd_signal="bearish",
      volume_confirmed=False,
      reason="bearish",
      rsi=50,
      rsi_divergence=None,
    )
    bot.signal_engine.analyze = MagicMock(return_value=signal)
    bot.signal_engine.composite_score = MagicMock(return_value=0.30)

    with patch("app.engines.scan_preview.BOT_CLASSES", {"crypto": MagicMock(return_value=bot)}):
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
            GateCls.return_value.evaluate = AsyncMock(
              return_value={"live_trading_ready": False, "total_trades": 5, "win_rate": 0.6}
            )
            GateCls.return_value.evaluate_per_bot = AsyncMock(
              return_value={"crypto": {"win_rate": 0.46}}
            )
            with patch(
              "app.engines.scan_preview.get_gate_entry_tightening",
              return_value=MagicMock(active=False, blocked_new_entries=frozenset()),
            ):
              with patch(
                "app.engines.scan_preview.get_chronic_loser_symbols",
                new=AsyncMock(return_value=frozenset()),
              ):
                with patch(
                  "app.engines.scan_preview.get_hard_gate_skip_symbols",
                  new=AsyncMock(return_value=frozenset()),
                ):
                  with patch(
                    "app.engines.scan_preview.get_integration_boost",
                    return_value=(0.14, "polymarket"),
                  ):
                    with patch(
                      "app.engines.scan_preview.is_price_sane",
                      return_value=True,
                    ):
                      with patch(
                        "app.engines.scan_preview.is_symbol_in_trade_cooldown",
                        new=AsyncMock(return_value=False),
                      ):
                        return await build_scan_preview(session, "crypto")

  import asyncio

  result = asyncio.run(_run())
  row = result["symbols"][0]
  assert row["direction"] == "sell"
  assert row["would_enter"] is True
  assert "signal_sell" not in row["blockers"]
  assert "macd" not in row["blockers"]
