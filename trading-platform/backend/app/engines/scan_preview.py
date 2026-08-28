"""Read-only scan preview — shows per-symbol signals and entry blockers."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.bots.trading_bots import (
  CommoditiesBot,
  CryptoBot,
  PolymarketBot,
  StocksFuturesBot,
)
from app.engines.gate_entry_guard import (
  SHADOW_MAX_OPEN,
  bot_min_sentiment,
  early_verification_active,
  gate_entry_guards_active,
  gate_position_scale,
  get_gate_entry_tightening,
  get_gate_skip_symbols,
  get_proven_winner_symbols,
  in_shadow_graduation_nudge,
  is_symbol_in_trade_cooldown,
  shadow_entry_min_signal,
  shadow_intel_composite_override,
  shadow_requires_macd,
  stocks_gate_entry_sentiment_ok,
)
from app.engines.integration_signals import get_integration_boost
from app.engines.paper_trading import PaperTradingEngine
from app.engines.platform_settings import is_bot_paused
from app.engines.price_validation import is_price_sane
from app.engines.profitability_gate import ProfitabilityGate

BOT_CLASSES = {
  "crypto": CryptoBot,
  "stocks_futures": StocksFuturesBot,
  "commodities": CommoditiesBot,
  "polymarket": PolymarketBot,
}


async def build_scan_preview(session: AsyncSession, bot_type: str) -> dict[str, Any]:
  bot_cls = BOT_CLASSES.get(bot_type)
  if not bot_cls:
    return {"error": f"unknown bot_type: {bot_type}"}

  bot = bot_cls()
  shadow_mode = await is_bot_paused(session, bot_type)
  engine = PaperTradingEngine(session, bot_type)
  strategy = await engine.get_strategy()
  gate_tightening = await get_gate_entry_tightening(session)

  gate_status = await ProfitabilityGate(session).evaluate()
  entry_guards = gate_entry_guards_active(
    gate_tightening=gate_tightening,
    shadow_mode=shadow_mode,
    live_trading_ready=bool(gate_status.get("live_trading_ready")),
  )

  shadow_bot_wr: float | None = None
  if shadow_mode:
    per_bot = await ProfitabilityGate(session).evaluate_per_bot()
    shadow_bot_wr = float((per_bot.get(bot_type) or {}).get("win_rate") or 0)

  chronic_losers: frozenset[str] = frozenset()
  proven_winners: frozenset[str] = frozenset()
  if entry_guards:
    chronic_losers = await get_gate_skip_symbols(session, bot_type)
    if bot_type in ("stocks_futures", "commodities"):
      proven_winners = await get_proven_winner_symbols(session, bot_type)

  min_signal = strategy.min_signal_score
  if shadow_mode:
    min_signal = shadow_entry_min_signal(
      bot_type, strategy.min_signal_score, bot_win_rate=shadow_bot_wr
    )
  min_sentiment = max(
    strategy.min_sentiment_score,
    bot_min_sentiment(bot_type, gate_tightening),
  )
  graduation_nudge = in_shadow_graduation_nudge(bot_type, shadow_bot_wr)
  open_count = len(await engine.get_open_positions())
  shadow_cap = SHADOW_MAX_OPEN.get(bot_type) if shadow_mode else None

  early_verification_boost = False
  if not shadow_mode and bot_type == "stocks_futures":
    active_trades = int(gate_status.get("total_trades") or 0)
    active_wr = float(gate_status.get("win_rate") or 0)
    if early_verification_active(active_trades, active_wr):
      from app.engines.gate_entry_guard import (
        EARLY_VERIFICATION_MIN_SIGNAL_FLOOR,
        EARLY_VERIFICATION_SENTIMENT_EASE,
        EARLY_VERIFICATION_SIGNAL_EASE,
      )

      min_signal = max(
        EARLY_VERIFICATION_MIN_SIGNAL_FLOOR,
        min_signal - EARLY_VERIFICATION_SIGNAL_EASE,
      )
      min_sentiment = max(0.0, min_sentiment - EARLY_VERIFICATION_SENTIMENT_EASE)
      early_verification_boost = True

  weights = {
    "technical_weight": strategy.technical_weight,
    "sentiment_weight": strategy.sentiment_weight,
    "momentum_weight": strategy.momentum_weight,
  }
  strategy_params = {
    "rsi_oversold": strategy.rsi_oversold,
    "rsi_overbought": strategy.rsi_overbought,
  }

  symbols = await bot.get_symbols()
  previews: list[dict[str, Any]] = []

  for symbol in symbols:
    price, df = await bot.fetch_price_data(symbol)
    if price <= 0 or not is_price_sane(symbol, price):
      previews.append({"symbol": symbol, "skip": "invalid_price"})
      continue

    signal = bot.signal_engine.analyze(symbol, df, strategy_params)
    sentiment, _ = await bot.get_sentiment_detail(symbol)
    composite = bot.signal_engine.composite_score(signal.score, sentiment, weights)
    integration_boost, integration_reason = await get_integration_boost(session, symbol)
    composite = max(0.0, composite + integration_boost)

    entry_min_signal = min_signal
    if gate_tightening.active and bot_type == "stocks_futures" and symbol in proven_winners:
      entry_min_signal = max(0.08, entry_min_signal - 0.02)
    if (
      gate_tightening.active
      and bot_type == "stocks_futures"
      and integration_reason
      and "tradingview" in integration_reason.lower()
      and integration_boost > 0.04
    ):
      entry_min_signal = max(0.08, entry_min_signal - 0.03)
    if gate_tightening.active and bot_type == "stocks_futures" and signal.rsi_divergence == "bullish":
      entry_min_signal = max(0.08, entry_min_signal - 0.02)

    volume_required = signal.volume_confirmed
    if gate_tightening.active and bot_type == "stocks_futures" and symbol in proven_winners:
      volume_required = (
        signal.volume_confirmed
        or integration_boost > 0.03
        or bool(integration_reason and "tradingview" in integration_reason.lower())
      )
    if early_verification_boost and bot_type == "stocks_futures":
      volume_required = (
        signal.volume_confirmed
        or composite >= entry_min_signal + 0.03
        or integration_boost > 0.02
        or signal.macd_signal == "bullish"
        or bool(integration_reason and "tradingview" in integration_reason.lower())
      )
    if graduation_nudge and shadow_mode and bot_type == "commodities":
      volume_required = (
        signal.volume_confirmed
        or composite >= entry_min_signal + 0.02
        or integration_boost > 0.02
        or signal.macd_signal == "bullish"
      )

    entry_direction_ok = signal.direction == "buy" or shadow_intel_composite_override(
      bot_type,
      graduation_nudge=graduation_nudge,
      shadow_mode=shadow_mode,
      composite=composite,
      entry_min_signal=entry_min_signal,
      integration_boost=integration_boost,
    )

    blockers: list[str] = []
    if await is_symbol_in_trade_cooldown(session, bot_type, symbol):
      blockers.append("symbol_cooldown")
    if entry_guards and symbol in chronic_losers:
      blockers.append("chronic_loser")
    if (
      gate_tightening.active
      and bot_type == "stocks_futures"
      and proven_winners
      and symbol not in proven_winners
    ):
      blockers.append("not_proven_winner")
    if (
      shadow_mode
      and bot_type == "commodities"
      and proven_winners
      and symbol not in proven_winners
      and not graduation_nudge
    ):
      blockers.append("not_proven_winner")
    if (
      gate_tightening.active
      and bot_type == "stocks_futures"
      and signal.rsi > 68
    ):
      blockers.append("rsi_high")
    if (
      gate_tightening.active
      and bot_type == "stocks_futures"
      and signal.macd_signal != "bullish"
      and integration_boost <= 0.03
    ):
      blockers.append("macd")
    if shadow_requires_macd(
      bot_type,
      bot_win_rate=shadow_bot_wr,
      gate_tightening=gate_tightening,
      shadow_mode=shadow_mode,
    ) and signal.macd_signal != "bullish":
      blockers.append("macd")
    if shadow_cap is not None and open_count >= shadow_cap:
      blockers.append("shadow_open_cap")
    if not shadow_mode and bot_type in gate_tightening.blocked_new_entries:
      blockers.append("entries_blocked")
    if not entry_direction_ok:
      blockers.append(f"signal_{signal.direction}")
    if not volume_required:
      blockers.append("volume")
    if composite < entry_min_signal:
      blockers.append(f"composite<{entry_min_signal:.2f}")
    if sentiment + integration_boost < min_sentiment:
      blockers.append(f"sentiment<{min_sentiment:.2f}")
    if (
      gate_tightening.active
      and bot_type == "stocks_futures"
      and not stocks_gate_entry_sentiment_ok(sentiment, integration_boost)
    ):
      blockers.append("sentiment_gate")

    previews.append(
      {
        "symbol": symbol,
        "price": price,
        "composite": round(composite, 3),
        "min_signal": round(entry_min_signal, 3),
        "sentiment": round(sentiment, 3),
        "direction": signal.direction,
        "macd": signal.macd_signal,
        "volume_ok": volume_required,
        "would_enter": not blockers,
        "blockers": blockers,
        "integration_boost": round(integration_boost, 3),
      }
    )

  previews.sort(key=lambda row: row.get("composite", 0), reverse=True)
  return {
    "bot_type": bot_type,
    "shadow_mode": shadow_mode,
    "graduation_nudge": graduation_nudge,
    "early_verification_boost": early_verification_boost,
    "shadow_bot_wr": shadow_bot_wr,
    "proven_winners": sorted(proven_winners),
    "min_signal": round(min_signal, 3),
    "symbols": previews,
  }
