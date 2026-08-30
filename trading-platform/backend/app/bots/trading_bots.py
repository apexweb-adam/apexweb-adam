import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import SessionLocal
from app.engines.gate_entry_guard import (
  bot_min_sentiment,
  chronic_loser_blocks_shadow_entry,
  apply_entry_min_signal_ease,
  apply_gate_tightening_min_signal,
  early_verification_index_etf_entry_min_signal,
  early_verification_raw_signal_ok,
  get_chronic_loser_symbols,
  get_gate_entry_tightening,
  get_gate_skip_symbols,
  get_hard_gate_skip_components,
  get_proven_winner_symbols,
  early_verification_active,
  early_verification_macd_ok,
  gate_entry_guards_active,
  gate_position_scale,
  hard_skip_blocks_shadow_entry,
  bot_win_rate_for_graduation_nudge,
  commodities_graduation_entry_min_signal,
  commodities_weekend_spot_gate_skip_bypass,
  commodities_monday_futures_gate_skip_bypass,
  stocks_monday_gate_skip_bypass,
  commodities_session_info,
  crypto_graduation_entry_min_signal,
  crypto_momentum_retreat_entry_min_signal,
  crypto_momentum_retreat_raw_signal_ok,
  crypto_retreat_cap_full_min_hold,
  crypto_momentum_retreat_cooldown_bypass,
  crypto_momentum_retreat_weak_signal_wind_down,
  graduation_nudge_min_sentiment,
  graduation_nudge_sentiment_ok,
  in_shadow_graduation_nudge,
  intel_override_allows_long_entry,
  is_symbol_in_trade_cooldown,
  open_position_cap_blocks_entry,
  prioritize_commodities_monday_scan,
  prioritize_stocks_monday_scan,
  shadow_chronic_position_scale,
  shadow_graduation_min_hold_seconds,
  shadow_graduation_min_composite,
  shadow_graduation_loss_wind_down,
  shadow_cap_pressure_loser_wind_down,
  shadow_graduation_loss_exposure_blocks_entry,
  shadow_graduation_profit_lock,
  gate_cap_pressure_proxy_entry_blocked,
  gate_cap_pressure_proxy_wind_down,
  commodities_cap_pressure_loser_wind_down,
  commodities_monday_cap_pressure_flat_wind_down,
  EARLY_VERIFICATION_LOSS_WIND_DOWN_SECONDS,
  EARLY_VERIFICATION_LOSS_WIND_DOWN_USD,
  shadow_entry_min_signal,
  shadow_intel_composite_override,
  shadow_requires_macd,
  stocks_proven_winner_sentiment_gate_ok,
  stocks_negative_pf_blocks_entry,
  stocks_trade_count_entry_min_signal,
  stocks_trade_count_graduation_nudge,
  stocks_trade_count_min_sentiment,
  stocks_trade_count_volume_required,
  whale_memecoin_aligned,
  stocks_in_us_session,
  stocks_session_close_wind_down,
  stocks_session_info,
  commodities_weekend_stale_signal_exit_blocked,
  commodities_weekend_futures_entry_blocked,
  commodities_weekend_forex_entry_blocked,
  commodities_weekend_spot_entry_blocked,
  commodities_gold_proxy_duplicate_entry_blocked,
  commodities_gold_proxy_duplicate_wind_down,
  commodities_weekend_spot_post_profit_lock_entry_blocked,
  commodities_weekend_spot_post_lock_wind_down,
  GATE_INDEX_ETF_SYMBOLS,
  HardGateSkipSets,
)
from app.engines.integration_signals import get_integration_boost
from app.engines.intelligence_scoring import compute_bot_sentiment
from app.engines.learning_engine import LearningEngine
from app.engines.market_data import fetch_crypto_data, fetch_yfinance_data
from app.engines.polymarket_data import (
  canonical_pm_symbol,
  fetch_polymarket_data,
  find_pm_position,
  get_market_meta,
  get_polymarket_symbols,
  is_macro_relevant_market,
)
from app.engines.polymarket_signals import analyze_polymarket
from app.engines.paper_trading import PaperTradingEngine
from app.engines.price_validation import is_price_sane
from app.engines.signal_engine import SignalEngine
from app.models.entities import BotState, Trade


def _prioritize_symbols(symbols: list[str], proven: frozenset[str]) -> list[str]:
  """Scan proven winners first during gate so the active bot captures best setups early."""
  if not proven:
    return symbols
  winners = [s for s in symbols if s in proven]
  rest = [s for s in symbols if s not in proven]
  return winners + rest


