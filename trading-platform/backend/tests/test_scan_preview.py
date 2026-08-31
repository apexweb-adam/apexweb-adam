"""Tests for scan preview diagnostics."""

from unittest.mock import AsyncMock, MagicMock, patch

from app.engines.gate_entry_guard import GateEntryTightening, HardGateSkipSets
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
          engine.get_consecutive_losses = AsyncMock(return_value=0)
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
                  "app.engines.scan_preview.get_hard_gate_skip_components",
                  new=AsyncMock(
                    return_value=HardGateSkipSets(
                      recent=frozenset(),
                      large=frozenset(),
                      review=frozenset(),
                    )
                  ),
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
                          "app.engines.scan_preview.symbol_cooldown_remaining_seconds",
                          new=AsyncMock(return_value=0),
                        ):
                          with patch(
                            "app.engines.scan_preview.commodities_weekend_futures_entry_blocked",
                            return_value=False,
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
          engine.get_consecutive_losses = AsyncMock(return_value=0)
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
                  "app.engines.scan_preview.get_hard_gate_skip_components",
                  new=AsyncMock(
                    return_value=HardGateSkipSets(
                      recent=frozenset(),
                      large=frozenset(),
                      review=frozenset(),
                    )
                  ),
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
                          "app.engines.scan_preview.symbol_cooldown_remaining_seconds",
                          new=AsyncMock(return_value=0),
                        ):
                          with patch(
                            "app.engines.scan_preview.commodities_weekend_futures_entry_blocked",
                            return_value=False,
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
          engine.get_consecutive_losses = AsyncMock(return_value=0)
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
                  "app.engines.scan_preview.get_hard_gate_skip_components",
                  new=AsyncMock(
                    return_value=HardGateSkipSets(
                      recent=frozenset(),
                      large=frozenset(),
                      review=frozenset(),
                    )
                  ),
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
                          "app.engines.scan_preview.symbol_cooldown_remaining_seconds",
                          new=AsyncMock(return_value=0),
                        ):
                          with patch(
                            "app.engines.scan_preview.commodities_weekend_futures_entry_blocked",
                            return_value=False,
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
        with patch(
          "app.engines.session_open_log.get_prep_phase_state",
          new_callable=AsyncMock,
          return_value={},
        ):
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
            engine.get_consecutive_losses = AsyncMock(return_value=0)
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
                    "app.engines.scan_preview.get_hard_gate_skip_components",
                    new=AsyncMock(
                      return_value=HardGateSkipSets(
                        recent=frozenset(),
                        large=frozenset(),
                        review=frozenset(),
                      )
                    ),
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
                            "app.engines.scan_preview.symbol_cooldown_remaining_seconds",
                            new=AsyncMock(return_value=0),
                          ):
                            with patch(
                              "app.engines.scan_preview.stocks_session_info",
                              return_value={"in_session": True, "minutes_until_open": 0},
                            ):
                              return await build_scan_preview(session, "stocks_futures")

  import asyncio

  result = asyncio.run(_run())
  assert result["early_verification_boost"] is True
  row = result["symbols"][0]
  assert row["volume_ok"] is True
  assert "volume" not in row["blockers"]
  assert row["would_enter"] is True


