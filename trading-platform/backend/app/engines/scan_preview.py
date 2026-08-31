"""Read-only scan preview — shows per-symbol signals and entry blockers."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.bots.trading_bots import (
  CommoditiesBot,
  CryptoBot,
  PolymarketBot,
  StocksFuturesBot,
)
from app.engines.gate_entry_guard import (
  EARLY_VERIFICATION_MIN_RAW_SIGNAL_SCORE,
  HardGateSkipSets,
  apply_entry_min_signal_ease,
  apply_gate_tightening_min_signal,
  bot_min_sentiment,
  chronic_loser_blocks_shadow_entry,
  early_verification_active,
  early_verification_index_etf_entry_min_signal,
  early_verification_macd_ok,
  early_verification_raw_signal_ok,
  gate_entry_guards_active,
  gate_position_scale,
  GATE_INDEX_ETF_SYMBOLS,
  get_chronic_loser_symbols,
  get_gate_entry_tightening,
  get_hard_gate_skip_components,
  get_proven_winner_symbols,
  hard_skip_blocks_shadow_entry,
  bot_win_rate_for_graduation_nudge,
  commodities_graduation_entry_min_signal,
  commodities_graduation_ease_active,
  commodities_verification_trade_count_nudge,
  commodities_verification_cooldown_bypass,
  commodities_verification_chronic_loser_bypass,
  commodities_verification_entry_min_signal,
  commodities_verification_min_sentiment,
  commodities_verification_near_floor_candidate,
  commodities_verification_open_ready,
  commodities_verification_volume_required,
  crypto_graduation_entry_min_signal,
  crypto_momentum_retreat_entry_min_signal,
  crypto_momentum_retreat_active,
  crypto_momentum_retreat_raw_signal_ok,
  crypto_momentum_retreat_raw_signal_floor,
  crypto_momentum_retreat_gate_skip_bypass,
  crypto_momentum_retreat_cooldown_bypass,
  crypto_shadow_raw_signal_floor_active,
  CRYPTO_MOMENTUM_RETREAT_MIN_RAW_SIGNAL,
  CRYPTO_MOMENTUM_RETREAT_ALIGNED_RAW_SIGNAL,
  CRYPTO_MOMENTUM_RETREAT_CAP_ROOM_ALIGNED_RAW_SIGNAL,
  CRYPTO_MOMENTUM_RETREAT_ALIGNED_COMPOSITE_FLOOR,
  CRYPTO_MOMENTUM_RETREAT_CAP_ROOM_ALIGNED_COMPOSITE_FLOOR,
  CRYPTO_MOMENTUM_RETREAT_CAP_PRESSURE_LOSER_USD,
  CRYPTO_MOMENTUM_RETREAT_CAP_FULL_MIN_HOLD_SECONDS,
  CRYPTO_MOMENTUM_RETREAT_LOSS_WIND_DOWN_USD,
  CRYPTO_MOMENTUM_RETREAT_WEAK_SIGNAL_WIND_DOWN_MAX_UPNL,
  COMMODITIES_ACTIVE_GATE_LOSS_WIND_DOWN_USD,
  COMMODITIES_GRADUATION_PF_PROFIT_LOCK_USD,
  COMMODITIES_HIGH_COMPOSITE_RECOVERY_FLOOR,
  commodities_recovery_composite_floor,
  commodities_effective_open_cap,
  crypto_graduation_entry_ease_active,
  crypto_strong_momentum_nudge,
  crypto_pre_graduation_nudge,
  crypto_cap_pressure_nudge,
  graduation_nudge_min_sentiment,
  graduation_nudge_sentiment_ok,
  in_shadow_graduation_nudge,
  intel_override_allows_long_entry,
  is_symbol_in_trade_cooldown,
  open_position_cap_blocks_entry,
  symbol_cooldown_remaining_seconds,
  commodities_monday_recovery_ready,
  commodities_monday_open_ready,
  commodities_near_floor_candidate,
  commodities_monday_futures_gate_skip_bypass,
  commodities_session_info,
  commodities_gate_fast_scan_active,
  commodities_reopen_imminent_scan_active,
  commodities_weekend_futures_entry_blocked,
  commodities_weekend_forex_entry_blocked,
  commodities_weekend_spot_entry_blocked,
  commodities_gold_proxy_duplicate_entry_blocked,
  commodities_weekend_spot_post_profit_lock_entry_blocked,
  gate_cap_pressure_proxy_entry_blocked,
  shadow_entry_min_signal,
  shadow_graduation_min_composite,
  shadow_graduation_loss_exposure_blocks_entry,
  shadow_intel_composite_override,
  shadow_requires_macd,
  stocks_monday_gate_skip_bypass,
  stocks_monday_open_ready,
  stocks_near_floor_candidate,
  stocks_monday_recovery_ready,
  stocks_trade_count_entry_min_signal,
  stocks_trade_count_graduation_nudge,
  stocks_trade_count_min_sentiment,
  stocks_gate_fast_scan_active,
  stocks_open_imminent_scan_active,
  stocks_trade_count_volume_required,
  stocks_proven_winner_sentiment_gate_ok,
  STOCKS_TRADE_COUNT_PROFIT_LOCK_USD,
  stocks_negative_pf_blocks_entry,
  stocks_session_entry_blocked,
  stocks_session_info,
  whale_memecoin_aligned,
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
  per_bot_stats: dict[str, Any] = {}
  if shadow_mode or bot_type == "stocks_futures" or bot_type == "commodities":
    per_bot_all = await ProfitabilityGate(session).evaluate_per_bot()
    per_bot_stats = per_bot_all.get(bot_type) or {}
  if shadow_mode:
    shadow_bot_wr = float(per_bot_stats.get("win_rate") or 0)
  bot_wr = bot_win_rate_for_graduation_nudge(
    bot_type,
    shadow_mode=shadow_mode,
    shadow_bot_wr=shadow_bot_wr,
    per_bot_stats=per_bot_stats,
  )

  chronic_losers: frozenset[str] = frozenset()
  hard_skip_sets = HardGateSkipSets(
    recent=frozenset(),
    large=frozenset(),
    review=frozenset(),
  )
  proven_winners: frozenset[str] = frozenset()
  if entry_guards:
    chronic_losers = await get_chronic_loser_symbols(session, bot_type)
    hard_skip_sets = await get_hard_gate_skip_components(session, bot_type)
    if bot_type in ("stocks_futures", "commodities"):
      proven_winners = await get_proven_winner_symbols(session, bot_type)

  min_signal = strategy.min_signal_score
  if shadow_mode:
    min_signal = shadow_entry_min_signal(
      bot_type,
      strategy.min_signal_score,
      bot_win_rate=bot_wr,
      profit_factor=per_bot_stats.get("profit_factor"),
      total_pnl=per_bot_stats.get("total_pnl"),
    )
  elif bot_type == "commodities" and (
    in_shadow_graduation_nudge(
      bot_type,
      bot_wr,
      profit_factor=per_bot_stats.get("profit_factor"),
      total_pnl=per_bot_stats.get("total_pnl"),
    )
    or commodities_graduation_ease_active(
      bot_type,
      shadow_mode,
      False,
      gate_status,
      per_bot_stats,
    )
  ):
    min_signal = shadow_entry_min_signal(
      bot_type,
      strategy.min_signal_score,
      bot_win_rate=bot_wr,
      profit_factor=per_bot_stats.get("profit_factor"),
      total_pnl=per_bot_stats.get("total_pnl"),
    )
  min_sentiment = max(
    strategy.min_sentiment_score,
    bot_min_sentiment(bot_type, gate_tightening),
  )
  if shadow_mode:
    from app.engines.gate_entry_guard import SHADOW_MIN_SENTIMENT_BOOST

    min_sentiment += SHADOW_MIN_SENTIMENT_BOOST
  graduation_nudge = in_shadow_graduation_nudge(
    bot_type,
    bot_wr,
    profit_factor=per_bot_stats.get("profit_factor"),
    total_pnl=per_bot_stats.get("total_pnl"),
  )
  commodities_verification_nudge = commodities_verification_trade_count_nudge(
    bot_type,
    shadow_mode,
    gate_status,
    per_bot_stats,
  )
  commodities_ease_active = commodities_graduation_ease_active(
    bot_type,
    shadow_mode,
    graduation_nudge,
    gate_status,
    per_bot_stats,
  )
  bypass_nudge = graduation_nudge or commodities_ease_active
  stocks_trade_count_nudge = stocks_trade_count_graduation_nudge(
    bot_type,
    shadow_mode,
    per_bot_stats.get("win_rate"),
    int(per_bot_stats.get("total_trades") or 0),
  )
  stocks_open_ready_active = False
  if bot_type == "stocks_futures":
    from app.engines.session_open_log import get_prep_phase_state

    prep_state = await get_prep_phase_state(session)
    stocks_open_ready_active = bool(
      (prep_state.get("us_stocks_open") or {}).get("open_ready_symbols")
    )
  stocks_session = stocks_session_info() if bot_type == "stocks_futures" else None
  stocks_fast_scan_active = stocks_gate_fast_scan_active(
    stocks_session,
    trade_count_nudge=stocks_trade_count_nudge,
    open_ready_active=stocks_open_ready_active,
  )
  stocks_open_imminent = (
    stocks_open_imminent_scan_active(
      stocks_session,
      trade_count_nudge=stocks_trade_count_nudge,
      open_ready_active=stocks_open_ready_active,
    )
    if bot_type == "stocks_futures"
    and (stocks_trade_count_nudge or stocks_open_ready_active)
    else False
  )
  commodities_fast_scan_active = commodities_gate_fast_scan_active(
    commodities_session_info() if bot_type == "commodities" else None,
    graduation_nudge=commodities_ease_active if bot_type == "commodities" else False,
  )
  commodities_reopen_imminent = (
    commodities_reopen_imminent_scan_active(
      commodities_session_info(),
      graduation_nudge=commodities_ease_active,
    )
    if bot_type == "commodities" and commodities_ease_active
    else False
  )
  crypto_strong_momentum = crypto_strong_momentum_nudge(
    bot_type,
    shadow_mode,
    bot_wr,
    per_bot_stats.get("profit_factor"),
    per_bot_stats.get("total_pnl"),
  )
  crypto_pre_graduation = crypto_pre_graduation_nudge(
    bot_type,
    shadow_mode,
    bot_wr,
    per_bot_stats.get("profit_factor"),
    per_bot_stats.get("total_pnl"),
  )
  min_sentiment = graduation_nudge_min_sentiment(
    bot_type,
    min_sentiment,
    graduation_nudge=bypass_nudge,
    shadow_mode=shadow_mode,
    bot_win_rate=bot_wr,
    profit_factor=per_bot_stats.get("profit_factor"),
    total_pnl=per_bot_stats.get("total_pnl"),
  )
  loss_streak = await engine.get_consecutive_losses()
  min_signal = apply_gate_tightening_min_signal(
    min_signal,
    bot_type,
    gate_tightening=gate_tightening,
    graduation_nudge=graduation_nudge,
    shadow_mode=shadow_mode,
    loss_streak=loss_streak,
  )
  open_positions = await engine.get_open_positions()
  open_count = len(open_positions)
  held_symbols = {p.symbol for p in open_positions}
  from app.engines.gate_entry_guard import shadow_max_open_for_bot

  shadow_cap = shadow_max_open_for_bot(
    bot_type,
    shadow_mode=shadow_mode,
    bot_win_rate=bot_wr,
    profit_factor=per_bot_stats.get("profit_factor"),
    total_pnl=per_bot_stats.get("total_pnl"),
  )
  gate_caps = {
    "crypto": gate_tightening.max_crypto_open_positions,
    "commodities": gate_tightening.max_commodities_open_positions,
    "stocks_futures": gate_tightening.max_stocks_open_positions,
    "polymarket": gate_tightening.max_pm_open_positions,
  }
  effective_open_cap = shadow_cap
  if not shadow_mode:
    base_cap = gate_caps.get(bot_type)
    effective_open_cap = commodities_effective_open_cap(
      base_cap,
      bot_type=bot_type,
      graduation_nudge=graduation_nudge,
      shadow_mode=shadow_mode,
      verification_nudge=commodities_verification_nudge,
    ) if bot_type == "commodities" else base_cap
  loss_exposure_block = shadow_graduation_loss_exposure_blocks_entry(
    open_positions,
    graduation_nudge=graduation_nudge,
    shadow_mode=shadow_mode,
    bot_type=bot_type,
    shadow_open_cap=shadow_cap,
    bot_win_rate=bot_wr,
    profit_factor=per_bot_stats.get("profit_factor"),
    total_pnl=per_bot_stats.get("total_pnl"),
  )

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

  last_exit_reasons: dict[str, str] = {}
  if bot_type == "crypto" and shadow_mode:
    from app.models.entities import Trade
    from sqlalchemy import select

    sell_rows = await session.execute(
      select(Trade.symbol, Trade.reason)
      .where(Trade.bot_type == bot_type, Trade.action == "sell")
      .order_by(Trade.executed_at.desc())
    )
    for sym, exit_reason in sell_rows:
      if sym and sym not in last_exit_reasons:
        last_exit_reasons[sym] = exit_reason or ""

  for symbol in symbols:
    price, df = await bot.fetch_price_data(symbol)
    if price <= 0 or not is_price_sane(symbol, price):
      previews.append({"symbol": symbol, "skip": "invalid_price"})
      continue

    signal = bot.signal_engine.analyze(symbol, df, strategy_params)
    sentiment, _ = await bot.get_sentiment_detail(symbol, session=session)
    composite = bot.signal_engine.composite_score(signal.score, sentiment, weights)
    integration_boost, integration_reason = await get_integration_boost(session, symbol)
    composite = max(0.0, composite + integration_boost)

    entry_min_signal = min_signal
    if (
      (gate_tightening.active or early_verification_boost)
      and bot_type == "stocks_futures"
      and symbol in proven_winners
    ):
      entry_min_signal = apply_entry_min_signal_ease(
        entry_min_signal, 0.02, early_boost=early_verification_boost
      )
    if (
      (gate_tightening.active or early_verification_boost)
      and bot_type == "stocks_futures"
      and integration_reason
      and "tradingview" in integration_reason.lower()
      and integration_boost > 0.04
    ):
      entry_min_signal = apply_entry_min_signal_ease(
        entry_min_signal, 0.03, early_boost=early_verification_boost
      )
    if gate_tightening.active and bot_type == "stocks_futures" and signal.rsi_divergence == "bullish":
      entry_min_signal = apply_entry_min_signal_ease(
        entry_min_signal, 0.02, early_boost=early_verification_boost
      )
    entry_min_signal = early_verification_index_etf_entry_min_signal(
      symbol,
      entry_min_signal,
      early_boost=early_verification_boost,
    )
    grad_composite_floor = shadow_graduation_min_composite(
      bot_type,
      graduation_nudge=graduation_nudge,
      shadow_mode=shadow_mode,
    )
    if grad_composite_floor is not None:
      entry_min_signal = max(entry_min_signal, grad_composite_floor)
    entry_min_signal = commodities_graduation_entry_min_signal(
      entry_min_signal,
      bot_type=bot_type,
      graduation_nudge=commodities_ease_active,
      shadow_mode=shadow_mode,
      signal_direction=signal.direction,
      macd_signal=signal.macd_signal,
      symbol=symbol,
      proven_winners=proven_winners,
    )
    entry_min_signal = commodities_verification_entry_min_signal(
      entry_min_signal,
      bot_type=bot_type,
      shadow_mode=shadow_mode,
      symbol=symbol,
      proven_winners=proven_winners,
      gate_status=gate_status,
      per_bot_stats=per_bot_stats,
    )
    entry_min_signal = crypto_graduation_entry_min_signal(
      entry_min_signal,
      bot_type=bot_type,
      graduation_nudge=graduation_nudge,
      shadow_mode=shadow_mode,
      signal_direction=signal.direction,
      macd_signal=signal.macd_signal,
      bot_win_rate=bot_wr,
      profit_factor=per_bot_stats.get("profit_factor"),
      total_pnl=per_bot_stats.get("total_pnl"),
    )
    entry_min_signal = crypto_momentum_retreat_entry_min_signal(
      entry_min_signal,
      bot_type=bot_type,
      graduation_nudge=graduation_nudge,
      shadow_mode=shadow_mode,
      bot_win_rate=bot_wr,
      profit_factor=per_bot_stats.get("profit_factor"),
      total_pnl=per_bot_stats.get("total_pnl"),
      signal_direction=signal.direction,
      macd_signal=signal.macd_signal,
      open_count=open_count,
      shadow_open_cap=shadow_cap,
    )
    entry_min_signal = stocks_trade_count_entry_min_signal(
      entry_min_signal,
      bot_type=bot_type,
      shadow_mode=shadow_mode,
      symbol=symbol,
      proven_winners=proven_winners,
      bot_win_rate=per_bot_stats.get("win_rate"),
      total_trades=int(per_bot_stats.get("total_trades") or 0),
    )
    symbol_min_sentiment = stocks_trade_count_min_sentiment(
      min_sentiment,
      bot_type=bot_type,
      shadow_mode=shadow_mode,
      symbol=symbol,
      proven_winners=proven_winners,
      bot_win_rate=per_bot_stats.get("win_rate"),
      total_trades=int(per_bot_stats.get("total_trades") or 0),
      composite=composite,
    )
    symbol_min_sentiment = commodities_verification_min_sentiment(
      symbol_min_sentiment,
      bot_type=bot_type,
      shadow_mode=shadow_mode,
      symbol=symbol,
      proven_winners=proven_winners,
      gate_status=gate_status,
      per_bot_stats=per_bot_stats,
      composite=composite,
    )

    volume_required = signal.volume_confirmed
    if (
      (gate_tightening.active or early_verification_boost)
      and bot_type == "stocks_futures"
      and symbol in proven_winners
    ):
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
    if commodities_ease_active and bot_type == "commodities":
      volume_required = (
        signal.volume_confirmed
        or composite >= entry_min_signal + 0.02
        or integration_boost > 0.02
        or signal.macd_signal == "bullish"
      )
    if graduation_nudge and shadow_mode and bot_type == "crypto":
      volume_required = (
        signal.volume_confirmed
        or composite >= entry_min_signal + 0.02
        or integration_boost > 0.02
        or signal.macd_signal == "bullish"
      )
    volume_required = stocks_trade_count_volume_required(
      volume_required,
      bot_type=bot_type,
      shadow_mode=shadow_mode,
      symbol=symbol,
      proven_winners=proven_winners,
      bot_win_rate=per_bot_stats.get("win_rate"),
      total_trades=int(per_bot_stats.get("total_trades") or 0),
      composite=composite,
      entry_min_signal=entry_min_signal,
      macd_signal=signal.macd_signal,
      integration_boost=integration_boost,
      integration_reason=integration_reason,
    )
    volume_required = commodities_verification_volume_required(
      volume_required,
      bot_type=bot_type,
      shadow_mode=shadow_mode,
      symbol=symbol,
      proven_winners=proven_winners,
      gate_status=gate_status,
      per_bot_stats=per_bot_stats,
      composite=composite,
      entry_min_signal=entry_min_signal,
      macd_signal=signal.macd_signal,
      integration_boost=integration_boost,
    )

    intel_override = shadow_intel_composite_override(
      bot_type,
      graduation_nudge=bypass_nudge,
      shadow_mode=shadow_mode,
      composite=composite,
      entry_min_signal=entry_min_signal,
      integration_boost=integration_boost,
      whale_aligned=whale_memecoin_aligned(integration_reason, integration_boost),
      bot_win_rate=per_bot_stats.get("win_rate"),
      profit_factor=per_bot_stats.get("profit_factor"),
      total_pnl=per_bot_stats.get("total_pnl"),
    )

    entry_direction_ok = (
      signal.direction == "buy"
      or intel_override_allows_long_entry(
        bot_type,
        intel_override=intel_override,
        signal_direction=signal.direction,
        shadow_mode=shadow_mode,
        graduation_nudge=bypass_nudge,
      )
    )

    blockers: list[str] = []
    if symbol in held_symbols:
      blockers.append("already_held")
    if stocks_session_entry_blocked(bot_type, stocks_session):
      blockers.append("stocks_session_closed")
    if commodities_weekend_futures_entry_blocked(symbol):
      blockers.append("weekend_futures_closed")
    if commodities_weekend_forex_entry_blocked(
      bot_type=bot_type,
      shadow_mode=shadow_mode,
      symbol=symbol,
      graduation_nudge=graduation_nudge,
    ):
      blockers.append("weekend_forex_blocked")
    if commodities_weekend_spot_entry_blocked(
      bot_type=bot_type,
      shadow_mode=shadow_mode,
      symbol=symbol,
      graduation_nudge=graduation_nudge,
    ):
      blockers.append("weekend_spot_blocked")
    if commodities_gold_proxy_duplicate_entry_blocked(symbol, held_symbols):
      blockers.append("gold_proxy_duplicate")
    if await commodities_weekend_spot_post_profit_lock_entry_blocked(
      session,
      bot_type=bot_type,
      shadow_mode=shadow_mode,
      graduation_nudge=graduation_nudge,
      symbol=symbol,
    ):
      blockers.append("weekend_spot_post_lock")
    if gate_cap_pressure_proxy_entry_blocked(
      bot_type=bot_type,
      shadow_mode=shadow_mode,
      graduation_nudge=graduation_nudge,
      symbol=symbol,
      open_count=len(held_symbols),
      gate_tightening=gate_tightening,
      verification_nudge=commodities_verification_nudge,
    ):
      blockers.append("open_cap_proxy")
    if stocks_negative_pf_blocks_entry(
      bot_type=bot_type,
      symbol=symbol,
      composite=composite,
      proven_winners=proven_winners,
      profit_factor=per_bot_stats.get("profit_factor"),
      total_trades=int(per_bot_stats.get("total_trades") or 0),
      bot_win_rate=per_bot_stats.get("win_rate"),
    ):
      blockers.append("stocks_negative_pf")
    cooldown_remaining = await symbol_cooldown_remaining_seconds(
      session,
      bot_type,
      symbol,
      chronic_symbols=chronic_losers,
      large_loss_symbols=hard_skip_sets.large,
      graduation_nudge=bypass_nudge,
      shadow_mode=shadow_mode,
      signal_direction=signal.direction,
      macd_signal=signal.macd_signal,
      composite=composite,
      proven_winners=proven_winners,
      bot_win_rate=per_bot_stats.get("win_rate"),
      total_trades=int(per_bot_stats.get("total_trades") or 0),
      open_count=open_count,
      shadow_open_cap=shadow_cap,
      profit_factor=per_bot_stats.get("profit_factor"),
      total_pnl=per_bot_stats.get("total_pnl"),
      gate_status=gate_status,
      per_bot_stats=per_bot_stats,
    )
    if cooldown_remaining > 0:
      blockers.append("symbol_cooldown")
    if entry_guards and hard_skip_blocks_shadow_entry(
      symbol,
      bot_type=bot_type,
      recent_skip=hard_skip_sets.recent,
      large_skip=hard_skip_sets.large,
      review_skip=hard_skip_sets.review,
      graduation_nudge=bypass_nudge,
      shadow_mode=shadow_mode,
      intel_override=intel_override,
      composite=composite,
      integration_boost=integration_boost,
      signal_direction=signal.direction,
      macd_signal=signal.macd_signal,
      proven_winners=proven_winners,
      bot_win_rate=per_bot_stats.get("win_rate"),
      total_trades=int(per_bot_stats.get("total_trades") or 0),
      profit_factor=per_bot_stats.get("profit_factor"),
      total_pnl=per_bot_stats.get("total_pnl"),
      open_count=open_count,
      shadow_open_cap=shadow_cap,
      gate_status=gate_status,
      per_bot_stats=per_bot_stats,
    ):
      blockers.append("gate_skip")
    if chronic_loser_blocks_shadow_entry(
      symbol,
      chronic_losers,
      bot_type=bot_type,
      graduation_nudge=bypass_nudge,
      shadow_mode=shadow_mode,
      intel_override=intel_override,
      proven_winners=proven_winners,
      bot_win_rate=per_bot_stats.get("win_rate"),
      composite=composite,
      signal_direction=signal.direction,
      macd_signal=signal.macd_signal,
      total_trades=int(per_bot_stats.get("total_trades") or 0),
      profit_factor=per_bot_stats.get("profit_factor"),
      total_pnl=per_bot_stats.get("total_pnl"),
      open_count=open_count,
      shadow_open_cap=shadow_cap,
      gate_status=gate_status,
      per_bot_stats=per_bot_stats,
    ):
      blockers.append("chronic_loser")
    if (
      (gate_tightening.active or early_verification_boost)
      and bot_type == "stocks_futures"
      and proven_winners
      and symbol not in proven_winners
    ):
      blockers.append("not_proven_winner")
    if (
      early_verification_boost
      and bot_type == "stocks_futures"
      and symbol in GATE_INDEX_ETF_SYMBOLS
      and proven_winners
      and symbol not in proven_winners
    ):
      blockers.append("index_etf_unproven")
    if (
      shadow_mode
      and bot_type == "commodities"
      and proven_winners
      and symbol not in proven_winners
      and not graduation_nudge
    ):
      blockers.append("not_proven_winner")
    if (
      (gate_tightening.active or early_verification_boost)
      and bot_type == "stocks_futures"
      and signal.rsi > 68
    ):
      blockers.append("rsi_high")
    if (
      early_verification_boost
      and bot_type == "stocks_futures"
      and not early_verification_macd_ok(
        macd_signal=signal.macd_signal,
        integration_boost=integration_boost,
      )
    ):
      blockers.append("macd_early")
    if (
      gate_tightening.active
      and bot_type == "stocks_futures"
      and signal.macd_signal != "bullish"
      and integration_boost <= 0.03
    ):
      blockers.append("macd")
    if shadow_requires_macd(
      bot_type,
      bot_win_rate=bot_wr,
      gate_tightening=gate_tightening,
      shadow_mode=shadow_mode,
      profit_factor=per_bot_stats.get("profit_factor"),
      total_pnl=per_bot_stats.get("total_pnl"),
    ) and signal.macd_signal != "bullish":
      blockers.append("macd")
    if (
      symbol not in held_symbols
      and open_position_cap_blocks_entry(
      bot_type,
      shadow_mode=shadow_mode,
      open_count=open_count,
      gate_tightening=gate_tightening,
      shadow_open_cap=shadow_cap,
      graduation_nudge=bypass_nudge,
      verification_nudge=commodities_verification_nudge,
    )
    ):
      blockers.append("open_cap")
    if loss_exposure_block:
      blockers.append("loss_exposure")
    if not shadow_mode and bot_type in gate_tightening.blocked_new_entries:
      blockers.append("entries_blocked")
    if not entry_direction_ok:
      blockers.append(f"signal_{signal.direction}")
    if not volume_required:
      blockers.append("volume")
    if composite < entry_min_signal:
      blockers.append(f"composite<{entry_min_signal:.2f}")
    if not graduation_nudge_sentiment_ok(
      bot_type,
      graduation_nudge=bypass_nudge,
      shadow_mode=shadow_mode,
      sentiment=sentiment,
      integration_boost=integration_boost,
      min_sentiment=symbol_min_sentiment,
      composite=composite,
      entry_min_signal=entry_min_signal,
      signal_direction=signal.direction,
      macd_signal=signal.macd_signal,
      symbol=symbol,
      proven_winners=proven_winners,
      bot_win_rate=bot_wr,
      profit_factor=per_bot_stats.get("profit_factor"),
      total_pnl=per_bot_stats.get("total_pnl"),
      gate_status=gate_status,
      per_bot_stats=per_bot_stats,
    ):
      blockers.append(f"sentiment<{symbol_min_sentiment:.2f}")
    if (
      gate_tightening.active
      and bot_type == "stocks_futures"
      and not stocks_proven_winner_sentiment_gate_ok(
        bot_type=bot_type,
        shadow_mode=shadow_mode,
        symbol=symbol,
        proven_winners=proven_winners,
        bot_win_rate=per_bot_stats.get("win_rate"),
        composite=composite,
        signal_direction=signal.direction,
        macd_signal=signal.macd_signal,
        sentiment=sentiment,
        integration_boost=integration_boost,
        total_trades=int(per_bot_stats.get("total_trades") or 0),
      )
    ):
      blockers.append("sentiment_gate")
    if not early_verification_raw_signal_ok(
      signal.score,
      early_boost=early_verification_boost,
      bot_type=bot_type,
    ):
      blockers.append(f"raw_signal<{EARLY_VERIFICATION_MIN_RAW_SIGNAL_SCORE:.2f}")
    if not crypto_momentum_retreat_raw_signal_ok(
      signal.score,
      bot_type=bot_type,
      graduation_nudge=graduation_nudge,
      shadow_mode=shadow_mode,
      bot_win_rate=per_bot_stats.get("win_rate"),
      profit_factor=per_bot_stats.get("profit_factor"),
      total_pnl=per_bot_stats.get("total_pnl"),
      composite=composite,
      signal_direction=signal.direction,
      macd_signal=signal.macd_signal,
      open_count=open_count,
      shadow_open_cap=shadow_cap,
    ):
      raw_floor = crypto_momentum_retreat_raw_signal_floor(
        bot_type=bot_type,
        graduation_nudge=graduation_nudge,
        shadow_mode=shadow_mode,
        bot_win_rate=per_bot_stats.get("win_rate"),
        profit_factor=per_bot_stats.get("profit_factor"),
        total_pnl=per_bot_stats.get("total_pnl"),
        composite=composite,
        signal_direction=signal.direction,
        macd_signal=signal.macd_signal,
        open_count=open_count,
        shadow_open_cap=shadow_cap,
      )
      blockers.append(f"shadow_raw<{raw_floor:.2f}")

    monday_gate_skip_ready = False
    verification_cooldown_bypass_ready = False
    verification_chronic_bypass_ready = False
    crypto_retreat_gate_skip_ready = False
    crypto_retreat_cooldown_ready = False
    if bot_type == "stocks_futures":
      monday_gate_skip_ready = stocks_monday_gate_skip_bypass(
        bot_type=bot_type,
        shadow_mode=shadow_mode,
        symbol=symbol,
        proven_winners=proven_winners,
        bot_win_rate=per_bot_stats.get("win_rate"),
        total_trades=int(per_bot_stats.get("total_trades") or 0),
        signal_direction="buy",
        macd_signal="bullish",
        composite=composite,
      )
    if bot_type == "commodities":
      monday_gate_skip_ready = commodities_monday_futures_gate_skip_bypass(
        bot_type=bot_type,
        shadow_mode=shadow_mode,
        symbol=symbol,
        graduation_nudge=bypass_nudge,
        signal_direction=signal.direction,
        macd_signal=signal.macd_signal,
        composite=composite,
      )
      verification_cooldown_bypass_ready = commodities_verification_cooldown_bypass(
        bot_type=bot_type,
        shadow_mode=shadow_mode,
        symbol=symbol,
        proven_winners=proven_winners,
        gate_status=gate_status,
        per_bot_stats=per_bot_stats,
        signal_direction=signal.direction,
        macd_signal=signal.macd_signal,
        composite=composite,
      )
      verification_chronic_bypass_ready = commodities_verification_chronic_loser_bypass(
        bot_type=bot_type,
        shadow_mode=shadow_mode,
        symbol=symbol,
        proven_winners=proven_winners,
        gate_status=gate_status,
        per_bot_stats=per_bot_stats,
        signal_direction=signal.direction,
        macd_signal=signal.macd_signal,
        composite=composite,
      )
    if bot_type == "crypto":
      crypto_retreat_gate_skip_ready = crypto_momentum_retreat_gate_skip_bypass(
        bot_type=bot_type,
        shadow_mode=shadow_mode,
        graduation_nudge=graduation_nudge,
        bot_win_rate=per_bot_stats.get("win_rate"),
        profit_factor=per_bot_stats.get("profit_factor"),
        total_pnl=per_bot_stats.get("total_pnl"),
        signal_direction=signal.direction,
        macd_signal=signal.macd_signal,
        composite=composite,
        open_count=open_count,
        shadow_open_cap=shadow_cap,
      )
      crypto_retreat_cooldown_ready = crypto_momentum_retreat_cooldown_bypass(
        bot_type=bot_type,
        shadow_mode=shadow_mode,
        graduation_nudge=graduation_nudge,
        bot_win_rate=per_bot_stats.get("win_rate"),
        profit_factor=per_bot_stats.get("profit_factor"),
        total_pnl=per_bot_stats.get("total_pnl"),
        signal_direction=signal.direction,
        macd_signal=signal.macd_signal,
        composite=composite,
        open_count=open_count,
        shadow_open_cap=shadow_cap,
        last_exit_reason=last_exit_reasons.get(symbol),
      )

    monday_open_ready = (
      commodities_monday_open_ready(
        bot_type=bot_type,
        shadow_mode=shadow_mode,
        symbol=symbol,
        composite=composite,
        signal_direction=signal.direction,
        macd_signal=signal.macd_signal,
        blockers=blockers,
        graduation_nudge=commodities_ease_active,
      )
      or commodities_verification_open_ready(
        bot_type=bot_type,
        shadow_mode=shadow_mode,
        symbol=symbol,
        proven_winners=proven_winners,
        gate_status=gate_status,
        per_bot_stats=per_bot_stats,
        composite=composite,
        signal_direction=signal.direction,
        macd_signal=signal.macd_signal,
        blockers=blockers,
      )
      or stocks_monday_open_ready(
        bot_type=bot_type,
        shadow_mode=shadow_mode,
        symbol=symbol,
        proven_winners=proven_winners,
        bot_win_rate=per_bot_stats.get("win_rate"),
        composite=composite,
        signal_direction=signal.direction,
        macd_signal=signal.macd_signal,
        blockers=blockers,
        total_trades=int(per_bot_stats.get("total_trades") or 0),
      )
    )
    near_floor = (
      commodities_near_floor_candidate(
        composite=composite,
        signal_direction=signal.direction,
        macd_signal=signal.macd_signal,
        blockers=blockers,
        graduation_nudge=commodities_ease_active,
        monday_open_ready=monday_open_ready,
      )
      or commodities_verification_near_floor_candidate(
        bot_type=bot_type,
        shadow_mode=shadow_mode,
        symbol=symbol,
        proven_winners=proven_winners,
        gate_status=gate_status,
        per_bot_stats=per_bot_stats,
        composite=composite,
        signal_direction=signal.direction,
        macd_signal=signal.macd_signal,
        blockers=blockers,
        open_ready=monday_open_ready,
      )
      or stocks_near_floor_candidate(
        composite=composite,
        signal_direction=signal.direction,
        macd_signal=signal.macd_signal,
        blockers=blockers,
        trade_count_nudge=stocks_trade_count_nudge,
        monday_open_ready=monday_open_ready,
      )
    )

    previews.append(
      {
        "symbol": symbol,
        "price": price,
        "composite": round(composite, 3),
        "raw_signal": round(signal.score, 3),
        "min_signal": round(entry_min_signal, 3),
        "sentiment": round(sentiment, 3),
        "direction": signal.direction,
        "macd": signal.macd_signal,
        "volume_ok": volume_required,
        "would_enter": not blockers,
        "blockers": blockers,
        "recovery_ready": (
          commodities_monday_recovery_ready(
            bot_type=bot_type,
            shadow_mode=shadow_mode,
            symbol=symbol,
            composite=composite,
            blockers=blockers,
            graduation_nudge=graduation_nudge,
          )
          or stocks_monday_recovery_ready(
            bot_type=bot_type,
            shadow_mode=shadow_mode,
            symbol=symbol,
            proven_winners=proven_winners,
            bot_win_rate=per_bot_stats.get("win_rate"),
            composite=composite,
            blockers=blockers,
            total_trades=int(per_bot_stats.get("total_trades") or 0),
          )
        ),
        "monday_open_ready": monday_open_ready,
        "near_floor_candidate": near_floor,
        "monday_gate_skip_ready": monday_gate_skip_ready,
        "verification_cooldown_bypass_ready": verification_cooldown_bypass_ready,
        "verification_chronic_bypass_ready": verification_chronic_bypass_ready,
        "crypto_retreat_gate_skip_ready": crypto_retreat_gate_skip_ready,
        "crypto_retreat_cooldown_ready": crypto_retreat_cooldown_ready,
        "integration_boost": round(integration_boost, 3),
        "intel_override": intel_override,
        "cooldown_seconds": cooldown_remaining or None,
      }
    )

  previews.sort(key=lambda row: row.get("composite", 0), reverse=True)
  recovery_candidates = [row["symbol"] for row in previews if row.get("recovery_ready")]
  open_ready_candidates = [row["symbol"] for row in previews if row.get("monday_open_ready")]
  near_floor_candidates = [row["symbol"] for row in previews if row.get("near_floor_candidate")]
  session = (
    commodities_session_info()
    if bot_type == "commodities"
    else stocks_session_info()
    if bot_type == "stocks_futures"
    else None
  )
  crypto_cap_pressure = (
    bot_type == "crypto"
    and shadow_mode
    and shadow_cap is not None
    and open_count >= shadow_cap
    and crypto_cap_pressure_nudge(
      bot_type,
      shadow_mode,
      graduation_nudge,
      bot_wr,
      per_bot_stats.get("profit_factor"),
      per_bot_stats.get("total_pnl"),
    )
  )
  crypto_momentum_retreat = crypto_momentum_retreat_active(
    bot_type,
    shadow_mode,
    graduation_nudge,
    bot_wr,
    per_bot_stats.get("profit_factor"),
    per_bot_stats.get("total_pnl"),
  )
  crypto_shadow_raw_floor = crypto_shadow_raw_signal_floor_active(
    bot_type,
    shadow_mode,
    graduation_nudge,
    bot_wr,
    per_bot_stats.get("profit_factor"),
    per_bot_stats.get("total_pnl"),
  )
  effective_min_signal = min_signal
  if crypto_momentum_retreat:
    effective_min_signal = max(
      min_signal,
      crypto_momentum_retreat_entry_min_signal(
        min_signal,
        bot_type=bot_type,
        graduation_nudge=graduation_nudge,
        shadow_mode=shadow_mode,
        bot_win_rate=bot_wr,
        profit_factor=per_bot_stats.get("profit_factor"),
        total_pnl=per_bot_stats.get("total_pnl"),
      ),
    )
  return {
    "bot_type": bot_type,
    "shadow_mode": shadow_mode,
    "graduation_nudge": graduation_nudge,
    "commodities_verification_trade_count_nudge": commodities_verification_nudge,
    "stocks_trade_count_nudge": stocks_trade_count_nudge,
    "stocks_gate_fast_scan_active": stocks_fast_scan_active,
    "stocks_open_imminent_scan": stocks_open_imminent,
    "commodities_gate_fast_scan_active": commodities_fast_scan_active,
    "commodities_reopen_imminent_scan": commodities_reopen_imminent,
    "crypto_strong_momentum_nudge": crypto_strong_momentum,
    "crypto_pre_graduation_nudge": crypto_pre_graduation,
    "crypto_cap_pressure_active": crypto_cap_pressure,
    "crypto_momentum_retreat": crypto_momentum_retreat,
    "crypto_momentum_retreat_min_signal": (
      round(effective_min_signal, 3) if crypto_momentum_retreat else None
    ),
    "crypto_momentum_retreat_aligned_composite_floor": (
      CRYPTO_MOMENTUM_RETREAT_ALIGNED_COMPOSITE_FLOOR
      if crypto_momentum_retreat
      else None
    ),
    "crypto_momentum_retreat_cap_room_aligned_composite_floor": (
      CRYPTO_MOMENTUM_RETREAT_CAP_ROOM_ALIGNED_COMPOSITE_FLOOR
      if crypto_momentum_retreat
      else None
    ),
    "crypto_chronic_loser_aligned_composite_floor": (
      CRYPTO_MOMENTUM_RETREAT_ALIGNED_COMPOSITE_FLOOR
      if crypto_momentum_retreat
      else None
    ),
    "crypto_momentum_retreat_max_open": (
      shadow_cap if crypto_momentum_retreat else None
    ),
    "crypto_momentum_retreat_min_raw_signal": (
      CRYPTO_MOMENTUM_RETREAT_ALIGNED_RAW_SIGNAL
      if crypto_momentum_retreat and crypto_shadow_raw_floor
      else CRYPTO_MOMENTUM_RETREAT_MIN_RAW_SIGNAL if crypto_shadow_raw_floor else None
    ),
    "crypto_momentum_retreat_aligned_raw_signal": (
      CRYPTO_MOMENTUM_RETREAT_ALIGNED_RAW_SIGNAL
      if crypto_momentum_retreat and crypto_shadow_raw_floor
      else None
    ),
    "crypto_momentum_retreat_cap_room_aligned_raw_signal": (
      CRYPTO_MOMENTUM_RETREAT_CAP_ROOM_ALIGNED_RAW_SIGNAL
      if crypto_momentum_retreat and crypto_shadow_raw_floor
      else None
    ),
    "crypto_momentum_retreat_loss_wind_down_usd": (
      CRYPTO_MOMENTUM_RETREAT_LOSS_WIND_DOWN_USD if crypto_momentum_retreat else None
    ),
    "crypto_momentum_retreat_cap_pressure_loser_usd": (
      CRYPTO_MOMENTUM_RETREAT_CAP_PRESSURE_LOSER_USD if crypto_momentum_retreat else None
    ),
    "crypto_momentum_retreat_cap_full_min_hold_seconds": (
      CRYPTO_MOMENTUM_RETREAT_CAP_FULL_MIN_HOLD_SECONDS if crypto_momentum_retreat else None
    ),
    "crypto_momentum_retreat_weak_signal_wind_down_max_upnl": (
      CRYPTO_MOMENTUM_RETREAT_WEAK_SIGNAL_WIND_DOWN_MAX_UPNL
      if crypto_momentum_retreat
      else None
    ),
    "commodities_gate_loss_wind_down_usd": (
      COMMODITIES_ACTIVE_GATE_LOSS_WIND_DOWN_USD
      if bot_type == "commodities" and not shadow_mode and graduation_nudge
      else None
    ),
    "commodities_graduation_pf_profit_lock_usd": (
      COMMODITIES_GRADUATION_PF_PROFIT_LOCK_USD
      if (
        bot_type == "commodities"
        and not shadow_mode
        and graduation_nudge
        and (per_bot_stats.get("profit_factor") or 0) < 1.3
      )
      else None
    ),
    "commodities_graduation_open_composite_floor": (
      commodities_recovery_composite_floor(graduation_nudge=True)
      if bot_type == "commodities" and not shadow_mode and graduation_nudge
      else None
    ),
    "commodities_high_composite_recovery_floor": (
      COMMODITIES_HIGH_COMPOSITE_RECOVERY_FLOOR
      if bot_type == "commodities" and not shadow_mode
      else None
    ),
    "stocks_trade_count_profit_lock_usd": (
      STOCKS_TRADE_COUNT_PROFIT_LOCK_USD
      if (
        bot_type == "stocks_futures"
        and shadow_mode
        and stocks_trade_count_nudge
        and (per_bot_stats.get("win_rate") or 0) >= 0.55
        and (per_bot_stats.get("profit_factor") or 0) < 1.0
      )
      else None
    ),
    "crypto_shadow_raw_floor_active": crypto_shadow_raw_floor,
    "early_verification_boost": early_verification_boost,
    "shadow_bot_wr": bot_wr if bot_wr is not None else shadow_bot_wr,
    "total_trades": int(per_bot_stats.get("total_trades") or 0),
    "proven_winners": sorted(proven_winners),
    "min_signal": round(effective_min_signal, 3),
    "open_count": open_count,
    "effective_open_cap": effective_open_cap,
    "shadow_open_cap": shadow_cap,
    "held_symbols": sorted(held_symbols),
    "session": session,
    "recovery_candidates": recovery_candidates,
    "open_ready_candidates": open_ready_candidates,
    "near_floor_candidates": near_floor_candidates,
    "symbols": previews,
  }


MONDAY_RECOVERY_BOT_TYPES = ("commodities", "stocks_futures")
MONDAY_RECOVERY_CACHE_TTL_SECONDS = 30
MONDAY_RECOVERY_PREP_CACHE_TTL_SECONDS = 60
MONDAY_RECOVERY_WATCH_CACHE_TTL_SECONDS = 15
_monday_recovery_cache: dict[str, Any] | None = None
_monday_recovery_cached_at: float = 0.0
_monday_recovery_build_lock = asyncio.Lock()


def _monday_recovery_cache_ttl_seconds() -> int:
  """Shorter cache during CME open-ready watch; longer when weekend is far from open."""
  from app.engines.gate_entry_guard import status_cache_ttl_seconds

  return status_cache_ttl_seconds(
    default_ttl=MONDAY_RECOVERY_CACHE_TTL_SECONDS,
    prep_ttl=MONDAY_RECOVERY_PREP_CACHE_TTL_SECONDS,
    watch_ttl=MONDAY_RECOVERY_WATCH_CACHE_TTL_SECONDS,
  )


def monday_recovery_cache_age_seconds() -> float | None:
  if _monday_recovery_cache is None:
    return None
  return round(time.monotonic() - _monday_recovery_cached_at, 1)


def monday_recovery_cache_fresh(max_age_seconds: float) -> bool:
  age = monday_recovery_cache_age_seconds()
  return age is not None and age < max_age_seconds


def clear_monday_recovery_cache() -> None:
  global _monday_recovery_cache, _monday_recovery_cached_at
  _monday_recovery_cache = None
  _monday_recovery_cached_at = 0.0


async def build_monday_recovery_summary(session: AsyncSession) -> dict[str, Any]:
  """Aggregate recovery-ready symbols across commodities and stocks for CRM overview."""
  global _monday_recovery_cache, _monday_recovery_cached_at
  now = time.monotonic()
  if (
    _monday_recovery_cache is not None
    and (now - _monday_recovery_cached_at) < _monday_recovery_cache_ttl_seconds()
  ):
    return dict(_monday_recovery_cache)

  if _monday_recovery_build_lock.locked() and _monday_recovery_cache is not None:
    stale = dict(_monday_recovery_cache)
    stale["recovery_cache_stale"] = True
    return stale

  async with _monday_recovery_build_lock:
    now = time.monotonic()
    if (
      _monday_recovery_cache is not None
      and (now - _monday_recovery_cached_at) < _monday_recovery_cache_ttl_seconds()
    ):
      return dict(_monday_recovery_cache)

    result = await _build_monday_recovery_summary(session)
    _monday_recovery_cache = result
    _monday_recovery_cached_at = time.monotonic()
    return dict(result)


async def _scan_preview_for_bot(bot_type: str) -> tuple[str, dict[str, Any]]:
  from app.database import SessionLocal

  async with SessionLocal() as bot_session:
    preview = await build_scan_preview(bot_session, bot_type)
    return bot_type, preview


async def _build_monday_recovery_summary(session: AsyncSession) -> dict[str, Any]:
  bots: dict[str, Any] = {}
  all_rows: list[dict[str, Any]] = []
  open_ready_rows: list[dict[str, Any]] = []
  near_floor_rows: list[dict[str, Any]] = []
  stocks_trade_count_nudge = False
  commodities_graduation_nudge = False
  commodities_verification_nudge = False

  preview_results = await asyncio.gather(
    *[_scan_preview_for_bot(bot_type) for bot_type in MONDAY_RECOVERY_BOT_TYPES]
  )

  for bot_type, preview in preview_results:
    if preview.get("error"):
      continue
    if bot_type == "stocks_futures":
      stocks_trade_count_nudge = bool(preview.get("stocks_trade_count_nudge"))
    if bot_type == "commodities":
      commodities_verification_nudge = bool(
        preview.get("commodities_verification_trade_count_nudge")
      )
      commodities_graduation_nudge = bool(preview.get("graduation_nudge"))

    candidates = preview.get("recovery_candidates") or []
    open_ready_symbols = [
      row for row in preview.get("symbols", []) if row.get("monday_open_ready")
    ]
    near_floor_symbols = [
      row for row in preview.get("symbols", []) if row.get("near_floor_candidate")
    ]
    bot_entry: dict[str, Any] = {
      "recovery_candidates": candidates,
      "session": preview.get("session"),
      "symbols": [],
      "open_ready_candidates": preview.get("open_ready_candidates") or [],
      "open_ready_symbols": open_ready_symbols,
      "near_floor_candidates": preview.get("near_floor_candidates") or [],
      "near_floor_symbols": near_floor_symbols,
      "stocks_trade_count_nudge": preview.get("stocks_trade_count_nudge"),
      "graduation_nudge": preview.get("graduation_nudge"),
      "commodities_verification_trade_count_nudge": preview.get(
        "commodities_verification_trade_count_nudge"
      ),
    }
    session_info = preview.get("session") or {}
    minutes_until_open = session_info.get("minutes_until_open")
    for row in open_ready_symbols:
      open_ready_rows.append(
        {
          "bot_type": bot_type,
          "symbol": row["symbol"],
          "composite": row.get("composite"),
          "direction": row.get("direction"),
          "macd": row.get("macd"),
          "blockers": row.get("blockers") or [],
          "minutes_until_open": minutes_until_open,
          "monday_gate_skip_ready": bool(row.get("monday_gate_skip_ready")),
          "verification_cooldown_bypass_ready": bool(
            row.get("verification_cooldown_bypass_ready")
          ),
          "verification_chronic_bypass_ready": bool(
            row.get("verification_chronic_bypass_ready")
          ),
        }
      )
    for row in near_floor_symbols:
      near_floor_rows.append(
        {
          "bot_type": bot_type,
          "symbol": row["symbol"],
          "composite": row.get("composite"),
          "direction": row.get("direction"),
          "macd": row.get("macd"),
          "blockers": row.get("blockers") or [],
          "minutes_until_open": minutes_until_open,
        }
      )
    if candidates:
      rows = [row for row in preview.get("symbols", []) if row.get("recovery_ready")]
      bot_entry["symbols"] = rows
      bots[bot_type] = bot_entry
      for row in rows:
        all_rows.append(
          {
            "bot_type": bot_type,
            "symbol": row["symbol"],
            "composite": row.get("composite"),
            "blockers": row.get("blockers") or [],
          }
        )
    elif bot_type == "stocks_futures" and stocks_trade_count_nudge:
      bots[bot_type] = bot_entry
    elif bot_type == "commodities" and (
      commodities_graduation_nudge or commodities_verification_nudge
    ):
      bots[bot_type] = bot_entry

  from app.engines.gate_entry_guard import (
    COMMODITIES_OPEN_READY_PREP_MINUTES,
    commodities_monday_open_ready,
    commodities_verification_open_ready,
    stocks_monday_open_ready,
  )
  from app.engines.session_open_log import get_prep_phase_state

  state = await get_prep_phase_state(session)
  existing_open_ready = {(row["bot_type"], row["symbol"]) for row in open_ready_rows}
  sticky_session_keys = {
    "commodities": "cme_reopen",
    "stocks_futures": "us_stocks_open",
  }
  for bot_type, preview in preview_results:
    if preview.get("error") or bot_type not in sticky_session_keys:
      continue
    session_key = sticky_session_keys[bot_type]
    prev_ready = (state.get(session_key) or {}).get("open_ready_symbols") or []
    extended_watch_symbols = (state.get(session_key) or {}).get("extended_watch_symbols") or []
    watch_symbols = extended_watch_symbols or prev_ready
    if not watch_symbols:
      continue
    graduation_nudge = bool(
      preview.get("graduation_nudge")
      or preview.get("commodities_verification_trade_count_nudge")
    )
    shadow_mode = bool(preview.get("shadow_mode"))
    session_info = preview.get("session") or {}
    minutes_until_open = session_info.get("minutes_until_open")
    symbol_rows = {row["symbol"]: row for row in preview.get("symbols", []) if row.get("symbol")}
    proven_winners = frozenset(preview.get("proven_winners") or [])
    bot_win_rate = preview.get("shadow_bot_wr")
    total_trades = int(preview.get("total_trades") or 0)
    for symbol in watch_symbols:
      if (bot_type, symbol) in existing_open_ready:
        continue
      row = symbol_rows.get(symbol)
      if not row:
        continue
      blockers = row.get("blockers") or []
      composite = row.get("composite")
      if composite is None:
        continue
      extended_watch = (
        bot_type == "commodities"
        and minutes_until_open is not None
        and minutes_until_open <= COMMODITIES_OPEN_READY_PREP_MINUTES
        and symbol in watch_symbols
      )
      sticky_ready = False
      if bot_type == "commodities":
        sticky_ready = commodities_monday_open_ready(
          bot_type=bot_type,
          shadow_mode=shadow_mode,
          symbol=symbol,
          composite=float(composite),
          signal_direction=str(row.get("direction") or ""),
          macd_signal=str(row.get("macd") or ""),
          blockers=blockers,
          graduation_nudge=commodities_graduation_nudge,
          sticky_queue=True,
          extended_sticky=extended_watch,
        ) or commodities_verification_open_ready(
          bot_type=bot_type,
          shadow_mode=shadow_mode,
          symbol=symbol,
          proven_winners=proven_winners,
          gate_status={},
          per_bot_stats={},
          composite=float(composite),
          signal_direction=str(row.get("direction") or ""),
          macd_signal=str(row.get("macd") or ""),
          blockers=blockers,
          sticky_queue=True,
          verification_nudge_active=commodities_verification_nudge,
        )
      elif bot_type == "stocks_futures":
        sticky_ready = stocks_monday_open_ready(
          bot_type=bot_type,
          shadow_mode=shadow_mode,
          symbol=symbol,
          proven_winners=proven_winners,
          bot_win_rate=bot_win_rate,
          composite=float(composite),
          signal_direction=str(row.get("direction") or ""),
          macd_signal=str(row.get("macd") or ""),
          blockers=blockers,
          total_trades=total_trades,
          sticky_queue=True,
        )
      if not sticky_ready:
        continue
      sticky_gate_skip = bool(row.get("monday_gate_skip_ready"))
      if bot_type == "stocks_futures" and not sticky_gate_skip:
        sticky_gate_skip = stocks_monday_gate_skip_bypass(
          bot_type=bot_type,
          shadow_mode=shadow_mode,
          symbol=symbol,
          proven_winners=proven_winners,
          bot_win_rate=bot_win_rate,
          total_trades=total_trades,
          signal_direction=str(row.get("direction") or ""),
          macd_signal=str(row.get("macd") or ""),
          composite=float(composite),
          sticky_queue=True,
        )
      open_ready_rows.append(
        {
          "bot_type": bot_type,
          "symbol": symbol,
          "composite": composite,
          "direction": row.get("direction"),
          "macd": row.get("macd"),
          "blockers": blockers,
          "minutes_until_open": minutes_until_open,
          "monday_gate_skip_ready": sticky_gate_skip,
          "sticky_queue": True,
          "extended_sticky": extended_watch,
        }
      )
      existing_open_ready.add((bot_type, symbol))

  return {
    "bots": bots,
    "all": all_rows,
    "open_ready": open_ready_rows,
    "near_floor": near_floor_rows,
    "recovery_candidates": [row["symbol"] for row in all_rows],
    "open_ready_candidates": [row["symbol"] for row in open_ready_rows],
    "near_floor_candidates": [row["symbol"] for row in near_floor_rows],
    "stocks_trade_count_nudge": stocks_trade_count_nudge,
    "commodities_graduation_nudge": commodities_graduation_nudge,
    "commodities_verification_trade_count_nudge": commodities_verification_nudge,
  }