class BaseBot(ABC):
  bot_type: str = "base"
  scan_interval: int = 30

  def __init__(self):
    self.signal_engine = SignalEngine()
    self.running = False
    self._symbol_cooldown_until: dict[str, datetime] = {}
    self._last_exit_reason: dict[str, str] = {}
    self._last_exit_after_loss: dict[str, bool] = {}
    self._prev_session_in_market: bool | None = None
    self._session_open_burst: bool = False

  def _cooldown_seconds(self, *, after_loss: bool) -> int | None:
    if self.bot_type == "crypto":
      return (
        settings.crypto_loss_cooldown_seconds
        if after_loss
        else settings.crypto_reentry_cooldown_seconds
      )
    if self.bot_type == "commodities":
      return (
        settings.commodities_loss_cooldown_seconds
        if after_loss
        else settings.commodities_reentry_cooldown_seconds
      )
    if self.bot_type == "stocks_futures":
      return (
        settings.stocks_loss_cooldown_seconds
        if after_loss
        else settings.stocks_reentry_cooldown_seconds
      )
    return None

  def _register_symbol_cooldown(
    self,
    symbol: str,
    *,
    after_loss: bool,
    reason: str | None = None,
  ) -> None:
    if not symbol:
      return
    if reason:
      self._last_exit_reason[symbol] = reason
    self._last_exit_after_loss[symbol] = after_loss
    seconds = self._cooldown_seconds(after_loss=after_loss)
    if seconds is None:
      return
    self._symbol_cooldown_until[symbol] = datetime.utcnow() + timedelta(seconds=seconds)

  @abstractmethod
  async def get_symbols(self) -> list[str]:
    pass

  @abstractmethod
  async def fetch_price_data(self, symbol: str) -> tuple[float, pd.DataFrame | None]:
    pass

  async def get_sentiment_score(self, symbol: str) -> float:
    score, _ = await self.get_sentiment_detail(symbol)
    return score

  async def get_sentiment_detail(
    self,
    symbol: str,
    *,
    session: AsyncSession | None = None,
  ) -> tuple[float, str]:
    if session is not None:
      return await compute_bot_sentiment(session, self.bot_type, symbol)
    async with SessionLocal() as owned:
      return await compute_bot_sentiment(owned, self.bot_type, symbol)

  async def scan_and_trade(self, *, allow_new_entries: bool = True) -> list[dict]:
    actions: list[dict] = []
    symbols = await self.get_symbols()
    shadow_mode = False

    async with SessionLocal() as session:
      from app.engines.gate_entry_guard import (
        SHADOW_MAX_OPEN,
        SHADOW_MIN_SENTIMENT_BOOST,
        SHADOW_POSITION_SCALE,
        shadow_entry_min_signal,
        shadow_requires_macd,
      )
      from app.engines.platform_settings import is_bot_paused

      shadow_mode = await is_bot_paused(session, self.bot_type)

      engine = PaperTradingEngine(session, self.bot_type)
      strategy = await engine.get_strategy()
      gate_tightening = await get_gate_entry_tightening(session)
      from app.engines.profitability_gate import ProfitabilityGate

      gate_status = await ProfitabilityGate(session).evaluate()
      entry_guards = gate_entry_guards_active(
        gate_tightening=gate_tightening,
        shadow_mode=shadow_mode,
        live_trading_ready=bool(gate_status.get("live_trading_ready")),
      )
      shadow_bot_wr: float | None = None
      per_bot_stats: dict[str, Any] = {}
      if shadow_mode or self.bot_type == "stocks_futures" or self.bot_type == "commodities":
        per_bot_all = await ProfitabilityGate(session).evaluate_per_bot()
        per_bot_stats = per_bot_all.get(self.bot_type) or {}
      if shadow_mode:
        shadow_bot_wr = float(per_bot_stats.get("win_rate") or 0)
      bot_wr = bot_win_rate_for_graduation_nudge(
        self.bot_type,
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
      commodities_graduation_nudge = False
      if entry_guards:
        chronic_losers = await get_chronic_loser_symbols(session, self.bot_type)
        hard_skip_sets = await get_hard_gate_skip_components(session, self.bot_type)
        if self.bot_type in ("stocks_futures", "commodities"):
          proven_winners = await get_proven_winner_symbols(session, self.bot_type)
          if self.bot_type == "commodities":
            commodities_graduation_nudge = in_shadow_graduation_nudge(
              self.bot_type,
              bot_wr,
              profit_factor=per_bot_stats.get("profit_factor"),
              total_pnl=per_bot_stats.get("total_pnl"),
            )
            symbols = prioritize_commodities_monday_scan(
              symbols,
              chronic_losers=chronic_losers,
              proven_winners=proven_winners,
              session_info=commodities_session_info(),
              graduation_nudge=commodities_graduation_nudge,
            )
          elif self.bot_type == "stocks_futures":
            stocks_trade_count_nudge = stocks_trade_count_graduation_nudge(
              self.bot_type,
              shadow_mode,
              per_bot_stats.get("win_rate"),
              int(per_bot_stats.get("total_trades") or 0),
            )
            symbols = prioritize_stocks_monday_scan(
              symbols,
              chronic_losers=chronic_losers,
              proven_winners=proven_winners,
              session_info=stocks_session_info(),
              trade_count_nudge=stocks_trade_count_nudge,
            )
          elif proven_winners:
            symbols = _prioritize_symbols(symbols, proven_winners)
      open_positions = await engine.get_open_positions()
      open_count = len(open_positions)
      held_symbols = [p.symbol for p in open_positions if p.symbol]
      if allow_new_entries:
        symbols = list(dict.fromkeys(held_symbols + symbols))
      else:
        symbols = held_symbols
      loss_streak = await engine.get_consecutive_losses()
      early_verification_boost = False
      min_signal = strategy.min_signal_score
      if shadow_mode:
        min_signal = shadow_entry_min_signal(
          self.bot_type,
          strategy.min_signal_score,
          bot_win_rate=bot_wr,
          profit_factor=per_bot_stats.get("profit_factor"),
          total_pnl=per_bot_stats.get("total_pnl"),
        )
      elif (
        self.bot_type == "commodities"
        and in_shadow_graduation_nudge(
          self.bot_type,
          bot_wr,
          profit_factor=per_bot_stats.get("profit_factor"),
          total_pnl=per_bot_stats.get("total_pnl"),
        )
      ):
        min_signal = shadow_entry_min_signal(
          self.bot_type,
          strategy.min_signal_score,
          bot_win_rate=bot_wr,
          profit_factor=per_bot_stats.get("profit_factor"),
          total_pnl=per_bot_stats.get("total_pnl"),
        )
      if gate_tightening.active and self.bot_type != "stocks_futures":
        min_signal = apply_gate_tightening_min_signal(
          min_signal,
          self.bot_type,
          gate_tightening=gate_tightening,
          graduation_nudge=in_shadow_graduation_nudge(
            self.bot_type,
            bot_wr,
            profit_factor=per_bot_stats.get("profit_factor"),
            total_pnl=per_bot_stats.get("total_pnl"),
          ),
          shadow_mode=shadow_mode,
          loss_streak=loss_streak,
        )
      min_sentiment = max(
        strategy.min_sentiment_score,
        bot_min_sentiment(self.bot_type, gate_tightening),
      )
      if shadow_mode:
        min_sentiment += SHADOW_MIN_SENTIMENT_BOOST
      if (
        allow_new_entries
        and self.bot_type == "stocks_futures"
        and not shadow_mode
      ):
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
      graduation_nudge = in_shadow_graduation_nudge(
        self.bot_type,
        bot_wr,
        profit_factor=per_bot_stats.get("profit_factor"),
        total_pnl=per_bot_stats.get("total_pnl"),
      )
      min_sentiment = graduation_nudge_min_sentiment(
        self.bot_type,
        min_sentiment,
        graduation_nudge=graduation_nudge,
        shadow_mode=shadow_mode,
        bot_win_rate=bot_wr,
        profit_factor=per_bot_stats.get("profit_factor"),
        total_pnl=per_bot_stats.get("total_pnl"),
      )
      from app.engines.gate_entry_guard import shadow_max_open_for_bot

      shadow_open_cap = shadow_max_open_for_bot(
        self.bot_type,
        shadow_mode=shadow_mode,
        bot_win_rate=bot_wr,
        profit_factor=per_bot_stats.get("profit_factor"),
        total_pnl=per_bot_stats.get("total_pnl"),
      )
      open_positions = await engine.get_open_positions()
      loss_exposure_block = shadow_graduation_loss_exposure_blocks_entry(
        open_positions,
        graduation_nudge=graduation_nudge,
        shadow_mode=shadow_mode,
        bot_type=self.bot_type,
        shadow_open_cap=shadow_open_cap,
        bot_win_rate=bot_wr,
        profit_factor=per_bot_stats.get("profit_factor"),
        total_pnl=per_bot_stats.get("total_pnl"),
      )
      strategy_params = {
        "rsi_oversold": strategy.rsi_oversold,
        "rsi_overbought": strategy.rsi_overbought,
      }
      weights = {
        "technical_weight": strategy.technical_weight,
        "sentiment_weight": strategy.sentiment_weight,
        "momentum_weight": strategy.momentum_weight,
      }

      prices: dict[str, float] = {}

      for symbol in symbols:
        price, df = await self.fetch_price_data(symbol)
        if price <= 0 or not is_price_sane(symbol, price):
          continue
        prices[symbol] = price

        signal = self.signal_engine.analyze(symbol, df, strategy_params)
        sentiment, sentiment_sources = await self.get_sentiment_detail(symbol, session=session)
        composite = self.signal_engine.composite_score(signal.score, sentiment, weights)
        integration_boost, integration_reason = await get_integration_boost(session, symbol)
        composite = max(0.0, composite + integration_boost)

        position = await engine.get_position(symbol)

        if position:
          from app.engines.market_data import reconcile_proxy_entry_levels

          reconcile_proxy_entry_levels(position, price)
          opened = position.opened_at
          if opened and opened.tzinfo is not None:
            opened = opened.replace(tzinfo=None)
          held_seconds = (datetime.utcnow() - opened).total_seconds() if opened else 9999
          min_hold = 0
          if self.bot_type == "crypto":
            min_hold = shadow_graduation_min_hold_seconds(
              self.bot_type,
              graduation_nudge=graduation_nudge,
              shadow_mode=shadow_mode,
              default_seconds=settings.crypto_min_hold_seconds,
            )
          elif self.bot_type == "commodities":
            min_hold = shadow_graduation_min_hold_seconds(
              self.bot_type,
              graduation_nudge=graduation_nudge,
              shadow_mode=shadow_mode,
              default_seconds=settings.commodities_min_hold_seconds,
            )
          allow_signal_exit = held_seconds >= min_hold

          if shadow_graduation_loss_wind_down(
            graduation_nudge=graduation_nudge,
            shadow_mode=shadow_mode,
            bot_type=self.bot_type,
            unrealized=(price - position.entry_price) * position.quantity,
            held_seconds=held_seconds,
            min_hold_seconds=min_hold,
            bot_win_rate=bot_wr,
            profit_factor=per_bot_stats.get("profit_factor"),
            total_pnl=per_bot_stats.get("total_pnl"),
          ):
            unrealized = (price - position.entry_price) * position.quantity
            label = "Shadow" if shadow_mode else "Gate"
            reason = (
              f"{label} graduation wind-down (uPnL ${unrealized:.2f}) | {signal.reason}"
            )
            result = await engine.sell(symbol, price, reason)
            if result:
              actions.append(result)
              if result.get("is_winner") is False:
                await self._analyze_loss(session, symbol)
                self._register_symbol_cooldown(symbol, after_loss=True, reason=reason)
              else:
                self._register_symbol_cooldown(symbol, after_loss=False, reason=reason)
            continue

          if shadow_cap_pressure_loser_wind_down(
            graduation_nudge=graduation_nudge,
            bot_type=self.bot_type,
            shadow_mode=shadow_mode,
            unrealized=(price - position.entry_price) * position.quantity,
            held_seconds=held_seconds,
            min_hold_seconds=crypto_retreat_cap_full_min_hold(
              min_hold,
              bot_type=self.bot_type,
              shadow_mode=shadow_mode,
              graduation_nudge=graduation_nudge,
              open_count=open_count,
              shadow_open_cap=shadow_open_cap,
              bot_win_rate=bot_wr,
              profit_factor=per_bot_stats.get("profit_factor"),
              total_pnl=per_bot_stats.get("total_pnl"),
            ),
            open_count=open_count,
            shadow_open_cap=shadow_open_cap,
            bot_win_rate=bot_wr,
            profit_factor=per_bot_stats.get("profit_factor"),
            total_pnl=per_bot_stats.get("total_pnl"),
          ):
            unrealized = (price - position.entry_price) * position.quantity
            reason = (
              f"Shadow cap-pressure loser wind-down (uPnL ${unrealized:.2f}) | {signal.reason}"
            )
            result = await engine.sell(symbol, price, reason)
            if result:
              actions.append(result)
              if result.get("is_winner") is False:
                await self._analyze_loss(session, symbol)
                self._register_symbol_cooldown(symbol, after_loss=True, reason=reason)
              else:
                self._register_symbol_cooldown(symbol, after_loss=False, reason=reason)
            continue

          if crypto_momentum_retreat_weak_signal_wind_down(
            graduation_nudge=graduation_nudge,
            bot_type=self.bot_type,
            shadow_mode=shadow_mode,
            composite=composite,
            unrealized=(price - position.entry_price) * position.quantity,
            held_seconds=held_seconds,
            min_hold_seconds=min_hold,
            open_count=open_count,
            shadow_open_cap=shadow_open_cap,
            bot_win_rate=bot_wr,
            profit_factor=per_bot_stats.get("profit_factor"),
            total_pnl=per_bot_stats.get("total_pnl"),
          ):
            unrealized = (price - position.entry_price) * position.quantity
            reason = (
              f"Shadow momentum retreat weak-signal wind-down "
              f"(composite {composite:.2f}, uPnL ${unrealized:.2f}) | {signal.reason}"
            )
            result = await engine.sell(symbol, price, reason)
            if result:
              actions.append(result)
              if result.get("is_winner") is False:
                await self._analyze_loss(session, symbol)
                self._register_symbol_cooldown(symbol, after_loss=True, reason=reason)
              else:
                self._register_symbol_cooldown(symbol, after_loss=False, reason=reason)
            continue

          if shadow_graduation_profit_lock(
            graduation_nudge=graduation_nudge,
            shadow_mode=shadow_mode,
            bot_type=self.bot_type,
            unrealized=(price - position.entry_price) * position.quantity,
            held_seconds=held_seconds,
            min_hold_seconds=min_hold,
            bot_win_rate=bot_wr,
            profit_factor=per_bot_stats.get("profit_factor"),
            total_pnl=per_bot_stats.get("total_pnl"),
            total_trades=int(per_bot_stats.get("total_trades") or 0),
            symbol=symbol,
            proven_winners=proven_winners,
            open_count=open_count,
            shadow_open_cap=shadow_open_cap,
          ):
            unrealized = (price - position.entry_price) * position.quantity
            label = "Shadow" if shadow_mode else "Gate"
            reason = (
              f"{label} graduation profit lock (uPnL ${unrealized:.2f}) | {signal.reason}"
            )
            result = await engine.sell(symbol, price, reason)
            if result:
              actions.append(result)
              if result.get("is_winner") is False:
                await self._analyze_loss(session, symbol)
                self._register_symbol_cooldown(symbol, after_loss=True, reason=reason)
              else:
                self._register_symbol_cooldown(symbol, after_loss=False, reason=reason)
            continue

          if commodities_gold_proxy_duplicate_wind_down(
            bot_type=self.bot_type,
            shadow_mode=shadow_mode,
            graduation_nudge=graduation_nudge,
            symbol=symbol,
            held_symbols=held_symbols,
            held_seconds=held_seconds,
            min_hold_seconds=min_hold,
          ):
            unrealized = (price - position.entry_price) * position.quantity
            reason = (
              f"Gold proxy dedup wind-down (uPnL ${unrealized:.2f}) | {signal.reason}"
            )
            result = await engine.sell(symbol, price, reason)
            if result:
              actions.append(result)
              if result.get("is_winner") is False:
                await self._analyze_loss(session, symbol)
                self._register_symbol_cooldown(symbol, after_loss=True, reason=reason)
              else:
                self._register_symbol_cooldown(symbol, after_loss=False, reason=reason)
            continue

          if await commodities_weekend_spot_post_lock_wind_down(
            session,
            bot_type=self.bot_type,
            shadow_mode=shadow_mode,
            graduation_nudge=graduation_nudge,
            symbol=symbol,
            unrealized=(price - position.entry_price) * position.quantity,
            held_seconds=held_seconds,
            min_hold_seconds=min_hold,
            position_opened_at=opened,
          ):
            unrealized = (price - position.entry_price) * position.quantity
            reason = (
              f"Weekend spot post-lock wind-down (uPnL ${unrealized:.2f}) | {signal.reason}"
            )
            result = await engine.sell(symbol, price, reason)
            if result:
              actions.append(result)
              if result.get("is_winner") is False:
                await self._analyze_loss(session, symbol)
                self._register_symbol_cooldown(symbol, after_loss=True, reason=reason)
              else:
                self._register_symbol_cooldown(symbol, after_loss=False, reason=reason)
            continue

          if gate_cap_pressure_proxy_wind_down(
            bot_type=self.bot_type,
            shadow_mode=shadow_mode,
            graduation_nudge=graduation_nudge,
            symbol=symbol,
            unrealized=(price - position.entry_price) * position.quantity,
            held_seconds=held_seconds,
            min_hold_seconds=min_hold,
            open_count=open_count,
            gate_tightening=gate_tightening,
            signal_direction=signal.direction,
          ):
            unrealized = (price - position.entry_price) * position.quantity
            reason = (
              f"Gate cap-pressure proxy wind-down (uPnL ${unrealized:.2f}) | {signal.reason}"
            )
            result = await engine.sell(symbol, price, reason)
            if result:
              actions.append(result)
              if result.get("is_winner") is False:
                await self._analyze_loss(session, symbol)
                self._register_symbol_cooldown(symbol, after_loss=True, reason=reason)
              else:
                self._register_symbol_cooldown(symbol, after_loss=False, reason=reason)
            continue

          if commodities_cap_pressure_loser_wind_down(
            bot_type=self.bot_type,
            shadow_mode=shadow_mode,
            graduation_nudge=graduation_nudge,
            symbol=symbol,
            unrealized=(price - position.entry_price) * position.quantity,
            held_seconds=held_seconds,
            min_hold_seconds=min_hold,
            open_count=open_count,
            gate_tightening=gate_tightening,
          ):
            unrealized = (price - position.entry_price) * position.quantity
            reason = (
              f"Gate cap-pressure loser wind-down (uPnL ${unrealized:.2f}) | {signal.reason}"
            )
            result = await engine.sell(symbol, price, reason)
            if result:
              actions.append(result)
              if result.get("is_winner") is False:
                await self._analyze_loss(session, symbol)
                self._register_symbol_cooldown(symbol, after_loss=True, reason=reason)
              else:
                self._register_symbol_cooldown(symbol, after_loss=False, reason=reason)
            continue

          if commodities_monday_cap_pressure_flat_wind_down(
            bot_type=self.bot_type,
            shadow_mode=shadow_mode,
            graduation_nudge=graduation_nudge,
            symbol=symbol,
            unrealized=(price - position.entry_price) * position.quantity,
            held_seconds=held_seconds,
            min_hold_seconds=min_hold,
            open_count=open_count,
            gate_tightening=gate_tightening,
          ):
            unrealized = (price - position.entry_price) * position.quantity
            reason = (
              f"Monday cap-pressure flat wind-down (uPnL ${unrealized:.2f}) | {signal.reason}"
            )
            result = await engine.sell(symbol, price, reason)
            if result:
              actions.append(result)
              if result.get("is_winner") is False:
                await self._analyze_loss(session, symbol)
                self._register_symbol_cooldown(symbol, after_loss=True, reason=reason)
              else:
                self._register_symbol_cooldown(symbol, after_loss=False, reason=reason)
            continue

          if self.bot_type == "stocks_futures":
            unrealized = (price - position.entry_price) * position.quantity
            session_info = stocks_session_info()
            if stocks_session_close_wind_down(
              in_session=session_info.get("in_session", False),
              minutes_until_close=session_info.get("minutes_until_close"),
              unrealized=unrealized,
              signal_direction=signal.direction,
            ):
              reason = (
                f"Session close wind-down: uPnL ${unrealized:.2f} | {signal.reason}"
              )
              result = await engine.sell(symbol, price, reason)
              if result:
                actions.append(result)
                if result.get("is_winner") is False:
                  await self._analyze_loss(session, symbol)
                  self._register_symbol_cooldown(symbol, after_loss=True, reason=reason)
                else:
                  self._register_symbol_cooldown(symbol, after_loss=False, reason=reason)
              continue

          if (
            early_verification_boost
            and self.bot_type == "stocks_futures"
          ):
            unrealized = (price - position.entry_price) * position.quantity
            if (
              unrealized <= -EARLY_VERIFICATION_LOSS_WIND_DOWN_USD
              and held_seconds >= EARLY_VERIFICATION_LOSS_WIND_DOWN_SECONDS
            ):
              reason = (
                f"Early verification wind-down (uPnL ${unrealized:.2f}) | {signal.reason}"
              )
              result = await engine.sell(symbol, price, reason)
              if result:
                actions.append(result)
                if result.get("is_winner") is False:
                  await self._analyze_loss(session, symbol)
                  self._register_symbol_cooldown(symbol, after_loss=True, reason=reason)
                else:
                  self._register_symbol_cooldown(symbol, after_loss=False, reason=reason)
              continue

          if (
            early_verification_boost
            and self.bot_type == "stocks_futures"
            and entry_guards
            and symbol in hard_skip_sets.all
          ):
            unrealized = (price - position.entry_price) * position.quantity
            wind_down = (
              unrealized > 0
              or signal.direction == "sell"
              or held_seconds >= 1800
            )
            if wind_down:
              reason = (
                f"Gate wind-down (skip-listed {symbol}): uPnL ${unrealized:.2f} | {signal.reason}"
              )
              result = await engine.sell(symbol, price, reason)
              if result:
                actions.append(result)
                if result.get("is_winner") is False:
                  await self._analyze_loss(session, symbol)
                  self._register_symbol_cooldown(symbol, after_loss=True, reason=reason)
                else:
                  self._register_symbol_cooldown(symbol, after_loss=False, reason=reason)
              continue

          # Wind down legacy stock positions opened before proven-winners-only gate.
          if (
            gate_tightening.active
            and self.bot_type == "stocks_futures"
            and proven_winners
            and symbol not in proven_winners
          ):
            unrealized = (price - position.entry_price) * position.quantity
            wind_down = (
              unrealized > 0
              or (unrealized < 0 and held_seconds >= 3600)
              or signal.direction == "sell"
              or signal.rsi >= 65
              or held_seconds >= 4 * 3600
            )
            if wind_down:
              reason = f"Gate wind-down (non-proven {symbol}): uPnL ${unrealized:.2f} | {signal.reason}"
              result = await engine.sell(symbol, price, reason)
              if result:
                actions.append(result)
                if result.get("is_winner") is False:
                  await self._analyze_loss(session, symbol)
                  self._register_symbol_cooldown(symbol, after_loss=True, reason=reason)
                else:
                  self._register_symbol_cooldown(symbol, after_loss=False, reason=reason)
              continue

          # Wind down legacy positions on bots blocked from gate — but not shadow graduation recovery.
          if (
            gate_tightening.active
            and self.bot_type in gate_tightening.blocked_new_entries
            and not (shadow_mode and graduation_nudge)
          ):
            unrealized = (price - position.entry_price) * position.quantity
            if position.side == "short":
              unrealized = (position.entry_price - price) * position.quantity
            wind_down = (
              unrealized > 0
              or (unrealized < 0 and held_seconds >= 3600)
              or signal.direction == "sell"
              or held_seconds >= 2 * 3600
            )
            if wind_down:
              reason = (
                f"Gate wind-down (blocked {self.bot_type}): uPnL ${unrealized:.2f} | {signal.reason}"
              )
              result = await engine.sell(symbol, price, reason)
              if result:
                actions.append(result)
                if result.get("is_winner") is False:
                  await self._analyze_loss(session, symbol)
                  self._register_symbol_cooldown(symbol, after_loss=True, reason=reason)
                else:
                  self._register_symbol_cooldown(symbol, after_loss=False, reason=reason)
              continue

          if allow_signal_exit and (signal.direction == "sell" or integration_boost < -0.1):
            unrealized = (price - position.entry_price) * position.quantity
            if commodities_weekend_stale_signal_exit_blocked(
              symbol=symbol,
              unrealized=unrealized,
              signal_direction=signal.direction,
            ):
              continue
            reason = f"Sell signal: {signal.reason}"
            if integration_reason:
              reason += f" | Integrations: {integration_reason}"
            result = await engine.sell(symbol, price, reason)
            if result:
              actions.append(result)
              if result.get("is_winner") is False:
                await self._analyze_loss(session, symbol)
                self._register_symbol_cooldown(symbol, after_loss=True, reason=reason)
              else:
                self._register_symbol_cooldown(symbol, after_loss=False, reason=reason)
          continue

        if not allow_new_entries:
          continue

        weekend_spot_cooldown_waived = commodities_weekend_spot_gate_skip_bypass(
          bot_type=self.bot_type,
          shadow_mode=shadow_mode,
          symbol=symbol,
          graduation_nudge=graduation_nudge,
          signal_direction=signal.direction,
          macd_signal=signal.macd_signal,
          composite=composite,
        )
        monday_commodities_cooldown_waived = commodities_monday_futures_gate_skip_bypass(
          bot_type=self.bot_type,
          shadow_mode=shadow_mode,
          symbol=symbol,
          graduation_nudge=graduation_nudge,
          signal_direction=signal.direction,
          macd_signal=signal.macd_signal,
          composite=composite,
        )
        monday_stocks_cooldown_waived = stocks_monday_gate_skip_bypass(
          bot_type=self.bot_type,
          shadow_mode=shadow_mode,
          symbol=symbol,
          proven_winners=proven_winners,
          bot_win_rate=per_bot_stats.get("win_rate"),
          total_trades=int(per_bot_stats.get("total_trades") or 0),
          signal_direction=signal.direction,
          macd_signal=signal.macd_signal,
          composite=composite,
        )
        retreat_cooldown_waived = crypto_momentum_retreat_cooldown_bypass(
          bot_type=self.bot_type,
          shadow_mode=shadow_mode,
          graduation_nudge=graduation_nudge,
          bot_win_rate=per_bot_stats.get("win_rate"),
          profit_factor=per_bot_stats.get("profit_factor"),
          total_pnl=per_bot_stats.get("total_pnl"),
          signal_direction=signal.direction,
          macd_signal=signal.macd_signal,
          composite=composite,
          open_count=open_count,
          shadow_open_cap=shadow_open_cap,
          last_exit_reason=self._last_exit_reason.get(symbol),
          last_exit_after_loss=self._last_exit_after_loss.get(symbol),
        )
        if (
          not weekend_spot_cooldown_waived
          and not monday_commodities_cooldown_waived
          and not monday_stocks_cooldown_waived
          and not retreat_cooldown_waived
        ):
          cooldown = self._symbol_cooldown_until.get(symbol)
          if cooldown and datetime.utcnow() < cooldown:
            continue
        if await is_symbol_in_trade_cooldown(
          session,
          self.bot_type,
          symbol,
          chronic_symbols=chronic_losers,
          large_loss_symbols=hard_skip_sets.large,
          graduation_nudge=graduation_nudge,
          shadow_mode=shadow_mode,
          signal_direction=signal.direction,
          macd_signal=signal.macd_signal,
          composite=composite,
          proven_winners=proven_winners,
          bot_win_rate=per_bot_stats.get("win_rate"),
          total_trades=int(per_bot_stats.get("total_trades") or 0),
          open_count=open_count,
          shadow_open_cap=shadow_open_cap,
          profit_factor=per_bot_stats.get("profit_factor"),
          total_pnl=per_bot_stats.get("total_pnl"),
        ):
          continue

        if (
          early_verification_boost
          and self.bot_type == "stocks_futures"
          and symbol in GATE_INDEX_ETF_SYMBOLS
          and proven_winners
          and symbol not in proven_winners
        ):
          continue

        if (
          (gate_tightening.active or early_verification_boost)
          and self.bot_type == "stocks_futures"
          and proven_winners
          and symbol not in proven_winners
        ):
          continue

        if (
          shadow_mode
          and self.bot_type == "commodities"
          and proven_winners
          and symbol not in proven_winners
          and not graduation_nudge
        ):
          continue

        if (
          (gate_tightening.active or early_verification_boost)
          and self.bot_type == "stocks_futures"
          and signal.rsi > 68
        ):
          continue

        if (
          early_verification_boost
          and self.bot_type == "stocks_futures"
          and not early_verification_macd_ok(
            macd_signal=signal.macd_signal,
            integration_boost=integration_boost,
          )
        ):
          continue

        if (
          gate_tightening.active
          and self.bot_type == "stocks_futures"
          and signal.macd_signal != "bullish"
          and integration_boost <= 0.03
        ):
          continue

        macd_required = shadow_requires_macd(
          self.bot_type,
          bot_win_rate=bot_wr,
          gate_tightening=gate_tightening,
          shadow_mode=shadow_mode,
          profit_factor=per_bot_stats.get("profit_factor"),
          total_pnl=per_bot_stats.get("total_pnl"),
        )
        if macd_required and signal.macd_signal != "bullish":
          continue

        if open_position_cap_blocks_entry(
          self.bot_type,
          shadow_mode=shadow_mode,
          open_count=open_count,
          gate_tightening=gate_tightening,
          shadow_open_cap=shadow_open_cap,
          graduation_nudge=graduation_nudge,
        ):
          continue

        entry_min_signal = min_signal
        if (
          (gate_tightening.active or early_verification_boost)
          and self.bot_type == "stocks_futures"
          and symbol in proven_winners
        ):
          entry_min_signal = apply_entry_min_signal_ease(
            entry_min_signal, 0.02, early_boost=early_verification_boost
          )
        if (
          (gate_tightening.active or early_verification_boost)
          and self.bot_type == "stocks_futures"
          and integration_reason
          and "tradingview" in integration_reason.lower()
          and integration_boost > 0.04
        ):
          entry_min_signal = apply_entry_min_signal_ease(
            entry_min_signal, 0.03, early_boost=early_verification_boost
          )
        if (
          (gate_tightening.active or early_verification_boost)
          and self.bot_type == "stocks_futures"
          and signal.rsi_divergence == "bullish"
        ):
          entry_min_signal = apply_entry_min_signal_ease(
            entry_min_signal, 0.02, early_boost=early_verification_boost
          )
        entry_min_signal = early_verification_index_etf_entry_min_signal(
          symbol,
          entry_min_signal,
          early_boost=early_verification_boost,
        )
        grad_composite_floor = shadow_graduation_min_composite(
          self.bot_type,
          graduation_nudge=graduation_nudge,
          shadow_mode=shadow_mode,
        )
        if grad_composite_floor is not None:
          entry_min_signal = max(entry_min_signal, grad_composite_floor)
        entry_min_signal = commodities_graduation_entry_min_signal(
          entry_min_signal,
          bot_type=self.bot_type,
          graduation_nudge=graduation_nudge,
          shadow_mode=shadow_mode,
          signal_direction=signal.direction,
          macd_signal=signal.macd_signal,
          symbol=symbol,
          proven_winners=proven_winners,
        )
        entry_min_signal = crypto_graduation_entry_min_signal(
          entry_min_signal,
          bot_type=self.bot_type,
          graduation_nudge=graduation_nudge,
          shadow_mode=shadow_mode,
          signal_direction=signal.direction,
          macd_signal=signal.macd_signal,
          bot_win_rate=per_bot_stats.get("win_rate"),
          profit_factor=per_bot_stats.get("profit_factor"),
          total_pnl=per_bot_stats.get("total_pnl"),
        )
        entry_min_signal = crypto_momentum_retreat_entry_min_signal(
          entry_min_signal,
          bot_type=self.bot_type,
          graduation_nudge=graduation_nudge,
          shadow_mode=shadow_mode,
          bot_win_rate=per_bot_stats.get("win_rate"),
          profit_factor=per_bot_stats.get("profit_factor"),
          total_pnl=per_bot_stats.get("total_pnl"),
          signal_direction=signal.direction,
          macd_signal=signal.macd_signal,
          open_count=open_count,
          shadow_open_cap=shadow_open_cap,
        )
        entry_min_signal = stocks_trade_count_entry_min_signal(
          entry_min_signal,
          bot_type=self.bot_type,
          shadow_mode=shadow_mode,
          symbol=symbol,
          proven_winners=proven_winners,
          bot_win_rate=per_bot_stats.get("win_rate"),
          total_trades=int(per_bot_stats.get("total_trades") or 0),
        )
        symbol_min_sentiment = stocks_trade_count_min_sentiment(
          min_sentiment,
          bot_type=self.bot_type,
          shadow_mode=shadow_mode,
          symbol=symbol,
          proven_winners=proven_winners,
          bot_win_rate=per_bot_stats.get("win_rate"),
          total_trades=int(per_bot_stats.get("total_trades") or 0),
          composite=composite,
        )

        intel_override = shadow_intel_composite_override(
          self.bot_type,
          graduation_nudge=graduation_nudge,
          shadow_mode=shadow_mode,
          composite=composite,
          entry_min_signal=entry_min_signal,
          integration_boost=integration_boost,
          whale_aligned=whale_memecoin_aligned(integration_reason, integration_boost),
          bot_win_rate=per_bot_stats.get("win_rate"),
          profit_factor=per_bot_stats.get("profit_factor"),
          total_pnl=per_bot_stats.get("total_pnl"),
        )

        if stocks_negative_pf_blocks_entry(
          bot_type=self.bot_type,
          symbol=symbol,
          composite=composite,
          proven_winners=proven_winners,
          profit_factor=per_bot_stats.get("profit_factor"),
          total_trades=int(per_bot_stats.get("total_trades") or 0),
          bot_win_rate=per_bot_stats.get("win_rate"),
        ):
          continue

        if entry_guards and hard_skip_blocks_shadow_entry(
          symbol,
          bot_type=self.bot_type,
          recent_skip=hard_skip_sets.recent,
          large_skip=hard_skip_sets.large,
          review_skip=hard_skip_sets.review,
          graduation_nudge=graduation_nudge,
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
          shadow_open_cap=shadow_open_cap,
        ):
          continue

        if chronic_loser_blocks_shadow_entry(
          symbol,
          chronic_losers,
          bot_type=self.bot_type,
          graduation_nudge=graduation_nudge,
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
          shadow_open_cap=shadow_open_cap,
        ):
          continue

        volume_required = signal.volume_confirmed
        if (
          (gate_tightening.active or early_verification_boost)
          and self.bot_type == "stocks_futures"
          and symbol in proven_winners
        ):
          # Proven winners: allow TV-boosted entries without strict volume bar
          volume_required = (
            signal.volume_confirmed
            or integration_boost > 0.03
            or bool(integration_reason and "tradingview" in integration_reason.lower())
          )
        if early_verification_boost and self.bot_type == "stocks_futures":
          volume_required = (
            signal.volume_confirmed
            or composite >= entry_min_signal + 0.03
            or integration_boost > 0.02
            or signal.macd_signal == "bullish"
            or bool(integration_reason and "tradingview" in integration_reason.lower())
          )
        if graduation_nudge and self.bot_type == "commodities":
          volume_required = (
            signal.volume_confirmed
            or composite >= entry_min_signal + 0.02
            or integration_boost > 0.02
            or signal.macd_signal == "bullish"
          )
        if graduation_nudge and shadow_mode and self.bot_type == "crypto":
          volume_required = (
            signal.volume_confirmed
            or composite >= entry_min_signal + 0.02
            or integration_boost > 0.02
            or signal.macd_signal == "bullish"
          )
        volume_required = stocks_trade_count_volume_required(
          volume_required,
          bot_type=self.bot_type,
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

        if (
          gate_tightening.active
          and self.bot_type == "stocks_futures"
          and not stocks_proven_winner_sentiment_gate_ok(
            bot_type=self.bot_type,
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
          continue

        if not early_verification_raw_signal_ok(
          signal.score,
          early_boost=early_verification_boost,
          bot_type=self.bot_type,
        ):
          continue

        if not crypto_momentum_retreat_raw_signal_ok(
          signal.score,
          bot_type=self.bot_type,
          graduation_nudge=graduation_nudge,
          shadow_mode=shadow_mode,
          bot_win_rate=per_bot_stats.get("win_rate"),
          profit_factor=per_bot_stats.get("profit_factor"),
          total_pnl=per_bot_stats.get("total_pnl"),
          composite=composite,
          signal_direction=signal.direction,
          macd_signal=signal.macd_signal,
          open_count=open_count,
          shadow_open_cap=shadow_open_cap,
        ):
          continue

        entry_direction_ok = (
          signal.direction == "buy"
          or intel_override_allows_long_entry(
            self.bot_type,
            intel_override=intel_override,
            signal_direction=signal.direction,
            shadow_mode=shadow_mode,
            graduation_nudge=graduation_nudge,
          )
        )

        if commodities_weekend_futures_entry_blocked(symbol):
          continue

        if commodities_weekend_forex_entry_blocked(
          bot_type=self.bot_type,
          shadow_mode=shadow_mode,
          symbol=symbol,
          graduation_nudge=graduation_nudge,
        ):
          continue

        if commodities_weekend_spot_entry_blocked(
          bot_type=self.bot_type,
          shadow_mode=shadow_mode,
          symbol=symbol,
          graduation_nudge=graduation_nudge,
        ):
          continue

        if commodities_gold_proxy_duplicate_entry_blocked(symbol, held_symbols):
          continue

        if await commodities_weekend_spot_post_profit_lock_entry_blocked(
          session,
          bot_type=self.bot_type,
          shadow_mode=shadow_mode,
          graduation_nudge=graduation_nudge,
          symbol=symbol,
        ):
          continue

        if gate_cap_pressure_proxy_entry_blocked(
          bot_type=self.bot_type,
          shadow_mode=shadow_mode,
          graduation_nudge=graduation_nudge,
          symbol=symbol,
          open_count=open_count,
          gate_tightening=gate_tightening,
        ):
          continue

        if (
          entry_direction_ok
          and volume_required
          and composite >= entry_min_signal
          and graduation_nudge_sentiment_ok(
            self.bot_type,
            graduation_nudge=graduation_nudge,
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
            bot_win_rate=per_bot_stats.get("win_rate"),
            profit_factor=per_bot_stats.get("profit_factor"),
            total_pnl=per_bot_stats.get("total_pnl"),
          )
          and (shadow_mode or self.bot_type not in gate_tightening.blocked_new_entries)
          and not loss_exposure_block
        ):
          reason = f"Signal:{signal.score:.2f} Sentiment:{sentiment:.2f}"
          if shadow_mode:
            reason = f"[shadow] {reason}"
          if intel_override:
            reason = f"[shadow-intel] {reason}"
          if sentiment_sources:
            reason += f" Intel:[{sentiment_sources}]"
          if integration_reason:
            reason += f" Integrations:{integration_boost:+.2f} ({integration_reason})"
          reason += f" | {signal.reason}"
          buy_scale = SHADOW_POSITION_SCALE if shadow_mode else 1.0
          if shadow_mode:
            buy_scale *= shadow_chronic_position_scale(
              symbol,
              chronic_losers,
              graduation_nudge=graduation_nudge,
              shadow_mode=shadow_mode,
              intel_override=intel_override,
            )
          if early_verification_boost and not shadow_mode:
            buy_scale *= gate_position_scale(
              composite, entry_min_signal, early_boost=True
            )
            if symbol in GATE_INDEX_ETF_SYMBOLS:
              buy_scale *= 0.5
          result = await engine.buy(
            symbol,
            price,
            composite,
            sentiment,
            reason,
            strategy=f"v{strategy.version}",
            position_scale=buy_scale,
          )
          if result:
            actions.append(result)
            open_count += 1
            held_symbols.append(symbol)

      stop_actions = await engine.update_positions(prices)
      actions.extend(stop_actions)

      for action in stop_actions:
        if action.get("is_winner") is False:
          await self._analyze_loss(session, action.get("symbol", ""))
          self._register_symbol_cooldown(action.get("symbol", ""), after_loss=True, reason=action.get("reason"))

    await self._record_scan_result(
      len(symbols),
      actions,
      "shadow — proving for graduation" if shadow_mode else None,
    )
    if getattr(self, "_session_open_burst", False):
      await self._record_session_open_burst(len(symbols), actions)

    if actions:
      from app.ws_manager import broadcast_trade, push_live_update

      for action in actions:
        await broadcast_trade({**action, "bot_type": self.bot_type})
      await push_live_update()

    return actions

  async def _analyze_loss(self, session, symbol: str) -> None:
    result = await session.execute(
      select(Trade)
      .where(Trade.bot_type == self.bot_type, Trade.symbol == symbol, Trade.action == "sell")
      .order_by(Trade.executed_at.desc())
      .limit(1)
    )
    trade = result.scalar_one_or_none()
    if trade and trade.is_winner is False:
      learner = LearningEngine(session)
      await learner.analyze_losing_trade(trade)

  async def _record_scan_heartbeat(self) -> None:
    async with SessionLocal() as session:
      result = await session.execute(
        select(BotState).where(BotState.bot_type == self.bot_type)
      )
      state = result.scalar_one_or_none()
      if not state:
        state = BotState(bot_type=self.bot_type, status="running")
        session.add(state)
      state.last_scan_at = datetime.utcnow()
      state.status = "running"
      if state.last_action.startswith("Paper reset"):
        state.last_action = "Scanning markets"
      state.updated_at = datetime.utcnow()
      await session.commit()

  async def _record_scan_result(self, symbol_count: int, actions: list[dict], detail: str = "") -> None:
    trade_actions = [a for a in actions if a.get("action") in ("buy", "sell")]
    if trade_actions:
      return
    async with SessionLocal() as session:
      result = await session.execute(
        select(BotState).where(BotState.bot_type == self.bot_type)
      )
      state = result.scalar_one_or_none()
      if not state:
        return
      if state.last_action.startswith(("BUY", "SELL", "PM:")):
        return
      summary = detail or "watching for signals"
      state.last_action = f"Scanned {symbol_count} symbols — {summary}"[:200]
      state.updated_at = datetime.utcnow()
      await session.commit()

  async def _record_scan_failure(self, error: str) -> None:
    async with SessionLocal() as session:
      result = await session.execute(
        select(BotState).where(BotState.bot_type == self.bot_type)
      )
      state = result.scalar_one_or_none()
      if not state:
        return
      state.last_action = f"Scan error — {error[:120]}"
      state.updated_at = datetime.utcnow()
      await session.commit()

  async def _record_session_open_burst(self, symbol_count: int, actions: list[dict]) -> None:
    """Log session-open burst scan and any auto-entries for CRM visibility."""
    from app.engines.session_open_log import record_session_open_event

    buys = [a for a in actions if a.get("action") == "buy"]
    buy_symbols = [a.get("symbol", "?") for a in buys]
    if buys:
      symbols = ", ".join(buy_symbols)
      summary = f"Session open auto-entry: {symbols}"
      event_type = "auto_entry"
    else:
      summary = f"Session open burst scan — {symbol_count} symbols, no entry yet"
      event_type = "burst_scan"
    async with SessionLocal() as session:
      result = await session.execute(
        select(BotState).where(BotState.bot_type == self.bot_type)
      )
      state = result.scalar_one_or_none()
      if not state:
        state = BotState(bot_type=self.bot_type, status="running")
        session.add(state)
      state.last_action = summary[:200]
      state.updated_at = datetime.utcnow()
      await session.commit()
    async with SessionLocal() as session:
      await record_session_open_event(
        session,
        bot_type=self.bot_type,
        event_type=event_type,
        symbols=buy_symbols if buys else [],
        symbol_count=symbol_count,
        detail=summary,
      )

  async def run_loop(self) -> None:
    self.running = True
    while self.running:
      try:
        await self._record_scan_heartbeat()
        await self.scan_and_trade()
      except Exception as e:
        print(f"[{self.bot_type}] Error in scan: {e}")
        await self._record_scan_failure(str(e))
      await asyncio.sleep(self.scan_interval)

  def stop(self) -> None:
    self.running = False


class CryptoBot(BaseBot):
  bot_type = "crypto"
  scan_interval = 20

  async def get_symbols(self) -> list[str]:
    base = [s.strip() for s in settings.crypto_symbols.split(",") if s.strip()]
    if not settings.fomo_hot_symbols_enabled and not settings.axiom_hot_symbols_enabled and not settings.phantom_hot_symbols_enabled:
      return base
    async with SessionLocal() as session:
      from app.intelligence.axiom_tracker import get_axiom_hot_symbols
      from app.intelligence.fomo_tracker import get_fomo_hot_symbols
      from app.intelligence.phantom_tracker import get_phantom_watch_symbols

      hot: list[str] = []
      if settings.fomo_hot_symbols_enabled:
        hot.extend(await get_fomo_hot_symbols(session))
      if settings.axiom_hot_symbols_enabled:
        for sym in await get_axiom_hot_symbols(session):
          if sym not in hot:
            hot.append(sym)
      if settings.phantom_hot_symbols_enabled:
        for sym in await get_phantom_watch_symbols(session):
          if sym not in hot:
            hot.append(sym)
    if not hot:
      return base
    merged = list(base)
    for sym in hot:
      if sym not in merged:
        merged.append(sym)
    return merged

  async def fetch_price_data(self, symbol: str) -> tuple[float, pd.DataFrame | None]:
    return await fetch_crypto_data(symbol, "15m")


class StocksFuturesBot(BaseBot):
  bot_type = "stocks_futures"
  scan_interval = 30
  gate_active_scan_interval = 15

  async def get_symbols(self) -> list[str]:
    stocks = [s.strip() for s in settings.stock_symbols.split(",")]
    futures = [s.strip() for s in settings.futures_symbols.split(",")]
    return stocks + futures

  async def fetch_price_data(self, symbol: str) -> tuple[float, pd.DataFrame | None]:
    return await fetch_yfinance_data(symbol)

  def _in_us_session(self) -> bool:
    return stocks_in_us_session()

  async def _effective_scan_interval(self) -> int:
    """Scan more often during US session, verification gate, or trade-count prep."""
    from app.config import settings
    from app.engines.gate_entry_guard import (
      bot_win_rate_for_graduation_nudge,
      stocks_effective_scan_interval,
      stocks_gate_fast_scan_active,
      stocks_session_info,
      stocks_trade_count_graduation_nudge,
    )
    from app.engines.profitability_gate import ProfitabilityGate

    session_info = stocks_session_info()
    in_session = self._in_us_session()
    trade_count_nudge = False
    gate_tightening_active = False
    use_gate_interval = in_session

    async with SessionLocal() as session:
      gate = await ProfitabilityGate(session).evaluate()
      per_bot = (await ProfitabilityGate(session).evaluate_per_bot()).get(
        "stocks_futures"
      ) or {}
      shadow_mode = bool(gate.get("shadow_mode"))
      bot_wr = bot_win_rate_for_graduation_nudge(
        "stocks_futures",
        shadow_mode=shadow_mode,
        shadow_bot_wr=per_bot.get("win_rate"),
        per_bot_stats=per_bot,
      )
      trade_count_nudge = stocks_trade_count_graduation_nudge(
        "stocks_futures",
        shadow_mode,
        bot_wr,
        int(per_bot.get("total_trades") or 0),
      )
      active_trades = int(gate.get("total_trades") or 0)
      tightening = await get_gate_entry_tightening(session)
      gate_tightening_active = tightening.active
      use_gate_interval = use_gate_interval or (
        settings.paper_trading_only and active_trades < ProfitabilityGate.MIN_TRADES
      ) or gate_tightening_active or trade_count_nudge

    prep_fast_scan = stocks_gate_fast_scan_active(
      session_info,
      trade_count_nudge=trade_count_nudge,
    )
    if not use_gate_interval and not prep_fast_scan:
      return self.scan_interval

    return stocks_effective_scan_interval(
      gate_active_interval=self.gate_active_scan_interval,
      default_interval=self.scan_interval,
      session_info=session_info,
      trade_count_nudge=trade_count_nudge,
      gate_tightening_active=gate_tightening_active,
      fast_scan=use_gate_interval or prep_fast_scan,
      in_session=in_session,
    )

  async def run_loop(self) -> None:
    self.running = True
    while self.running:
      from app.engines.gate_entry_guard import stocks_session_info

      session_info = stocks_session_info()
      in_session = bool(session_info.get("in_session"))
      burst = self._prev_session_in_market is False and in_session
      self._prev_session_in_market = in_session
      self._session_open_burst = burst
      try:
        await self._record_scan_heartbeat()
        await self.scan_and_trade()
      except Exception as e:
        print(f"[{self.bot_type}] Error in scan: {e}")
        await self._record_scan_failure(str(e))
      finally:
        self._session_open_burst = False
      if not burst:
        await asyncio.sleep(await self._effective_scan_interval())

  async def scan_and_trade(self) -> list[dict]:
    in_session = self._in_us_session()
    if not in_session:
      async with SessionLocal() as session:
        engine = PaperTradingEngine(session, self.bot_type)
        open_positions = await engine.get_open_positions()
        if not open_positions:
          symbols = await self.get_symbols()
          await self._record_scan_result(len(symbols), [], "outside US market hours")
          return []
    actions = await super().scan_and_trade(allow_new_entries=in_session)
    if in_session and not any(a.get("action") in ("buy", "sell") for a in actions):
      interval = await self._effective_scan_interval()
      if interval < self.scan_interval:
        async with SessionLocal() as session:
          gate_tightening = await get_gate_entry_tightening(session)
          if gate_tightening.active:
            symbols = await self.get_symbols()
            await self._record_scan_result(
              len(symbols),
              actions,
              f"US session · {interval}s scan · gate active",
            )
    return actions


class CommoditiesBot(BaseBot):
  bot_type = "commodities"
  scan_interval = 30
  gate_active_scan_interval = 15

  async def get_symbols(self) -> list[str]:
    yf_symbols = [s.strip() for s in settings.commodity_symbols.split(",")]
    crypto_fallback = ["PAXGUSDT", "XAUUSDT"]
    return yf_symbols + crypto_fallback

  async def fetch_price_data(self, symbol: str) -> tuple[float, pd.DataFrame | None]:
    if symbol.endswith("USDT"):
      return await fetch_crypto_data(symbol, "15m")
    return await fetch_yfinance_data(symbol)

  async def _effective_scan_interval(self) -> int:
    """Scan faster during CME session and graduation prep while gate is active."""
    from app.engines.gate_entry_guard import (
      bot_win_rate_for_graduation_nudge,
      commodities_effective_scan_interval,
      commodities_gate_fast_scan_active,
      commodities_session_info,
      in_shadow_graduation_nudge,
    )
    from app.engines.profitability_gate import ProfitabilityGate

    session_info = commodities_session_info()
    graduation_nudge = False
    fast_scan = commodities_gate_fast_scan_active(session_info)
    async with SessionLocal() as session:
      per_bot = (await ProfitabilityGate(session).evaluate_per_bot()).get("commodities") or {}
      bot_wr = bot_win_rate_for_graduation_nudge(
        "commodities",
        shadow_mode=False,
        shadow_bot_wr=None,
        per_bot_stats=per_bot,
      )
      graduation_nudge = in_shadow_graduation_nudge(
        "commodities",
        bot_wr,
        profit_factor=per_bot.get("profit_factor"),
        total_pnl=per_bot.get("total_pnl"),
      )
    if not fast_scan:
      fast_scan = commodities_gate_fast_scan_active(
        session_info,
        graduation_nudge=graduation_nudge,
      )
    gate_tightening_active = False
    if fast_scan:
      async with SessionLocal() as session:
        tightening = await get_gate_entry_tightening(session)
        gate_tightening_active = tightening.active
    return commodities_effective_scan_interval(
      gate_active_interval=self.gate_active_scan_interval,
      default_interval=self.scan_interval,
      session_info=session_info,
      graduation_nudge=graduation_nudge,
      gate_tightening_active=gate_tightening_active,
      fast_scan=fast_scan,
    )

  async def run_loop(self) -> None:
    self.running = True
    while self.running:
      from app.engines.gate_entry_guard import commodities_session_info

      session_info = commodities_session_info()
      in_session = bool(session_info.get("in_session"))
      burst = self._prev_session_in_market is False and in_session
      self._prev_session_in_market = in_session
      self._session_open_burst = burst
      try:
        await self._record_scan_heartbeat()
        await self.scan_and_trade()
      except Exception as e:
        print(f"[{self.bot_type}] Error in scan: {e}")
        await self._record_scan_failure(str(e))
      finally:
        self._session_open_burst = False
      if not burst:
        await asyncio.sleep(await self._effective_scan_interval())


class PolymarketBot(BaseBot):
  """Paper-trades Polymarket Yes shares — politics, crypto, sports, geopolitics, weather, etc."""

  bot_type = "polymarket"
  scan_interval = 45
  _symbol_cooldown_until: dict[str, datetime] = {}

  async def get_symbols(self) -> list[str]:
    return await get_polymarket_symbols()

  async def fetch_price_data(self, symbol: str) -> tuple[float, pd.DataFrame | None]:
    return await fetch_polymarket_data(symbol)

  def _register_symbol_cooldown(self, symbol: str, *, after_loss: bool) -> None:
    if not symbol:
      return
    seconds = (
      settings.polymarket_loss_cooldown_seconds
      if after_loss
      else settings.polymarket_reentry_cooldown_seconds
    )
    self._symbol_cooldown_until[symbol] = datetime.utcnow() + timedelta(seconds=seconds)

  async def scan_and_trade(self) -> list[dict]:
    actions: list[dict] = []
    symbols = await self.get_symbols()
    buy_candidates = 0
    best_buy_score = 0.0
    skipped = 0

    shadow_mode = False

    try:
      async with SessionLocal() as session:
        from app.engines.gate_entry_guard import (
          SHADOW_MAX_OPEN,
          SHADOW_MIN_SENTIMENT_BOOST,
          SHADOW_POSITION_SCALE,
          shadow_min_signal_boost,
        )
        from app.engines.platform_settings import is_bot_paused

        shadow_mode = await is_bot_paused(session, self.bot_type)
        engine = PaperTradingEngine(session, self.bot_type)
        strategy = await engine.get_strategy()
        gate_tightening = await get_gate_entry_tightening(session)
        gate_skip_symbols = (
          await get_gate_skip_symbols(session, self.bot_type)
          if gate_tightening.active
          else frozenset()
        )
        min_score = strategy.min_signal_score
        if shadow_mode:
          min_score = min(0.95, min_score + shadow_min_signal_boost(self.bot_type))
        if gate_tightening.active:
          min_score = min(0.95, min_score + gate_tightening.min_composite_boost)
        min_sentiment = max(
          strategy.min_sentiment_score,
          bot_min_sentiment(self.bot_type, gate_tightening),
        )
        if shadow_mode:
          min_sentiment += SHADOW_MIN_SENTIMENT_BOOST
        pm_position_cap = settings.polymarket_max_open_positions
        if gate_tightening.max_pm_open_positions is not None:
          pm_position_cap = min(pm_position_cap, gate_tightening.max_pm_open_positions)
        if shadow_mode:
          shadow_cap = SHADOW_MAX_OPEN.get("polymarket")
          if shadow_cap is not None:
            pm_position_cap = min(pm_position_cap, shadow_cap)
        open_positions = await engine.get_open_positions()
        pm_open = len(open_positions)
        prices: dict[str, float] = {}
        held_symbols = [p.symbol for p in open_positions]
        scan_symbols = list(dict.fromkeys(held_symbols + symbols))

        for symbol in scan_symbols:
          try:
            price, df = await self.fetch_price_data(symbol)
            if price <= 0 or not is_price_sane(symbol, price):
              continue

            meta = await get_market_meta(symbol)
            symbol = canonical_pm_symbol(symbol, meta)
            prices[symbol] = price

            question = (meta or {}).get("question", symbol)
            pm_sig = await analyze_polymarket(session, symbol, price, df, question)
            integration_boost, integration_reason = await get_integration_boost(session, symbol)
            composite = pm_sig.score + integration_boost

            position = find_pm_position(open_positions, symbol)

            if position:
              opened = position.opened_at
              if opened and opened.tzinfo is not None:
                opened = opened.replace(tzinfo=None)
              held_seconds = (datetime.utcnow() - opened).total_seconds() if opened else 9999

              if gate_tightening.active and "polymarket" in gate_tightening.blocked_new_entries:
                unrealized = (price - position.entry_price) * position.quantity
                wind_down = (
                  unrealized > 0
                  or pm_sig.direction == "sell"
                  or held_seconds >= 2 * 3600
                )
                if wind_down:
                  reason = f"Gate wind-down (blocked PM): uPnL ${unrealized:.2f} | {pm_sig.reason}"
                  result = await engine.sell(position.symbol, price, reason)
                  if result:
                    actions.append(result)
                    if result.get("is_winner") is False:
                      await self._analyze_loss(session, symbol)
                    self._register_symbol_cooldown(symbol, after_loss=result.get("is_winner") is False)
                  continue

              if position.stop_loss and price <= position.stop_loss:
                exit_price = position.stop_loss
                result = await engine.sell(
                  position.symbol,
                  exit_price,
                  f"Stop loss triggered at {exit_price:.4f}",
                )
                if result:
                  actions.append(result)
                  if result.get("is_winner") is False:
                    await self._analyze_loss(session, symbol)
                  self._register_symbol_cooldown(symbol, after_loss=result.get("is_winner") is False)
                continue

              min_hold_seconds = settings.polymarket_min_hold_seconds
              allow_signal_exit = (
                held_seconds >= min_hold_seconds
                and pm_sig.direction == "sell"
                and pm_sig.sentiment <= 0.05
                and (price >= 0.60 or (df is not None and len(df) >= 15))
              )
              if allow_signal_exit or integration_boost < -0.15:
                reason = f"PM exit: {pm_sig.reason}"
                if integration_reason:
                  reason += f" | {integration_reason}"
                result = await engine.sell(position.symbol, price, reason)
                if result:
                  actions.append(result)
                  won = result.get("is_winner")
                  if won is False:
                    await self._analyze_loss(session, symbol)
                  self._register_symbol_cooldown(symbol, after_loss=won is False)
              continue

            if symbol not in symbols:
              continue

            if find_pm_position(open_positions, symbol):
              continue

            cooldown = self._symbol_cooldown_until.get(symbol)
            if cooldown and datetime.utcnow() < cooldown:
              continue

            if pm_open >= pm_position_cap:
              continue

            if gate_tightening.active and symbol in gate_skip_symbols:
              continue

            if not meta or not is_macro_relevant_market(meta):
              continue

            if pm_sig.direction == "buy":
              buy_candidates += 1
              best_buy_score = max(best_buy_score, composite)

            if (
              pm_sig.direction == "buy"
              and composite >= min_score
              and pm_sig.sentiment + integration_boost >= min_sentiment
              and (shadow_mode or "polymarket" not in gate_tightening.blocked_new_entries)
            ):
              reason = f"PM:{pm_sig.reason}"
              if shadow_mode:
                reason = f"[shadow] {reason}"
              if integration_reason:
                reason += f" | {integration_reason}"
              result = await engine.buy(
                symbol,
                price,
                composite,
                pm_sig.sentiment,
                reason,
                strategy=f"v{strategy.version}",
                position_scale=SHADOW_POSITION_SCALE if shadow_mode else 1.0,
              )
              if result:
                actions.append(result)
                pm_open += 1
          except Exception as e:
            skipped += 1
            print(f"[polymarket] skip {symbol}: {e}")

        stop_actions = await engine.update_positions(prices)
        actions.extend(stop_actions)

        for action in stop_actions:
          if action.get("is_winner") is False:
            sym = action.get("symbol", "")
            await self._analyze_loss(session, sym)
            self._register_symbol_cooldown(sym, after_loss=True)
          else:
            sym = action.get("symbol", "")
            self._register_symbol_cooldown(sym, after_loss=False)
    except Exception as e:
      await self._record_scan_result(len(symbols), actions, f"failed — {e}")
      raise

    pm_detail = (
      f"{buy_candidates} buy signals (best {best_buy_score:.2f})"
      if buy_candidates
      else "shadow — proving for graduation" if shadow_mode else "no qualifying entries"
    )
    if skipped:
      pm_detail += f", {skipped} skipped"
    await self._record_scan_result(len(symbols), actions, pm_detail)

    if actions:
      from app.ws_manager import broadcast_trade, push_live_update

      for action in actions:
        await broadcast_trade({**action, "bot_type": self.bot_type})
      await push_live_update()

    return actions