def test_build_scan_preview_stocks_early_verification_blocks_weak_raw_signal():
  async def _run():
    session = AsyncMock()
    bot = MagicMock()
    bot.get_symbols = AsyncMock(return_value=["NVDA"])
    bot.fetch_price_data = AsyncMock(return_value=(220.0, None))
    bot.get_sentiment_detail = AsyncMock(return_value=(0.40, "news"))
    signal = MagicMock(
      score=0.03,
      direction="buy",
      macd_signal="bullish",
      volume_confirmed=True,
      reason="weak",
      rsi=55,
      rsi_divergence=None,
    )
    bot.signal_engine.analyze = MagicMock(return_value=signal)
    bot.signal_engine.composite_score = MagicMock(return_value=0.45)

    tightening = MagicMock(
      active=True,
      blocked_new_entries=frozenset(),
      require_macd_bullish=True,
      min_sentiment=0.04,
    )

    with patch("app.engines.scan_preview.BOT_CLASSES", {"stocks_futures": MagicMock(return_value=bot)}):
      with patch("app.engines.scan_preview.is_bot_paused", return_value=False):
        with patch(
          "app.engines.session_open_log.get_prep_phase_state",
          new_callable=AsyncMock,
          return_value={},
        ):
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
            engine.get_consecutive_losses = AsyncMock(return_value=0)
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
                    "app.engines.scan_preview.get_hard_gate_skip_components",
                    new=AsyncMock(
                      return_value=HardGateSkipSets(
                        recent=frozenset(),
                        large=frozenset(),
                        review=frozenset(),
                      )
                    ),
                  ):
                    with patch(
                      "app.engines.scan_preview.get_proven_winner_symbols",
                      return_value=frozenset({"NVDA"}),
                    ):
                      with patch(
                        "app.engines.scan_preview.get_integration_boost",
                        return_value=(0.20, "tradingview alert"),
                      ):
                        with patch(
                          "app.engines.scan_preview.is_price_sane",
                          return_value=True,
                        ):
                          with patch(
                            "app.engines.scan_preview.symbol_cooldown_remaining_seconds",
                            new=AsyncMock(return_value=0),
                          ):
                            return await build_scan_preview(session, "stocks_futures")

  import asyncio

  result = asyncio.run(_run())
  row = result["symbols"][0]
  assert row["would_enter"] is False
  assert any("raw_signal<" in b for b in row["blockers"])


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
          engine.get_consecutive_losses = AsyncMock(return_value=0)
          with patch("app.engines.scan_preview.ProfitabilityGate") as GateCls:
            GateCls.return_value.evaluate = AsyncMock(
              return_value={"live_trading_ready": False, "total_trades": 5, "win_rate": 0.6}
            )
            GateCls.return_value.evaluate_per_bot = AsyncMock(
              return_value={
                "crypto": {
                  "win_rate": 0.50,
                  "profit_factor": 1.25,
                  "total_pnl": 31.0,
                }
              }
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
                  "app.engines.scan_preview.get_hard_gate_skip_components",
                  new=AsyncMock(
                    return_value=HardGateSkipSets(
                      recent=frozenset(),
                      large=frozenset(),
                      review=frozenset(),
                    )
                  ),
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
                        "app.engines.scan_preview.symbol_cooldown_remaining_seconds",
                        new=AsyncMock(return_value=0),
                      ):
                        return await build_scan_preview(session, "crypto")

  import asyncio

  result = asyncio.run(_run())
  row = result["symbols"][0]
  assert row["direction"] == "sell"
  assert row["would_enter"] is True
  assert "signal_sell" not in row["blockers"]
  assert "macd" not in row["blockers"]


def test_build_scan_preview_commodities_recovery_candidates_weekend():
  async def _run():
    session = AsyncMock()
    bot = MagicMock()
    bot.get_symbols = AsyncMock(return_value=["SI=F", "CL=F"])
    bot.fetch_price_data = AsyncMock(return_value=(69.0, None))
    bot.get_sentiment_detail = AsyncMock(return_value=(0.1, "news"))

    def _signal(symbol: str):
      if symbol == "SI=F":
        return MagicMock(
          score=-0.1,
          direction="sell",
          macd_signal="bearish",
          volume_confirmed=False,
          reason="test",
          rsi=50,
          rsi_divergence=None,
        )
      return MagicMock(
        score=0.2,
        direction="buy",
        macd_signal="bullish",
        volume_confirmed=True,
        reason="test",
        rsi=50,
        rsi_divergence=None,
      )

    bot.signal_engine.analyze = MagicMock(
      side_effect=[
        _signal("SI=F"),
        _signal("CL=F"),
      ]
    )
    bot.signal_engine.composite_score = MagicMock(side_effect=[0.501, 0.35])

    with patch("app.engines.scan_preview.BOT_CLASSES", {"commodities": MagicMock(return_value=bot)}):
      with patch("app.engines.scan_preview.is_bot_paused", return_value=False):
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
          engine.get_consecutive_losses = AsyncMock(return_value=0)
          with patch("app.engines.scan_preview.ProfitabilityGate") as GateCls:
            GateCls.return_value.evaluate = AsyncMock(
              return_value={"live_trading_ready": False, "total_trades": 31, "win_rate": 0.44}
            )
            GateCls.return_value.evaluate_per_bot = AsyncMock(
              return_value={"commodities": {"win_rate": 0.44}}
            )
            with patch(
              "app.engines.scan_preview.get_gate_entry_tightening",
              return_value=GateEntryTightening(
                active=True,
                win_rate=0.44,
                min_sentiment=0.06,
                require_macd_bullish=True,
                min_composite_boost=0.0,
                blocked_new_entries=frozenset(),
              ),
            ):
              with patch(
                "app.engines.scan_preview.get_chronic_loser_symbols",
                new=AsyncMock(return_value=frozenset({"SI=F"})),
              ):
                with patch(
                  "app.engines.scan_preview.get_hard_gate_skip_components",
                  new=AsyncMock(
                    return_value=HardGateSkipSets(
                      recent=frozenset({"SI=F"}),
                      large=frozenset(),
                      review=frozenset(),
                    )
                  ),
                ):
                  with patch(
                    "app.engines.scan_preview.get_proven_winner_symbols",
                    return_value=frozenset({"CL=F"}),
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
                          "app.engines.scan_preview.symbol_cooldown_remaining_seconds",
                          new=AsyncMock(return_value=0),
                        ):
                          with patch(
                            "app.engines.scan_preview.commodities_weekend_futures_entry_blocked",
                            return_value=True,
                          ):
                            return await build_scan_preview(session, "commodities")

  import asyncio

  result = asyncio.run(_run())
  si = next(row for row in result["symbols"] if row["symbol"] == "SI=F")
  assert si["recovery_ready"] is True
  assert "SI=F" in result["recovery_candidates"]
  assert result.get("session") is not None


def test_build_scan_preview_stocks_recovery_candidates_gate_skip():
  async def _run():
    session = AsyncMock()
    bot = MagicMock()
    bot.get_symbols = AsyncMock(return_value=["NVDA"])
    bot.fetch_price_data = AsyncMock(return_value=(220.0, None))
    bot.get_sentiment_detail = AsyncMock(return_value=(0.12, "news"))
    signal = MagicMock(
      score=-0.1,
      direction="sell",
      macd_signal="bearish",
      volume_confirmed=False,
      reason="test",
      rsi=50,
      rsi_divergence=None,
    )
    bot.signal_engine.analyze = MagicMock(return_value=signal)
    bot.signal_engine.composite_score = MagicMock(return_value=0.414)

    with patch("app.engines.scan_preview.BOT_CLASSES", {"stocks_futures": MagicMock(return_value=bot)}):
      with patch("app.engines.scan_preview.is_bot_paused", return_value=True):
        with patch(
          "app.engines.session_open_log.get_prep_phase_state",
          new_callable=AsyncMock,
          return_value={},
        ):
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
            engine.get_consecutive_losses = AsyncMock(return_value=0)
            with patch("app.engines.scan_preview.ProfitabilityGate") as GateCls:
              GateCls.return_value.evaluate = AsyncMock(
                return_value={"live_trading_ready": False, "total_trades": 15, "win_rate": 0.57}
              )
              GateCls.return_value.evaluate_per_bot = AsyncMock(
                return_value={"stocks_futures": {"win_rate": 0.57, "profit_factor": 0.62, "total_trades": 15}}
              )
              with patch(
                "app.engines.scan_preview.get_gate_entry_tightening",
                return_value=GateEntryTightening(
                  active=True,
                  win_rate=0.44,
                  min_sentiment=0.04,
                  require_macd_bullish=True,
                  min_composite_boost=0.0,
                  blocked_new_entries=frozenset(),
                ),
              ):
                with patch(
                  "app.engines.scan_preview.get_chronic_loser_symbols",
                  new=AsyncMock(return_value=frozenset()),
                ):
                  with patch(
                    "app.engines.scan_preview.get_hard_gate_skip_components",
                    new=AsyncMock(
                      return_value=HardGateSkipSets(
                        recent=frozenset({"NVDA"}),
                        large=frozenset({"NVDA"}),
                        review=frozenset(),
                      )
                    ),
                  ):
                    with patch(
                      "app.engines.scan_preview.get_proven_winner_symbols",
                      return_value=frozenset({"NVDA", "AAPL"}),
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
                            "app.engines.scan_preview.symbol_cooldown_remaining_seconds",
                            new=AsyncMock(return_value=0),
                          ):
                            return await build_scan_preview(session, "stocks_futures")

  import asyncio

  result = asyncio.run(_run())
  nvda = next(row for row in result["symbols"] if row["symbol"] == "NVDA")
  assert nvda["recovery_ready"] is True
  assert "NVDA" in result["recovery_candidates"]
  assert result["open_count"] == 0
  assert "held_symbols" in result


def test_build_scan_preview_stocks_monday_gate_skip_ready():
  async def _run():
    session = AsyncMock()
    bot = MagicMock()
    bot.get_symbols = AsyncMock(return_value=["AAPL"])
    bot.fetch_price_data = AsyncMock(return_value=(190.0, None))
    bot.get_sentiment_detail = AsyncMock(return_value=(0.12, "news"))
    signal = MagicMock(
      score=0.2,
      direction="sell",
      macd_signal="bearish",
      volume_confirmed=True,
      reason="test",
      rsi=50,
      rsi_divergence=None,
    )
    bot.signal_engine.analyze = MagicMock(return_value=signal)
    bot.signal_engine.composite_score = MagicMock(return_value=0.40)

    with patch("app.engines.scan_preview.BOT_CLASSES", {"stocks_futures": MagicMock(return_value=bot)}):
      with patch("app.engines.scan_preview.is_bot_paused", return_value=True):
        with patch(
          "app.engines.session_open_log.get_prep_phase_state",
          new_callable=AsyncMock,
          return_value={},
        ):
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
            engine.get_consecutive_losses = AsyncMock(return_value=0)
            with patch("app.engines.scan_preview.ProfitabilityGate") as GateCls:
              GateCls.return_value.evaluate = AsyncMock(
                return_value={"live_trading_ready": False, "total_trades": 15, "win_rate": 0.57}
              )
              GateCls.return_value.evaluate_per_bot = AsyncMock(
                return_value={"stocks_futures": {"win_rate": 0.57, "profit_factor": 0.62, "total_trades": 15}}
              )
              with patch(
                "app.engines.scan_preview.get_gate_entry_tightening",
                return_value=GateEntryTightening(
                  active=True,
                  win_rate=0.44,
                  min_sentiment=0.04,
                  require_macd_bullish=True,
                  min_composite_boost=0.0,
                  blocked_new_entries=frozenset(),
                ),
              ):
                with patch(
                  "app.engines.scan_preview.get_chronic_loser_symbols",
                  new=AsyncMock(return_value=frozenset()),
                ):
                  with patch(
                    "app.engines.scan_preview.get_hard_gate_skip_components",
                    new=AsyncMock(
                      return_value=HardGateSkipSets(
                        recent=frozenset({"AAPL"}),
                        large=frozenset(),
                        review=frozenset(),
                      )
                    ),
                  ):
                    with patch(
                      "app.engines.scan_preview.get_proven_winner_symbols",
                      return_value=frozenset({"AAPL"}),
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
                            "app.engines.scan_preview.symbol_cooldown_remaining_seconds",
                            new=AsyncMock(return_value=0),
                          ):
                            with patch(
                              "app.engines.scan_preview.stocks_session_info",
                              return_value={
                                "in_session": False,
                                "minutes_until_open": 45,
                                "minutes_since_open": 0,
                              },
                            ):
                              with patch(
                                "app.engines.gate_entry_guard.stocks_session_info",
                                return_value={
                                  "in_session": False,
                                  "minutes_until_open": 45,
                                  "minutes_since_open": 0,
                                },
                              ):
                                return await build_scan_preview(session, "stocks_futures")

  import asyncio

  result = asyncio.run(_run())
  aapl = next(row for row in result["symbols"] if row["symbol"] == "AAPL")
  assert aapl["monday_gate_skip_ready"] is True
  assert "gate_skip" in aapl["blockers"]
  assert "stocks_session_closed" in aapl["blockers"]
  assert aapl["would_enter"] is False
  assert result.get("stocks_trade_count_nudge") is True
  assert result.get("stocks_trade_count_gap") == 5
  assert result.get("stocks_gate_fast_scan_active") is True
