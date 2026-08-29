"""Tighten entry criteria when the verification gate win rate is below target."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import BOT_TYPES
from app.engines.profitability_gate import ProfitabilityGate


@dataclass(frozen=True)
class GateEntryTightening:
  active: bool
  win_rate: float
  min_sentiment: float
  require_macd_bullish: bool
  min_composite_boost: float
  max_pm_open_positions: int | None = None
  max_crypto_open_positions: int | None = None
  max_commodities_open_positions: int | None = None
  max_stocks_open_positions: int | None = None
  blocked_new_entries: frozenset[str] = frozenset()


BOT_MIN_SENTIMENT = {
  "crypto": 0.10,
  "commodities": 0.06,
  "stocks_futures": 0.04,
  "polymarket": 0.12,
}

SHADOW_POSITION_SCALE = 0.5
SHADOW_MIN_SIGNAL_BOOST = 0.10
SHADOW_MIN_SIGNAL_BOOST_BY_BOT = {
  "crypto": 0.12,
  "commodities": 0.14,
  "stocks_futures": 0.10,
  "polymarket": 0.12,
}
SHADOW_MIN_SENTIMENT_BOOST = 0.04
SHADOW_MAX_OPEN = {
  "crypto": 1,
  "commodities": 1,
  "stocks_futures": 2,
  "polymarket": 2,
}
SHADOW_GRADUATION_NUDGE_MAX_OPEN = 2
SHADOW_PROFITABLE_GRADUATION_NUDGE_MAX_OPEN = 3
ACTIVE_GATE_GRADUATION_NUDGE_MAX_OPEN = 3
GATE_RECOVERY_ROTATION_CANDIDATES = ("crypto", "commodities")
GATE_RECOVERY_MIN_PF = 1.0

GRADUATION_NUDGE_MIN_WR = 0.48
GRADUATION_NUDGE_MIN_WR_BY_BOT = {
  "crypto": 0.42,
  "commodities": 0.44,
}
PROFITABLE_SHADOW_NUDGE_MIN_WR = 0.42
PROFITABLE_SHADOW_MIN_PF = 0.95
SHADOW_GRADUATION_MIN_HOLD_BY_BOT = {
  "crypto": 900,
  "commodities": 600,
}
SHADOW_GRADUATION_MIN_COMPOSITE_BY_BOT = {
  "crypto": 0.26,
  "commodities": 0.28,
}
GRADUATION_NUDGE_LOSS_WIND_DOWN_USD = 3.5
PROFITABLE_SHADOW_LOSS_WIND_DOWN_USD = 4.0
SHADOW_GRADUATION_LOSS_EXPOSURE_MIN_LOSERS = 2
SHADOW_GRADUATION_LOSS_EXPOSURE_PER_POSITION_USD = 2.5
SHADOW_GRADUATION_LOSS_EXPOSURE_AGGREGATE_USD = 6.0
SHADOW_GRADUATION_LOSS_EXPOSURE_SINGLE_POSITION_USD = 2.5
GRADUATION_NUDGE_PROFIT_LOCK_USD = 3.0
COMMODITIES_PROVEN_WINNER_PROFIT_LOCK_USD = 2.0
COMMODITIES_GRADUATION_PF_PROFIT_LOCK_USD = 2.0
COMMODITIES_ACTIVE_GATE_LOSS_WIND_DOWN_USD = 2.0
PROFITABLE_SHADOW_PROFIT_LOCK_USD = 3.5
SHADOW_GRADUATION_LOSS_COOLDOWN_MULTIPLIER = 2
FEED_ARTIFACT_COOLDOWN_MULTIPLIER = 3
GRADUATION_NUDGE_SENTIMENT_EASE_BY_BOT = {
  "crypto": 0.04,
  "commodities": 0.02,
}
COMMODITIES_GRADUATION_BULLISH_SIGNAL_EASE = 0.09
COMMODITIES_GRADUATION_BULLISH_SIGNAL_FLOOR = 0.20
COMMODITIES_PROVEN_WINNER_SIGNAL_FLOOR = 0.12
COMMODITIES_PROVEN_WINNER_SIGNAL_EASE = 0.06
CRYPTO_GRADUATION_BULLISH_SIGNAL_EASE = 0.06
CRYPTO_GRADUATION_BULLISH_SIGNAL_FLOOR = 0.24
CRYPTO_SHADOW_REVIEW_BYPASS_COMPOSITE = 0.32
CRYPTO_SHADOW_COMPOSITE_SENTIMENT_MARGIN = 0.01
CRYPTO_SHADOW_BULLISH_SENTIMENT_COMPOSITE_FLOOR = 0.26
CRYPTO_NEAR_GRADUATION_PNL_FLOOR_USD = 10.0
CRYPTO_NEAR_GRADUATION_WR_FLOOR = 0.405
CRYPTO_NEAR_GRADUATION_PROFIT_LOCK_USD = 1.5
CRYPTO_NEAR_GRADUATION_CAP_PRESSURE_LOSER_USD = 0.35
CRYPTO_NEAR_GRADUATION_EARLY_PROFIT_LOCK_MULTIPLIER = 2.0
CRYPTO_NEAR_GRADUATION_EARLY_PROFIT_LOCK_MIN_HOLD_SECONDS = 60
CRYPTO_STRONG_MOMENTUM_MIN_WR = 0.47
CRYPTO_STRONG_MOMENTUM_MIN_PF = 1.15
CRYPTO_STRONG_MOMENTUM_CHRONIC_COMPOSITE = 0.42
CRYPTO_STRONG_MOMENTUM_LOSS_WIND_DOWN_USD = 2.5
CRYPTO_PRE_GRADUATION_MIN_WR = 0.50
CRYPTO_PRE_GRADUATION_MIN_PF = 1.20
CRYPTO_PRE_GRADUATION_LOSS_WIND_DOWN_USD = 2.0
CRYPTO_GRADUATION_ENTRY_EASE_MIN_WR = 0.47
CRYPTO_GRADUATION_ENTRY_EASE_MIN_PF = 1.10
CRYPTO_MOMENTUM_RETREAT_MIN_SIGNAL = 0.48
CRYPTO_MOMENTUM_RETREAT_ALIGNED_COMPOSITE_FLOOR = 0.43
CRYPTO_MOMENTUM_RETREAT_CAP_ROOM_ALIGNED_COMPOSITE_FLOOR = 0.36
CRYPTO_MOMENTUM_RETREAT_MIN_RAW_SIGNAL = 0.42
CRYPTO_MOMENTUM_RETREAT_ALIGNED_RAW_SIGNAL = 0.32
CRYPTO_MOMENTUM_RETREAT_CAP_ROOM_ALIGNED_RAW_SIGNAL = 0.24
CRYPTO_MOMENTUM_RETREAT_PROFIT_LOCK_USD = 1.25
CRYPTO_MOMENTUM_RETREAT_LOSS_WIND_DOWN_USD = 1.5
CRYPTO_MOMENTUM_RETREAT_CAP_PRESSURE_LOSER_USD = 0.35
CRYPTO_MOMENTUM_RETREAT_CAP_FULL_MIN_HOLD_SECONDS = 300
CRYPTO_MOMENTUM_RETREAT_LOSS_EXPOSURE_AGGREGATE_USD = 5.0
CRYPTO_MOMENTUM_RETREAT_MAX_OPEN = 2
CRYPTO_PRE_GRADUATION_CAP_PRESSURE_LOSER_USD = 1.5
CRYPTO_STRONG_MOMENTUM_CAP_PRESSURE_LOSER_USD = 1.0
CRYPTO_CAP_PRESSURE_MODERATE_LOSER_USD = 2.0
CRYPTO_CAP_PRESSURE_MODERATE_LOSER_MIN_HOLD_SECONDS = 300
CRYPTO_CAP_PRESSURE_LARGE_LOSER_USD = 4.0
CRYPTO_CAP_PRESSURE_LARGE_LOSER_MIN_HOLD_SECONDS = 180
CRYPTO_CAP_PRESSURE_SEVERE_LOSER_USD = 6.0
CRYPTO_CAP_PRESSURE_SEVERE_LOSER_MIN_HOLD_SECONDS = 60
CRYPTO_CAP_PRESSURE_PROFIT_LOCK_MIN_HOLD_SECONDS = 300
SHADOW_STRONG_MOMENTUM_MAX_OPEN = 4


def crypto_near_graduation_nudge(
  bot_type: str,
  shadow_mode: bool,
  bot_win_rate: float | None,
  profit_factor: float | None,
  total_pnl: float | None,
) -> bool:
  """Crypto shadow is near graduation WR with acceptable PF — rotate winners faster."""
  from app.engines.profitability_gate import ProfitabilityGate

  if not shadow_mode or bot_type != "crypto":
    return False
  if bot_win_rate is None or profit_factor is None or total_pnl is None:
    return False
  return (
    profit_factor >= PROFITABLE_SHADOW_MIN_PF
    and total_pnl > -CRYPTO_NEAR_GRADUATION_PNL_FLOOR_USD
    and bot_win_rate >= CRYPTO_NEAR_GRADUATION_WR_FLOOR
    and bot_win_rate < ProfitabilityGate.GRADUATION_MIN_WIN_RATE
  )


def crypto_strong_momentum_nudge(
  bot_type: str,
  shadow_mode: bool,
  bot_win_rate: float | None,
  profit_factor: float | None,
  total_pnl: float | None,
) -> bool:
  """Crypto shadow with graduation-tier WR/PF — stack winners and cut losers faster."""
  from app.engines.profitability_gate import ProfitabilityGate

  if not shadow_mode or bot_type != "crypto":
    return False
  if bot_win_rate is None or profit_factor is None or total_pnl is None:
    return False
  return (
    total_pnl > 0
    and profit_factor >= CRYPTO_STRONG_MOMENTUM_MIN_PF
    and bot_win_rate >= CRYPTO_STRONG_MOMENTUM_MIN_WR
    and bot_win_rate < ProfitabilityGate.GRADUATION_MIN_WIN_RATE
  )


def crypto_pre_graduation_nudge(
  bot_type: str,
  shadow_mode: bool,
  bot_win_rate: float | None,
  profit_factor: float | None,
  total_pnl: float | None,
) -> bool:
  """Crypto shadow at 50%+ WR and 1.2+ PF — tighten loss cuts to protect graduation path."""
  from app.engines.profitability_gate import ProfitabilityGate

  if not shadow_mode or bot_type != "crypto":
    return False
  if bot_win_rate is None or profit_factor is None or total_pnl is None:
    return False
  return (
    total_pnl > 0
    and profit_factor >= CRYPTO_PRE_GRADUATION_MIN_PF
    and bot_win_rate >= CRYPTO_PRE_GRADUATION_MIN_WR
    and bot_win_rate < ProfitabilityGate.GRADUATION_MIN_WIN_RATE
  )


def crypto_cap_pressure_nudge(
  bot_type: str,
  shadow_mode: bool,
  graduation_nudge: bool,
  bot_win_rate: float | None,
  profit_factor: float | None,
  total_pnl: float | None,
) -> bool:
  """Crypto shadow tiers that should free cap slots when full."""
  return (
    crypto_momentum_retreat_active(
      bot_type,
      shadow_mode,
      graduation_nudge,
      bot_win_rate=bot_win_rate,
      profit_factor=profit_factor,
      total_pnl=total_pnl,
    )
    or crypto_near_graduation_nudge(
      bot_type, shadow_mode, bot_win_rate, profit_factor, total_pnl
    )
    or crypto_strong_momentum_nudge(
      bot_type, shadow_mode, bot_win_rate, profit_factor, total_pnl
    )
    or crypto_pre_graduation_nudge(
      bot_type, shadow_mode, bot_win_rate, profit_factor, total_pnl
    )
  )


def crypto_cap_pressure_loser_threshold(
  bot_type: str,
  shadow_mode: bool,
  graduation_nudge: bool,
  bot_win_rate: float | None,
  profit_factor: float | None,
  total_pnl: float | None,
) -> float:
  """Per-tier loser threshold when shadow open cap is full."""
  thresholds: list[float] = []
  if crypto_momentum_retreat_active(
    bot_type,
    shadow_mode,
    graduation_nudge,
    bot_win_rate=bot_win_rate,
    profit_factor=profit_factor,
    total_pnl=total_pnl,
  ):
    thresholds.append(CRYPTO_MOMENTUM_RETREAT_CAP_PRESSURE_LOSER_USD)
  if crypto_pre_graduation_nudge(
    bot_type, shadow_mode, bot_win_rate, profit_factor, total_pnl
  ):
    thresholds.append(CRYPTO_PRE_GRADUATION_CAP_PRESSURE_LOSER_USD)
  if crypto_strong_momentum_nudge(
    bot_type, shadow_mode, bot_win_rate, profit_factor, total_pnl
  ):
    thresholds.append(CRYPTO_STRONG_MOMENTUM_CAP_PRESSURE_LOSER_USD)
  if crypto_near_graduation_nudge(
    bot_type, shadow_mode, bot_win_rate, profit_factor, total_pnl
  ):
    thresholds.append(CRYPTO_NEAR_GRADUATION_CAP_PRESSURE_LOSER_USD)
  if thresholds:
    return min(thresholds)
  return CRYPTO_NEAR_GRADUATION_CAP_PRESSURE_LOSER_USD


def crypto_cap_pressure_effective_min_hold(
  min_hold_seconds: int,
  unrealized: float,
) -> int:
  """Shorten min hold for larger losers when cap is full so slots rotate faster."""
  effective = min_hold_seconds
  if unrealized <= -CRYPTO_CAP_PRESSURE_SEVERE_LOSER_USD:
    return min(effective, CRYPTO_CAP_PRESSURE_SEVERE_LOSER_MIN_HOLD_SECONDS)
  if unrealized <= -CRYPTO_CAP_PRESSURE_LARGE_LOSER_USD:
    return min(effective, CRYPTO_CAP_PRESSURE_LARGE_LOSER_MIN_HOLD_SECONDS)
  if unrealized <= -CRYPTO_CAP_PRESSURE_MODERATE_LOSER_USD:
    return min(effective, CRYPTO_CAP_PRESSURE_MODERATE_LOSER_MIN_HOLD_SECONDS)
  return effective


def crypto_retreat_cap_full_min_hold(
  min_hold_seconds: int,
  *,
  bot_type: str,
  shadow_mode: bool,
  graduation_nudge: bool,
  open_count: int,
  shadow_open_cap: int | None,
  bot_win_rate: float | None = None,
  profit_factor: float | None = None,
  total_pnl: float | None = None,
) -> int:
  """Shorten min hold when retreat shadow cap is full so losers rotate faster."""
  if not crypto_momentum_retreat_active(
    bot_type,
    shadow_mode,
    graduation_nudge,
    bot_win_rate=bot_win_rate,
    profit_factor=profit_factor,
    total_pnl=total_pnl,
  ):
    return min_hold_seconds
  if shadow_open_cap is None or open_count < shadow_open_cap:
    return min_hold_seconds
  return min(min_hold_seconds, CRYPTO_MOMENTUM_RETREAT_CAP_FULL_MIN_HOLD_SECONDS)


def crypto_momentum_retreat_raw_signal_floor(
  *,
  bot_type: str,
  graduation_nudge: bool,
  shadow_mode: bool,
  bot_win_rate: float | None,
  profit_factor: float | None,
  total_pnl: float | None,
  composite: float,
  signal_direction: str,
  macd_signal: str,
  open_count: int | None = None,
  shadow_open_cap: int | None = None,
) -> float:
  """Raw signal floor used for retreat diagnostics and entry checks."""
  if crypto_momentum_retreat_gate_skip_bypass(
    bot_type=bot_type,
    shadow_mode=shadow_mode,
    graduation_nudge=graduation_nudge,
    bot_win_rate=bot_win_rate,
    profit_factor=profit_factor,
    total_pnl=total_pnl,
    signal_direction=signal_direction,
    macd_signal=macd_signal,
    composite=composite,
    open_count=open_count,
    shadow_open_cap=shadow_open_cap,
  ):
    if (
      open_count is not None
      and shadow_open_cap is not None
      and open_count < shadow_open_cap
    ):
      return CRYPTO_MOMENTUM_RETREAT_CAP_ROOM_ALIGNED_RAW_SIGNAL
    return CRYPTO_MOMENTUM_RETREAT_ALIGNED_RAW_SIGNAL
  if crypto_momentum_retreat_active(
    bot_type,
    shadow_mode,
    graduation_nudge,
    bot_win_rate=bot_win_rate,
    profit_factor=profit_factor,
    total_pnl=total_pnl,
  ) or crypto_graduation_entry_ease_active(
    bot_type,
    shadow_mode,
    bot_win_rate,
    profit_factor,
    total_pnl,
  ):
    return CRYPTO_MOMENTUM_RETREAT_MIN_RAW_SIGNAL
  return CRYPTO_MOMENTUM_RETREAT_MIN_RAW_SIGNAL


def crypto_graduation_entry_ease_active(
  bot_type: str,
  shadow_mode: bool,
  bot_win_rate: float | None,
  profit_factor: float | None,
  total_pnl: float | None,
) -> bool:
  """Crypto shadow only eases entry filters while momentum tiers are intact."""
  if not shadow_mode or bot_type != "crypto":
    return False
  if crypto_pre_graduation_nudge(
    bot_type, shadow_mode, bot_win_rate, profit_factor, total_pnl
  ):
    return True
  if crypto_strong_momentum_nudge(
    bot_type, shadow_mode, bot_win_rate, profit_factor, total_pnl
  ):
    return True
  if not crypto_near_graduation_nudge(
    bot_type, shadow_mode, bot_win_rate, profit_factor, total_pnl
  ):
    return False
  if bot_win_rate is None or profit_factor is None or total_pnl is None:
    return False
  return (
    total_pnl > 0
    and profit_factor >= CRYPTO_GRADUATION_ENTRY_EASE_MIN_PF
    and bot_win_rate >= CRYPTO_GRADUATION_ENTRY_EASE_MIN_WR
  )


def crypto_momentum_retreat_active(
  bot_type: str,
  shadow_mode: bool,
  graduation_nudge: bool,
  bot_win_rate: float | None = None,
  profit_factor: float | None = None,
  total_pnl: float | None = None,
) -> bool:
  """Crypto shadow in momentum retreat — WR/PF below entry-ease tier."""
  if not (graduation_nudge and shadow_mode and bot_type == "crypto"):
    return False
  if bot_win_rate is None or profit_factor is None or total_pnl is None:
    return False
  return not crypto_graduation_entry_ease_active(
    bot_type,
    shadow_mode,
    bot_win_rate,
    profit_factor,
    total_pnl,
  )


def shadow_min_signal_boost(
  bot_type: str,
  *,
  bot_win_rate: float | None = None,
  profit_factor: float | None = None,
  total_pnl: float | None = None,
) -> float:
  base = SHADOW_MIN_SIGNAL_BOOST_BY_BOT.get(bot_type, SHADOW_MIN_SIGNAL_BOOST)
  if bot_win_rate is None:
    return base
  if in_shadow_graduation_nudge(
    bot_type,
    bot_win_rate,
    profit_factor=profit_factor,
    total_pnl=total_pnl,
  ):
    if bot_type == "commodities":
      return max(0.08, base - 0.05)
    if bot_type == "crypto":
      return max(0.08, base - 0.02)
  return base


def is_profitable_graduation_nudge(
  bot_type: str,
  bot_win_rate: float | None,
  *,
  profit_factor: float | None = None,
  total_pnl: float | None = None,
) -> bool:
  """Paused/shadow bot is in graduation nudge with positive PF and PnL."""
  if bot_win_rate is None:
    return False
  return in_shadow_graduation_nudge(
    bot_type,
    bot_win_rate,
    profit_factor=profit_factor,
    total_pnl=total_pnl,
  ) and (
    profit_factor is not None
    and profit_factor >= PROFITABLE_SHADOW_MIN_PF
    and total_pnl is not None
    and total_pnl > 0
  )


def shadow_max_open_for_bot(
  bot_type: str,
  *,
  shadow_mode: bool,
  bot_win_rate: float | None = None,
  profit_factor: float | None = None,
  total_pnl: float | None = None,
) -> int | None:
  """Raise shadow open cap during graduation nudge so profitable bots can stack setups."""
  if not shadow_mode:
    return None
  base = SHADOW_MAX_OPEN.get(bot_type)
  if base is None:
    return None
  if crypto_strong_momentum_nudge(
    bot_type,
    shadow_mode,
    bot_win_rate,
    profit_factor,
    total_pnl,
  ):
    cap = max(base, SHADOW_STRONG_MOMENTUM_MAX_OPEN)
  elif (
    bot_type in ("crypto", "commodities")
    and is_profitable_graduation_nudge(
      bot_type,
      bot_win_rate,
      profit_factor=profit_factor,
      total_pnl=total_pnl,
    )
  ):
    cap = max(base, SHADOW_PROFITABLE_GRADUATION_NUDGE_MAX_OPEN)
  elif (
    crypto_near_graduation_nudge(
      bot_type,
      shadow_mode,
      bot_win_rate,
      profit_factor,
      total_pnl,
    )
  ):
    cap = max(base, SHADOW_PROFITABLE_GRADUATION_NUDGE_MAX_OPEN)
  elif in_shadow_graduation_nudge(
    bot_type,
    bot_win_rate,
    profit_factor=profit_factor,
    total_pnl=total_pnl,
  ):
    cap = max(base, SHADOW_GRADUATION_NUDGE_MAX_OPEN)
  else:
    cap = base
  graduation_nudge = in_shadow_graduation_nudge(
    bot_type,
    bot_win_rate,
    profit_factor=profit_factor,
    total_pnl=total_pnl,
  )
  if crypto_momentum_retreat_active(
    bot_type,
    shadow_mode,
    graduation_nudge,
    bot_win_rate,
    profit_factor,
    total_pnl,
  ):
    cap = min(cap, CRYPTO_MOMENTUM_RETREAT_MAX_OPEN)
  return cap


def commodities_effective_open_cap(
  cap: int | None,
  *,
  bot_type: str,
  graduation_nudge: bool,
  shadow_mode: bool,
) -> int | None:
  """Give commodities one extra slot during graduation nudge on weekends and Monday open hour."""
  if cap is None or bot_type != "commodities" or shadow_mode or not graduation_nudge:
    return cap
  if commodities_futures_weekend_closed():
    return cap + COMMODITIES_WEEKEND_GRADUATION_CAP_BONUS
  session = commodities_session_info()
  if session.get("in_session") and commodities_monday_scan_priority_active(
    session,
    graduation_nudge=graduation_nudge,
  ):
    return cap + COMMODITIES_WEEKEND_GRADUATION_CAP_BONUS
  return cap


def open_position_cap_blocks_entry(
  bot_type: str,
  *,
  shadow_mode: bool,
  open_count: int,
  gate_tightening: GateEntryTightening,
  shadow_open_cap: int | None,
  graduation_nudge: bool = False,
) -> bool:
  """Shadow bots use shadow_open_cap only — gate tightening caps apply to active gate bots."""
  if shadow_mode:
    return shadow_open_cap is not None and open_count >= shadow_open_cap
  gate_caps = {
    "crypto": gate_tightening.max_crypto_open_positions,
    "commodities": gate_tightening.max_commodities_open_positions,
    "stocks_futures": gate_tightening.max_stocks_open_positions,
    "polymarket": gate_tightening.max_pm_open_positions,
  }
  cap = commodities_effective_open_cap(
    gate_caps.get(bot_type),
    bot_type=bot_type,
    graduation_nudge=graduation_nudge,
    shadow_mode=shadow_mode,
  )
  if not isinstance(cap, int):
    return False
  return open_count >= cap


def in_shadow_graduation_nudge(
  bot_type: str,
  bot_win_rate: float | None,
  *,
  profit_factor: float | None = None,
  total_pnl: float | None = None,
) -> bool:
  """Paused bot is close to per-bot graduation WR — ease shadow filters."""
  if bot_win_rate is None:
    return False
  from app.engines.profitability_gate import ProfitabilityGate

  floor = GRADUATION_NUDGE_MIN_WR_BY_BOT.get(bot_type, GRADUATION_NUDGE_MIN_WR)
  if (
    bot_type in ("crypto", "commodities")
    and profit_factor is not None
    and profit_factor >= PROFITABLE_SHADOW_MIN_PF
    and total_pnl is not None
    and total_pnl > 0
    and bot_win_rate >= PROFITABLE_SHADOW_NUDGE_MIN_WR
  ):
    floor = min(floor, PROFITABLE_SHADOW_NUDGE_MIN_WR)
  if (
    bot_type == "crypto"
    and profit_factor is not None
    and profit_factor >= PROFITABLE_SHADOW_MIN_PF
    and total_pnl is not None
    and total_pnl > -CRYPTO_NEAR_GRADUATION_PNL_FLOOR_USD
    and bot_win_rate is not None
    and bot_win_rate >= CRYPTO_NEAR_GRADUATION_WR_FLOOR
  ):
    floor = min(floor, CRYPTO_NEAR_GRADUATION_WR_FLOOR)
  return (
    bot_type in ("commodities", "crypto")
    and floor <= bot_win_rate < ProfitabilityGate.GRADUATION_MIN_WIN_RATE
  )


ACTIVE_GATE_GRADUATION_NUDGE_BOTS = frozenset({"commodities"})


def bot_win_rate_for_graduation_nudge(
  bot_type: str,
  *,
  shadow_mode: bool,
  shadow_bot_wr: float | None,
  per_bot_stats: dict[str, Any],
) -> float | None:
  """Win rate used for graduation nudge — shadow bots or active gate commodities."""
  if shadow_mode:
    return shadow_bot_wr
  if bot_type in ACTIVE_GATE_GRADUATION_NUDGE_BOTS and per_bot_stats:
    wr = per_bot_stats.get("win_rate")
    if wr is None:
      return None
    return float(wr)
  return None


def graduation_nudge_easing_active(
  bot_type: str,
  *,
  graduation_nudge: bool,
  shadow_mode: bool,
) -> bool:
  """Graduation nudge entry easing for shadow bots and active gate commodities."""
  if not graduation_nudge:
    return False
  if shadow_mode:
    return bot_type in ("crypto", "commodities")
  return bot_type in ACTIVE_GATE_GRADUATION_NUDGE_BOTS


def shadow_graduation_exits_active(
  bot_type: str,
  *,
  graduation_nudge: bool,
  shadow_mode: bool,
  bot_win_rate: float | None = None,
) -> bool:
  """Keep shadow profit lock / wind-down active when WR dips just below nudge floor."""
  if graduation_nudge_easing_active(
    bot_type, graduation_nudge=graduation_nudge, shadow_mode=shadow_mode
  ):
    return True
  if not shadow_mode or bot_type not in ("crypto", "commodities"):
    return False
  if bot_win_rate is None:
    return False
  floor = GRADUATION_NUDGE_MIN_WR_BY_BOT.get(bot_type, GRADUATION_NUDGE_MIN_WR)
  return bot_win_rate >= floor - 0.03


SHADOW_INTEL_COMPOSITE_FLOOR = 0.50
SHADOW_INTEL_COMPOSITE_FLOOR_BY_BOT = {
  "crypto": 0.32,
  "commodities": 0.40,
}
SHADOW_INTEL_COMPOSITE_ONLY_BY_BOT = {
  "crypto": 0.46,
  "commodities": 0.48,
}
WHALE_ALIGNED_COMPOSITE_ONLY_BY_BOT = {
  "crypto": 0.40,
  "commodities": 0.44,
}
SHADOW_INTEL_CHRONIC_POSITION_SCALE = 0.25
SHADOW_CHRONIC_LOSS_COOLDOWN_MULTIPLIER = 2
LARGE_LOSS_COOLDOWN_MULTIPLIER_BY_BOT = {
  "stocks_futures": 3,
}
SHADOW_INTEL_BOOST_FLOOR = 0.08
SHADOW_INTEL_BOOST_FLOOR_BY_BOT = {
  "crypto": 0.06,
}
GATE_INDEX_ETF_SYMBOLS = frozenset({"SPY", "QQQ"})
EARLY_VERIFICATION_INDEX_ETF_SIGNAL_BONUS = 0.08
EARLY_VERIFICATION_MAX_TRADES = 30
EARLY_VERIFICATION_MIN_SIGNAL_FLOOR = 0.20
EARLY_VERIFICATION_ENTRY_MIN_SIGNAL_FLOOR = 0.18
EARLY_VERIFICATION_MIN_RAW_SIGNAL_SCORE = 0.12
EARLY_VERIFICATION_SIGNAL_EASE = 0.04
EARLY_VERIFICATION_SENTIMENT_EASE = 0.03
EARLY_VERIFICATION_LOSS_WIND_DOWN_USD = 15.0
EARLY_VERIFICATION_LOSS_WIND_DOWN_SECONDS = 7200
EARLY_VERIFICATION_MACD_INTEGRATION_BYPASS = 0.05
STOCKS_NEGATIVE_PF_MIN_COMPOSITE = 0.42
STOCKS_NEGATIVE_PF_HIGH_WR_MIN_COMPOSITE = 0.38
STOCKS_PROVEN_RECOVERY_MIN_COMPOSITE = 0.38
STOCKS_TRADE_COUNT_GRADUATION_GAP = 5
STOCKS_TRADE_COUNT_RECOVERY_MIN_COMPOSITE = 0.34
STOCKS_TRADE_COUNT_MIN_SENTIMENT = 0.05
STOCKS_TRADE_COUNT_PROFIT_LOCK_USD = 2.5
COMMODITIES_HIGH_COMPOSITE_RECOVERY_FLOOR = 0.48
COMMODITIES_GRADUATION_OPEN_COMPOSITE_FLOOR = 0.42
COMMODITIES_FUTURES_WEEKEND_FLAT_EXIT_BAND_USD = 1.0
COMMODITIES_WEEKEND_SPOT_SYMBOLS = frozenset({"XAUUSDT", "PAXGUSDT"})
COMMODITIES_GOLD_PROXY_PREFERRED = "XAUUSDT"
COMMODITIES_WEEKEND_SPOT_COOLDOWN_MULTIPLIER = 0.55
COMMODITIES_WEEKEND_SPOT_GATE_SKIP_COMPOSITE_FLOOR = 0.40
COMMODITIES_WEEKEND_GRADUATION_CAP_BONUS = 1
COMMODITIES_WEEKEND_SPOT_PROFIT_LOCK_USD = 1.0
COMMODITIES_WEEKEND_SPOT_POST_LOCK_BUFFER_MINUTES = 60
COMMODITIES_GOLD_PROXY_DEDUP_MIN_HOLD_SECONDS = 60
COMMODITIES_CAP_PRESSURE_LOSER_WIND_DOWN_USD = 0.35
COMMODITIES_MONDAY_CAP_PRESSURE_FLAT_BAND_USD = 0.15
STOCKS_SESSION_CLOSE_WIND_DOWN_MINUTES = 30
STOCKS_SESSION_CLOSE_FORCE_MINUTES = 15
DEFAULT_ENTRY_MIN_SIGNAL_FLOOR = 0.08


def stocks_trade_count_graduation_nudge(
  bot_type: str,
  shadow_mode: bool,
  bot_win_rate: float | None,
  total_trades: int,
) -> bool:
  """Stocks shadow has graduation WR but needs a few more trades — ease proven-winner entries."""
  from app.engines.profitability_gate import ProfitabilityGate

  if not (shadow_mode and bot_type == "stocks_futures"):
    return False
  if bot_win_rate is None or bot_win_rate < ProfitabilityGate.GRADUATION_MIN_WIN_RATE:
    return False
  gap = ProfitabilityGate.GRADUATION_MIN_TRADES - total_trades
  return 0 < gap <= STOCKS_TRADE_COUNT_GRADUATION_GAP


def stocks_trade_count_entry_min_signal(
  entry_min_signal: float,
  *,
  bot_type: str,
  shadow_mode: bool,
  symbol: str,
  proven_winners: frozenset[str],
  bot_win_rate: float | None,
  total_trades: int,
) -> float:
  """Cap proven-winner entry threshold during trade-count graduation nudge."""
  if symbol not in proven_winners:
    return entry_min_signal
  if not stocks_trade_count_graduation_nudge(
    bot_type, shadow_mode, bot_win_rate, total_trades
  ):
    return entry_min_signal
  return min(entry_min_signal, STOCKS_TRADE_COUNT_RECOVERY_MIN_COMPOSITE)


def stocks_trade_count_min_sentiment(
  base_min_sentiment: float,
  *,
  bot_type: str,
  shadow_mode: bool,
  symbol: str,
  proven_winners: frozenset[str],
  bot_win_rate: float | None,
  total_trades: int,
  composite: float,
) -> float:
  """Ease sentiment floor for proven winners nearing graduation trade count."""
  if symbol not in proven_winners:
    return base_min_sentiment
  if composite < STOCKS_TRADE_COUNT_RECOVERY_MIN_COMPOSITE:
    return base_min_sentiment
  if not stocks_trade_count_graduation_nudge(
    bot_type, shadow_mode, bot_win_rate, total_trades
  ):
    return base_min_sentiment
  return min(base_min_sentiment, STOCKS_TRADE_COUNT_MIN_SENTIMENT)


def stocks_trade_count_volume_required(
  volume_required: bool,
  *,
  bot_type: str,
  shadow_mode: bool,
  symbol: str,
  proven_winners: frozenset[str],
  bot_win_rate: float | None,
  total_trades: int,
  composite: float,
  entry_min_signal: float,
  macd_signal: str,
  integration_boost: float,
  integration_reason: str,
) -> bool:
  """Allow strong proven-winner entries without strict volume during trade-count nudge."""
  if volume_required:
    return True
  if not stocks_trade_count_graduation_nudge(
    bot_type, shadow_mode, bot_win_rate, total_trades
  ):
    return volume_required
  if symbol not in proven_winners:
    return volume_required
  if composite < STOCKS_TRADE_COUNT_RECOVERY_MIN_COMPOSITE:
    return volume_required
  return (
    composite >= entry_min_signal + 0.02
    or macd_signal == "bullish"
    or integration_boost > 0.02
    or bool(integration_reason and "tradingview" in integration_reason.lower())
  )


def early_verification_active(active_trades: int, active_wr: float) -> bool:
  from app.engines.profitability_gate import ProfitabilityGate

  return (
    active_trades < EARLY_VERIFICATION_MAX_TRADES
    and active_wr >= ProfitabilityGate.MIN_WIN_RATE
  )


def gate_position_scale(composite: float, entry_min_signal: float, *, early_boost: bool) -> float:
  """Scale down marginal gate entries so weak signals cannot blow up verification PnL."""
  if not early_boost:
    return 1.0
  margin = composite - entry_min_signal
  if margin >= 0.08:
    return 1.0
  if margin >= 0.04:
    return 0.75
  return 0.5


def whale_memecoin_aligned(integration_reason: str, integration_boost: float) -> bool:
  """True when whale/fomo social intel aligns with DexScreener or Hyperliquid on the same symbol."""
  reason = integration_reason.lower()
  if integration_boost < 0.10:
    return False
  has_social = "wallet" in reason or "fomo" in reason
  has_meme_intel = (
    "dexscreener" in reason
    or "hyperliquid" in reason
    or "memecoin_confluence" in reason
    or "fomo_leader_confluence" in reason.replace(" ", "_")
  )
  return has_social and has_meme_intel


def shadow_intel_composite_override(
  bot_type: str,
  *,
  graduation_nudge: bool,
  shadow_mode: bool,
  composite: float,
  entry_min_signal: float,
  integration_boost: float,
  whale_aligned: bool = False,
  bot_win_rate: float | None = None,
  profit_factor: float | None = None,
  total_pnl: float | None = None,
) -> bool:
  """Allow shadow long when intel composite is strong despite technical sell/hold."""
  if not graduation_nudge_easing_active(
    bot_type,
    graduation_nudge=graduation_nudge,
    shadow_mode=shadow_mode,
  ):
    return False
  if (
    bot_type == "crypto"
    and shadow_mode
    and not crypto_graduation_entry_ease_active(
      bot_type,
      shadow_mode,
      bot_win_rate,
      profit_factor,
      total_pnl,
    )
  ):
    return False
  if (
    bot_type == "crypto"
    and shadow_mode
    and crypto_shadow_raw_signal_floor_active(
      bot_type,
      shadow_mode,
      graduation_nudge,
      bot_win_rate,
      profit_factor,
      total_pnl,
    )
    and not whale_aligned
  ):
    return False
  composite_floor = SHADOW_INTEL_COMPOSITE_FLOOR_BY_BOT.get(
    bot_type, SHADOW_INTEL_COMPOSITE_FLOOR
  )
  composite_only_floor = SHADOW_INTEL_COMPOSITE_ONLY_BY_BOT.get(bot_type)
  if whale_aligned:
    whale_floor = WHALE_ALIGNED_COMPOSITE_ONLY_BY_BOT.get(bot_type)
    if whale_floor is not None and composite >= max(whale_floor, entry_min_signal + 0.08):
      return True
  if composite_only_floor is not None:
    if composite >= max(composite_only_floor, entry_min_signal + 0.12):
      return True
  boost_floor = SHADOW_INTEL_BOOST_FLOOR_BY_BOT.get(bot_type, SHADOW_INTEL_BOOST_FLOOR)
  if whale_aligned:
    boost_floor = max(0.04, boost_floor - 0.02)
  composite_margin = 0.05 if bot_type == "crypto" else 0.15
  if whale_aligned and bot_type == "crypto":
    composite_margin = 0.03
  return (
    composite >= max(entry_min_signal + composite_margin, composite_floor)
    and integration_boost >= boost_floor
  )


def intel_override_allows_long_entry(
  bot_type: str,
  *,
  intel_override: bool,
  signal_direction: str,
  shadow_mode: bool,
  graduation_nudge: bool,
) -> bool:
  """Intel override opens longs only when direction aligns — blocks bearish commodity churn."""
  if not intel_override:
    return False
  if signal_direction == "buy":
    return True
  if signal_direction == "sell":
    if (
      bot_type == "commodities"
      and not shadow_mode
      and graduation_nudge
    ):
      return False
    return bot_type in ("crypto", "commodities") and shadow_mode
  return True


def graduation_nudge_min_sentiment(
  bot_type: str,
  base_min_sentiment: float,
  *,
  graduation_nudge: bool,
  shadow_mode: bool,
  bot_win_rate: float | None = None,
  profit_factor: float | None = None,
  total_pnl: float | None = None,
) -> float:
  """Ease sentiment floor during graduation nudge for shadow and active gate bots."""
  if not graduation_nudge:
    return base_min_sentiment
  ease = GRADUATION_NUDGE_SENTIMENT_EASE_BY_BOT.get(bot_type, 0.0)
  if ease <= 0:
    return base_min_sentiment
  if shadow_mode and bot_type == "crypto":
    if not crypto_graduation_entry_ease_active(
      bot_type,
      shadow_mode,
      bot_win_rate,
      profit_factor,
      total_pnl,
    ):
      return base_min_sentiment
    return max(0.0, base_min_sentiment - ease)
  if shadow_mode and bot_type == "commodities":
    return max(0.0, base_min_sentiment - ease)
  if not shadow_mode and bot_type in ACTIVE_GATE_GRADUATION_NUDGE_BOTS:
    return max(0.0, base_min_sentiment - ease)
  return base_min_sentiment


def commodities_graduation_entry_min_signal(
  entry_min_signal: float,
  *,
  bot_type: str,
  graduation_nudge: bool,
  shadow_mode: bool,
  signal_direction: str,
  macd_signal: str,
  symbol: str,
  proven_winners: frozenset[str],
) -> float:
  """Ease entry threshold for aligned bullish commodities during graduation nudge."""
  if not (graduation_nudge and bot_type == "commodities"):
    return entry_min_signal
  eased = entry_min_signal
  if (
    not shadow_mode
    and signal_direction == "buy"
    and macd_signal == "bullish"
  ):
    eased = max(
      COMMODITIES_GRADUATION_BULLISH_SIGNAL_FLOOR,
      eased - COMMODITIES_GRADUATION_BULLISH_SIGNAL_EASE,
    )
  if symbol in proven_winners:
    eased = max(
      COMMODITIES_GRADUATION_BULLISH_SIGNAL_FLOOR,
      eased - 0.03,
    )
    if not shadow_mode:
      eased = max(
        COMMODITIES_PROVEN_WINNER_SIGNAL_FLOOR,
        eased - COMMODITIES_PROVEN_WINNER_SIGNAL_EASE,
      )
  return eased


def crypto_graduation_entry_min_signal(
  entry_min_signal: float,
  *,
  bot_type: str,
  graduation_nudge: bool,
  shadow_mode: bool,
  signal_direction: str,
  macd_signal: str,
  bot_win_rate: float | None = None,
  profit_factor: float | None = None,
  total_pnl: float | None = None,
) -> float:
  """Ease entry threshold for aligned bullish shadow crypto during graduation nudge."""
  if not (graduation_nudge and shadow_mode and bot_type == "crypto"):
    return entry_min_signal
  if not crypto_graduation_entry_ease_active(
    bot_type,
    shadow_mode,
    bot_win_rate,
    profit_factor,
    total_pnl,
  ):
    return entry_min_signal
  if signal_direction == "buy" and macd_signal == "bullish":
    return max(
      CRYPTO_GRADUATION_BULLISH_SIGNAL_FLOOR,
      entry_min_signal - CRYPTO_GRADUATION_BULLISH_SIGNAL_EASE,
    )
  return entry_min_signal


def crypto_momentum_retreat_composite_floor(
  signal_direction: str = "buy",
  macd_signal: str = "bullish",
  *,
  open_count: int | None = None,
  shadow_open_cap: int | None = None,
) -> float:
  """Per-setup composite floor during crypto momentum retreat."""
  if signal_direction == "buy" and macd_signal == "bullish":
    if (
      open_count is not None
      and shadow_open_cap is not None
      and open_count < shadow_open_cap
    ):
      return CRYPTO_MOMENTUM_RETREAT_CAP_ROOM_ALIGNED_COMPOSITE_FLOOR
    return CRYPTO_MOMENTUM_RETREAT_ALIGNED_COMPOSITE_FLOOR
  return CRYPTO_MOMENTUM_RETREAT_MIN_SIGNAL


def crypto_momentum_retreat_entry_min_signal(
  entry_min_signal: float,
  *,
  bot_type: str,
  graduation_nudge: bool,
  shadow_mode: bool,
  bot_win_rate: float | None = None,
  profit_factor: float | None = None,
  total_pnl: float | None = None,
  signal_direction: str = "buy",
  macd_signal: str = "bullish",
  open_count: int | None = None,
  shadow_open_cap: int | None = None,
) -> float:
  """Raise composite floor during crypto momentum retreat — block marginal cap rotations."""
  if not (graduation_nudge and shadow_mode and bot_type == "crypto"):
    return entry_min_signal
  if crypto_graduation_entry_ease_active(
    bot_type,
    shadow_mode,
    bot_win_rate,
    profit_factor,
    total_pnl,
  ):
    return entry_min_signal
  retreat_floor = crypto_momentum_retreat_composite_floor(
    signal_direction,
    macd_signal,
    open_count=open_count,
    shadow_open_cap=shadow_open_cap,
  )
  return max(entry_min_signal, retreat_floor)


def crypto_momentum_retreat_raw_signal_ok(
  signal_score: float,
  *,
  bot_type: str,
  graduation_nudge: bool,
  shadow_mode: bool,
  bot_win_rate: float | None = None,
  profit_factor: float | None = None,
  total_pnl: float | None = None,
  composite: float | None = None,
  signal_direction: str = "buy",
  macd_signal: str = "bullish",
  open_count: int | None = None,
  shadow_open_cap: int | None = None,
) -> bool:
  """Block TV-inflated composite entries when raw technical score is weak.

  Applies during momentum retreat and during entry-ease tier until pre-graduation WR.
  Aligned retreat setups with strong composite use a lower raw floor.
  """
  if not (graduation_nudge and shadow_mode and bot_type == "crypto"):
    return True
  if bot_win_rate is not None and bot_win_rate >= CRYPTO_PRE_GRADUATION_MIN_WR:
    return True
  retreat = crypto_momentum_retreat_active(
    bot_type,
    shadow_mode,
    graduation_nudge,
    bot_win_rate,
    profit_factor,
    total_pnl,
  )
  ease = crypto_graduation_entry_ease_active(
    bot_type,
    shadow_mode,
    bot_win_rate,
    profit_factor,
    total_pnl,
  )
  if not retreat and not ease:
    return True
  if composite is not None and crypto_momentum_retreat_gate_skip_bypass(
    bot_type=bot_type,
    shadow_mode=shadow_mode,
    graduation_nudge=graduation_nudge,
    bot_win_rate=bot_win_rate,
    profit_factor=profit_factor,
    total_pnl=total_pnl,
    signal_direction=signal_direction,
    macd_signal=macd_signal,
    composite=composite,
    open_count=open_count,
    shadow_open_cap=shadow_open_cap,
  ):
    floor = crypto_momentum_retreat_raw_signal_floor(
      bot_type=bot_type,
      graduation_nudge=graduation_nudge,
      shadow_mode=shadow_mode,
      bot_win_rate=bot_win_rate,
      profit_factor=profit_factor,
      total_pnl=total_pnl,
      composite=composite,
      signal_direction=signal_direction,
      macd_signal=macd_signal,
      open_count=open_count,
      shadow_open_cap=shadow_open_cap,
    )
    return signal_score >= floor
  return signal_score >= CRYPTO_MOMENTUM_RETREAT_MIN_RAW_SIGNAL


def crypto_momentum_retreat_gate_skip_bypass(
  *,
  bot_type: str,
  shadow_mode: bool,
  graduation_nudge: bool,
  bot_win_rate: float | None,
  profit_factor: float | None,
  total_pnl: float | None,
  signal_direction: str,
  macd_signal: str,
  composite: float,
  open_count: int | None = None,
  shadow_open_cap: int | None = None,
) -> bool:
  """Crypto shadow momentum retreat bypasses recent gate_skip on aligned setups."""
  if not crypto_momentum_retreat_active(
    bot_type,
    shadow_mode,
    graduation_nudge,
    bot_win_rate,
    profit_factor,
    total_pnl,
  ):
    return False
  if signal_direction != "buy" or macd_signal != "bullish":
    return False
  return composite >= crypto_momentum_retreat_composite_floor(
    signal_direction,
    macd_signal,
    open_count=open_count,
    shadow_open_cap=shadow_open_cap,
  )


def crypto_momentum_retreat_cooldown_bypass(
  *,
  bot_type: str,
  shadow_mode: bool,
  graduation_nudge: bool,
  bot_win_rate: float | None,
  profit_factor: float | None,
  total_pnl: float | None,
  signal_direction: str,
  macd_signal: str,
  composite: float,
  open_count: int | None = None,
  shadow_open_cap: int | None = None,
  last_exit_reason: str | None = None,
  last_exit_after_loss: bool | None = None,
) -> bool:
  """Waive re-entry cooldown for aligned retreat setups when cap has room or after cap-pressure rotation."""
  if not crypto_momentum_retreat_gate_skip_bypass(
    bot_type=bot_type,
    shadow_mode=shadow_mode,
    graduation_nudge=graduation_nudge,
    bot_win_rate=bot_win_rate,
    profit_factor=profit_factor,
    total_pnl=total_pnl,
    signal_direction=signal_direction,
    macd_signal=macd_signal,
    composite=composite,
    open_count=open_count,
    shadow_open_cap=shadow_open_cap,
  ):
    return False
  if last_exit_reason and "cap-pressure" in last_exit_reason:
    return True
  if open_count is not None and shadow_open_cap is not None:
    if open_count < shadow_open_cap:
      # Do not immediately re-enter the same symbol after a loss when cap has room.
      if last_exit_after_loss:
        return False
      return True
  return False


def crypto_shadow_raw_signal_floor_active(
  bot_type: str,
  shadow_mode: bool,
  graduation_nudge: bool,
  bot_win_rate: float | None = None,
  profit_factor: float | None = None,
  total_pnl: float | None = None,
) -> bool:
  """Whether shadow crypto enforces the minimum raw technical signal floor."""
  if not (graduation_nudge and shadow_mode and bot_type == "crypto"):
    return False
  if bot_win_rate is not None and bot_win_rate >= CRYPTO_PRE_GRADUATION_MIN_WR:
    return False
  return crypto_momentum_retreat_active(
    bot_type,
    shadow_mode,
    graduation_nudge,
    bot_win_rate,
    profit_factor,
    total_pnl,
  ) or crypto_graduation_entry_ease_active(
    bot_type,
    shadow_mode,
    bot_win_rate,
    profit_factor,
    total_pnl,
  )


def graduation_nudge_sentiment_ok(
  bot_type: str,
  *,
  graduation_nudge: bool,
  shadow_mode: bool,
  sentiment: float,
  integration_boost: float,
  min_sentiment: float,
  composite: float,
  entry_min_signal: float,
  signal_direction: str = "buy",
  macd_signal: str = "bullish",
  symbol: str | None = None,
  proven_winners: frozenset[str] | None = None,
  bot_win_rate: float | None = None,
  profit_factor: float | None = None,
  total_pnl: float | None = None,
) -> bool:
  """Allow strong-composite shadow crypto entries during graduation nudge despite weak sentiment."""
  if sentiment + integration_boost >= min_sentiment:
    return True
  crypto_ease = crypto_graduation_entry_ease_active(
    bot_type,
    shadow_mode,
    bot_win_rate,
    profit_factor,
    total_pnl,
  )
  if (
    graduation_nudge
    and shadow_mode
    and bot_type == "crypto"
    and crypto_ease
    and composite >= entry_min_signal + CRYPTO_SHADOW_COMPOSITE_SENTIMENT_MARGIN
  ):
    return True
  if (
    graduation_nudge
    and shadow_mode
    and bot_type == "crypto"
    and crypto_ease
    and signal_direction == "buy"
    and macd_signal == "bullish"
    and composite >= CRYPTO_SHADOW_BULLISH_SENTIMENT_COMPOSITE_FLOOR
  ):
    return True
  if (
    graduation_nudge
    and shadow_mode
    and bot_type == "crypto"
    and crypto_momentum_retreat_gate_skip_bypass(
      bot_type=bot_type,
      shadow_mode=shadow_mode,
      graduation_nudge=graduation_nudge,
      bot_win_rate=bot_win_rate,
      profit_factor=profit_factor,
      total_pnl=total_pnl,
      signal_direction=signal_direction,
      macd_signal=macd_signal,
      composite=composite,
    )
  ):
    return True
  if (
    graduation_nudge
    and not shadow_mode
    and bot_type == "commodities"
    and symbol
    and proven_winners
    and symbol in proven_winners
    and signal_direction == "buy"
    and macd_signal == "bullish"
    and composite >= COMMODITIES_PROVEN_WINNER_SIGNAL_FLOOR
  ):
    return True
  return False


def chronic_loser_blocks_shadow_entry(
  symbol: str,
  chronic_symbols: frozenset[str],
  *,
  bot_type: str,
  graduation_nudge: bool,
  shadow_mode: bool,
  intel_override: bool,
  proven_winners: frozenset[str] | None = None,
  bot_win_rate: float | None = None,
  composite: float | None = None,
  signal_direction: str | None = None,
  macd_signal: str | None = None,
  total_trades: int = 0,
  profit_factor: float | None = None,
  total_pnl: float | None = None,
  open_count: int | None = None,
  shadow_open_cap: int | None = None,
) -> bool:
  """Chronic losers are skippable during graduation nudge when intel override applies."""
  if symbol not in chronic_symbols:
    return False
  if stocks_proven_winner_recovery_entry_ok(
    bot_type=bot_type,
    shadow_mode=shadow_mode,
    symbol=symbol,
    proven_winners=proven_winners or frozenset(),
    bot_win_rate=bot_win_rate,
    composite=composite or 0.0,
    signal_direction=signal_direction or "buy",
    macd_signal=macd_signal or "bullish",
    total_trades=total_trades,
  ):
    return False
  if commodities_high_composite_recovery_entry_ok(
    bot_type=bot_type,
    shadow_mode=shadow_mode,
    symbol=symbol,
    composite=composite or 0.0,
    signal_direction=signal_direction or "buy",
    macd_signal=macd_signal or "bullish",
    graduation_nudge=graduation_nudge,
  ):
    return False
  if commodities_weekend_spot_gate_skip_bypass(
    bot_type=bot_type,
    shadow_mode=shadow_mode,
    symbol=symbol,
    graduation_nudge=graduation_nudge,
    signal_direction=signal_direction or "buy",
    macd_signal=macd_signal or "bullish",
    composite=composite or 0.0,
  ):
    return False
  if commodities_monday_futures_gate_skip_bypass(
    bot_type=bot_type,
    shadow_mode=shadow_mode,
    symbol=symbol,
    graduation_nudge=graduation_nudge,
    signal_direction=signal_direction or "buy",
    macd_signal=macd_signal or "bullish",
    composite=composite or 0.0,
  ):
    return False
  if stocks_monday_gate_skip_bypass(
    bot_type=bot_type,
    shadow_mode=shadow_mode,
    symbol=symbol,
    proven_winners=proven_winners or frozenset(),
    bot_win_rate=bot_win_rate,
    total_trades=total_trades,
    signal_direction=signal_direction or "buy",
    macd_signal=macd_signal or "bullish",
    composite=composite or 0.0,
  ):
    return False
  if crypto_momentum_retreat_gate_skip_bypass(
    bot_type=bot_type,
    shadow_mode=shadow_mode,
    graduation_nudge=graduation_nudge,
    bot_win_rate=bot_win_rate,
    profit_factor=profit_factor,
    total_pnl=total_pnl,
    signal_direction=signal_direction or "buy",
    macd_signal=macd_signal or "bullish",
    composite=composite or 0.0,
    open_count=open_count,
    shadow_open_cap=shadow_open_cap,
  ):
    return False
  if (
    crypto_strong_momentum_nudge(
      bot_type,
      shadow_mode,
      bot_win_rate,
      profit_factor,
      total_pnl,
    )
    and (composite or 0.0) >= CRYPTO_STRONG_MOMENTUM_CHRONIC_COMPOSITE
    and (signal_direction or "buy") == "buy"
    and (macd_signal or "bullish") == "bullish"
  ):
    return False
  if graduation_nudge_easing_active(
    bot_type,
    graduation_nudge=graduation_nudge,
    shadow_mode=shadow_mode,
  ) and intel_override:
    return False
  return True


def shadow_chronic_position_scale(
  symbol: str,
  chronic_symbols: frozenset[str],
  *,
  graduation_nudge: bool,
  shadow_mode: bool,
  intel_override: bool,
) -> float:
  """Reduce shadow size on chronic losers when intel override allows re-entry."""
  if (
    symbol in chronic_symbols
    and graduation_nudge
    and shadow_mode
    and intel_override
  ):
    return SHADOW_INTEL_CHRONIC_POSITION_SCALE
  return 1.0


def shadow_graduation_min_hold_seconds(
  bot_type: str,
  *,
  graduation_nudge: bool,
  shadow_mode: bool,
  default_seconds: int,
) -> int:
  """Longer min hold during graduation nudge to avoid intel-override churn."""
  if graduation_nudge_easing_active(
    bot_type, graduation_nudge=graduation_nudge, shadow_mode=shadow_mode
  ):
    return SHADOW_GRADUATION_MIN_HOLD_BY_BOT.get(bot_type, default_seconds)
  return default_seconds


def shadow_graduation_min_composite(
  bot_type: str,
  *,
  graduation_nudge: bool,
  shadow_mode: bool,
) -> float | None:
  """Absolute composite floor during graduation nudge — blocks weak eased entries."""
  if graduation_nudge:
    return SHADOW_GRADUATION_MIN_COMPOSITE_BY_BOT.get(bot_type)
  return None


def early_verification_macd_ok(
  *,
  macd_signal: str,
  integration_boost: float,
) -> bool:
  """Early verification stocks need MACD alignment unless TV integration is strong."""
  if macd_signal == "bullish":
    return True
  return integration_boost > EARLY_VERIFICATION_MACD_INTEGRATION_BYPASS


def shadow_graduation_loss_wind_down(
  *,
  graduation_nudge: bool,
  shadow_mode: bool,
  bot_type: str,
  unrealized: float,
  held_seconds: float,
  min_hold_seconds: int,
  bot_win_rate: float | None = None,
  profit_factor: float | None = None,
  total_pnl: float | None = None,
) -> bool:
  """Exit losing positions during graduation nudge after min hold to cut churn."""
  if not shadow_graduation_exits_active(
    bot_type,
    graduation_nudge=graduation_nudge,
    shadow_mode=shadow_mode,
    bot_win_rate=bot_win_rate,
  ):
    return False
  if held_seconds < min_hold_seconds:
    return False
  if crypto_momentum_retreat_active(
    bot_type,
    shadow_mode,
    graduation_nudge,
    bot_win_rate=bot_win_rate,
    profit_factor=profit_factor,
    total_pnl=total_pnl,
  ):
    threshold = CRYPTO_MOMENTUM_RETREAT_LOSS_WIND_DOWN_USD
  elif crypto_pre_graduation_nudge(
    bot_type,
    shadow_mode,
    bot_win_rate,
    profit_factor,
    total_pnl,
  ):
    threshold = CRYPTO_PRE_GRADUATION_LOSS_WIND_DOWN_USD
  elif crypto_strong_momentum_nudge(
    bot_type,
    shadow_mode,
    bot_win_rate,
    profit_factor,
    total_pnl,
  ):
    threshold = CRYPTO_STRONG_MOMENTUM_LOSS_WIND_DOWN_USD
  elif (
    bot_type == "commodities"
    and not shadow_mode
    and graduation_nudge
  ):
    threshold = COMMODITIES_ACTIVE_GATE_LOSS_WIND_DOWN_USD
  elif (
    shadow_mode
    and is_profitable_graduation_nudge(
      bot_type,
      bot_win_rate,
      profit_factor=profit_factor,
      total_pnl=total_pnl,
    )
  ):
    threshold = PROFITABLE_SHADOW_LOSS_WIND_DOWN_USD
  else:
    threshold = GRADUATION_NUDGE_LOSS_WIND_DOWN_USD
  return unrealized <= -threshold


def shadow_cap_pressure_loser_wind_down(
  *,
  graduation_nudge: bool,
  bot_type: str,
  shadow_mode: bool,
  unrealized: float,
  held_seconds: float,
  min_hold_seconds: int,
  open_count: int,
  shadow_open_cap: int | None,
  bot_win_rate: float | None = None,
  profit_factor: float | None = None,
  total_pnl: float | None = None,
) -> bool:
  """Free shadow cap slots by exiting losers when graduation nudge tiers fill the cap."""
  if not shadow_mode or shadow_open_cap is None or open_count < shadow_open_cap:
    return False
  if not crypto_cap_pressure_nudge(
    bot_type,
    shadow_mode,
    graduation_nudge,
    bot_win_rate,
    profit_factor,
    total_pnl,
  ):
    return False
  effective_min_hold = crypto_cap_pressure_effective_min_hold(
    min_hold_seconds,
    unrealized,
  )
  if held_seconds < effective_min_hold:
    return False
  threshold = crypto_cap_pressure_loser_threshold(
    bot_type,
    shadow_mode,
    graduation_nudge,
    bot_win_rate,
    profit_factor,
    total_pnl,
  )
  return unrealized <= -threshold


def crypto_momentum_retreat_loss_exposure_bypass(
  open_positions: list[Any],
  *,
  graduation_nudge: bool,
  shadow_mode: bool,
  bot_type: str,
  shadow_open_cap: int | None,
  bot_win_rate: float | None,
  profit_factor: float | None,
  total_pnl: float | None,
) -> bool:
  """Allow aligned retreat entries while shadow cap still has room for one loser."""
  if not crypto_momentum_retreat_active(
    bot_type,
    shadow_mode,
    graduation_nudge,
    bot_win_rate=bot_win_rate,
    profit_factor=profit_factor,
    total_pnl=total_pnl,
  ):
    return False
  if shadow_open_cap is None or len(open_positions) >= shadow_open_cap:
    return False
  losers = [
    p for p in open_positions
    if float(getattr(p, "unrealized_pnl", 0) or 0)
    <= -CRYPTO_MOMENTUM_RETREAT_CAP_PRESSURE_LOSER_USD
  ]
  if len(losers) >= SHADOW_GRADUATION_LOSS_EXPOSURE_MIN_LOSERS:
    return False
  aggregate = sum(float(getattr(p, "unrealized_pnl", 0) or 0) for p in open_positions)
  return aggregate > -CRYPTO_MOMENTUM_RETREAT_LOSS_EXPOSURE_AGGREGATE_USD


def shadow_graduation_loss_exposure_blocks_entry(
  open_positions: list[Any],
  *,
  graduation_nudge: bool,
  shadow_mode: bool,
  bot_type: str | None = None,
  shadow_open_cap: int | None = None,
  bot_win_rate: float | None = None,
  profit_factor: float | None = None,
  total_pnl: float | None = None,
) -> bool:
  """Block new shadow entries when multiple open positions are already losing."""
  if not (graduation_nudge and shadow_mode):
    return False
  losers = [
    p for p in open_positions
    if float(getattr(p, "unrealized_pnl", 0) or 0) <= -SHADOW_GRADUATION_LOSS_EXPOSURE_PER_POSITION_USD
  ]
  blocked = False
  if any(
    float(getattr(p, "unrealized_pnl", 0) or 0) <= -SHADOW_GRADUATION_LOSS_EXPOSURE_SINGLE_POSITION_USD
    for p in open_positions
  ):
    blocked = True
  elif len(losers) >= SHADOW_GRADUATION_LOSS_EXPOSURE_MIN_LOSERS:
    blocked = True
  else:
    aggregate = sum(float(getattr(p, "unrealized_pnl", 0) or 0) for p in open_positions)
    blocked = aggregate <= -SHADOW_GRADUATION_LOSS_EXPOSURE_AGGREGATE_USD
  if blocked and bot_type == "crypto":
    if crypto_momentum_retreat_loss_exposure_bypass(
      open_positions,
      graduation_nudge=graduation_nudge,
      shadow_mode=shadow_mode,
      bot_type=bot_type,
      shadow_open_cap=shadow_open_cap,
      bot_win_rate=bot_win_rate,
      profit_factor=profit_factor,
      total_pnl=total_pnl,
    ):
      return False
  return blocked


def shadow_graduation_profit_lock(
  *,
  graduation_nudge: bool,
  shadow_mode: bool,
  bot_type: str,
  unrealized: float,
  held_seconds: float,
  min_hold_seconds: int,
  bot_win_rate: float | None = None,
  profit_factor: float | None = None,
  total_pnl: float | None = None,
  total_trades: int | None = None,
  symbol: str | None = None,
  proven_winners: frozenset[str] | None = None,
  open_count: int = 0,
  shadow_open_cap: int | None = None,
) -> bool:
  """Bank winners during graduation nudge instead of round-tripping gains."""
  stocks_trade_count_exit = False
  if (
    shadow_mode
    and bot_type == "stocks_futures"
    and bot_win_rate is not None
    and total_trades is not None
    and stocks_trade_count_graduation_nudge(
      bot_type, shadow_mode, bot_win_rate, total_trades
    )
  ):
    stocks_trade_count_exit = True
  if not stocks_trade_count_exit and not shadow_graduation_exits_active(
    bot_type,
    graduation_nudge=graduation_nudge,
    shadow_mode=shadow_mode,
    bot_win_rate=bot_win_rate,
  ):
    return False
  effective_min_hold = min_hold_seconds
  if crypto_near_graduation_nudge(
    bot_type,
    shadow_mode,
    bot_win_rate,
    profit_factor,
    total_pnl,
  ) and unrealized >= CRYPTO_NEAR_GRADUATION_PROFIT_LOCK_USD * (
    CRYPTO_NEAR_GRADUATION_EARLY_PROFIT_LOCK_MULTIPLIER
  ):
    effective_min_hold = min(
      min_hold_seconds,
      CRYPTO_NEAR_GRADUATION_EARLY_PROFIT_LOCK_MIN_HOLD_SECONDS,
    )
  if (
    bot_type == "crypto"
    and shadow_mode
    and shadow_open_cap is not None
    and open_count >= shadow_open_cap
    and crypto_cap_pressure_nudge(
      bot_type,
      shadow_mode,
      graduation_nudge,
      bot_win_rate,
      profit_factor,
      total_pnl,
    )
  ):
    effective_min_hold = min(
      effective_min_hold,
      CRYPTO_CAP_PRESSURE_PROFIT_LOCK_MIN_HOLD_SECONDS,
    )
  if held_seconds < effective_min_hold:
    return False
  if (
    shadow_mode
    and is_profitable_graduation_nudge(
      bot_type,
      bot_win_rate,
      profit_factor=profit_factor,
      total_pnl=total_pnl,
    )
  ):
    threshold = PROFITABLE_SHADOW_PROFIT_LOCK_USD
  else:
    threshold = GRADUATION_NUDGE_PROFIT_LOCK_USD
  if (
    not shadow_mode
    and bot_type == "commodities"
    and symbol
    and proven_winners
    and symbol in proven_winners
  ):
    threshold = min(threshold, COMMODITIES_PROVEN_WINNER_PROFIT_LOCK_USD)
  if (
    not shadow_mode
    and bot_type == "commodities"
    and graduation_nudge
    and profit_factor is not None
    and profit_factor < 1.3
  ):
    threshold = min(threshold, COMMODITIES_GRADUATION_PF_PROFIT_LOCK_USD)
  if (
    not shadow_mode
    and bot_type == "commodities"
    and graduation_nudge
    and symbol in COMMODITIES_WEEKEND_SPOT_SYMBOLS
    and commodities_futures_weekend_closed()
  ):
    threshold = min(threshold, COMMODITIES_WEEKEND_SPOT_PROFIT_LOCK_USD)
  if crypto_near_graduation_nudge(
    bot_type,
    shadow_mode,
    bot_win_rate,
    profit_factor,
    total_pnl,
  ):
    threshold = min(threshold, CRYPTO_NEAR_GRADUATION_PROFIT_LOCK_USD)
  if crypto_momentum_retreat_active(
    bot_type,
    shadow_mode,
    graduation_nudge,
    bot_win_rate,
    profit_factor,
    total_pnl,
  ):
    threshold = min(threshold, CRYPTO_MOMENTUM_RETREAT_PROFIT_LOCK_USD)
  if (
    shadow_mode
    and bot_type == "stocks_futures"
    and bot_win_rate is not None
    and profit_factor is not None
    and total_trades is not None
  ):
    from app.engines.profitability_gate import ProfitabilityGate

    if (
      bot_win_rate >= ProfitabilityGate.GRADUATION_MIN_WIN_RATE
      and profit_factor < 1.0
      and stocks_trade_count_graduation_nudge(
        bot_type, shadow_mode, bot_win_rate, total_trades
      )
    ):
      threshold = min(threshold, STOCKS_TRADE_COUNT_PROFIT_LOCK_USD)
  return unrealized >= threshold


def gate_cap_pressure_proxy_wind_down(
  *,
  bot_type: str,
  shadow_mode: bool,
  graduation_nudge: bool,
  symbol: str,
  unrealized: float,
  held_seconds: float,
  min_hold_seconds: int,
  open_count: int,
  gate_tightening: GateEntryTightening,
  signal_direction: str | None = None,
) -> bool:
  """Free gate slots by exiting losing crypto proxy marks when commodities is at open cap."""
  if shadow_mode or bot_type not in ACTIVE_GATE_GRADUATION_NUDGE_BOTS or not graduation_nudge:
    return False
  if symbol not in _commodities_cap_pressure_proxy_symbols():
    return False
  cap = commodities_effective_open_cap(
    gate_tightening.max_commodities_open_positions,
    bot_type=bot_type,
    graduation_nudge=graduation_nudge,
    shadow_mode=shadow_mode,
  )
  if not isinstance(cap, int) or open_count < cap:
    return False
  if held_seconds < min_hold_seconds:
    return False
  return unrealized < 0


def _commodities_cap_pressure_proxy_symbols() -> frozenset[str]:
  from app.engines.market_data import CRYPTO_LIVE_PRICE_PROXY

  return frozenset(CRYPTO_LIVE_PRICE_PROXY) | COMMODITIES_WEEKEND_SPOT_SYMBOLS


def gate_cap_pressure_proxy_entry_blocked(
  *,
  bot_type: str,
  shadow_mode: bool,
  graduation_nudge: bool,
  symbol: str,
  open_count: int,
  gate_tightening: GateEntryTightening,
) -> bool:
  """Block new proxy marks at open cap — avoids cap-pressure churn on immediate wind-down."""
  if shadow_mode or bot_type not in ACTIVE_GATE_GRADUATION_NUDGE_BOTS or not graduation_nudge:
    return False
  if symbol not in _commodities_cap_pressure_proxy_symbols():
    return False
  cap = commodities_effective_open_cap(
    gate_tightening.max_commodities_open_positions,
    bot_type=bot_type,
    graduation_nudge=graduation_nudge,
    shadow_mode=shadow_mode,
  )
  if not isinstance(cap, int) or open_count < cap:
    return False
  return True


def commodities_gold_proxy_duplicate_entry_blocked(
  symbol: str,
  held_symbols: frozenset[str] | set[str],
) -> bool:
  """Block a second weekend gold proxy when one is already held — same exposure thesis."""
  if symbol not in COMMODITIES_WEEKEND_SPOT_SYMBOLS:
    return False
  held_spot = frozenset(held_symbols) & COMMODITIES_WEEKEND_SPOT_SYMBOLS
  return bool(held_spot - {symbol})


def commodities_gold_proxy_duplicate_wind_down(
  *,
  bot_type: str,
  shadow_mode: bool,
  graduation_nudge: bool,
  symbol: str,
  held_symbols: frozenset[str] | set[str],
  held_seconds: float,
  min_hold_seconds: int,
) -> bool:
  """Drop the non-preferred gold proxy when both are held over the weekend."""
  if shadow_mode or bot_type != "commodities" or not graduation_nudge:
    return False
  if not commodities_futures_weekend_closed():
    return False
  held_spot = frozenset(held_symbols) & COMMODITIES_WEEKEND_SPOT_SYMBOLS
  if len(held_spot) < 2 or symbol not in held_spot:
    return False
  if COMMODITIES_GOLD_PROXY_PREFERRED not in held_spot:
    return False
  if symbol == COMMODITIES_GOLD_PROXY_PREFERRED:
    return False
  min_hold = min(min_hold_seconds, COMMODITIES_GOLD_PROXY_DEDUP_MIN_HOLD_SECONDS)
  if held_seconds < min_hold:
    return False
  return True


async def _commodities_recent_weekend_spot_profit_lock_at(
  session: AsyncSession,
) -> datetime | None:
  """Most recent winning weekend spot sell with profit lock, if still in post-lock window."""
  from app.models.entities import Trade

  result = await session.execute(
    select(Trade.executed_at)
    .where(
      Trade.bot_type == "commodities",
      Trade.action == "sell",
      Trade.symbol.in_(tuple(COMMODITIES_WEEKEND_SPOT_SYMBOLS)),
      Trade.is_winner.is_(True),
      Trade.reason.ilike("%profit lock%"),
    )
    .order_by(Trade.executed_at.desc())
    .limit(1)
  )
  locked_at = result.scalar_one_or_none()
  if not locked_at:
    return None
  session_info = commodities_session_info()
  minutes_until = session_info.get("minutes_until_open")
  if minutes_until is None or minutes_until <= 0:
    return None
  if locked_at.tzinfo is not None:
    locked_at = locked_at.replace(tzinfo=None)
  if (datetime.utcnow() - locked_at).total_seconds() > 7 * 86400:
    return None
  return locked_at


async def commodities_weekend_spot_post_profit_lock_entry_blocked(
  session: AsyncSession,
  *,
  bot_type: str,
  shadow_mode: bool,
  graduation_nudge: bool,
  symbol: str,
) -> bool:
  """After banking weekend spot profits, block re-entry until CME reopen."""
  if shadow_mode or bot_type != "commodities" or not graduation_nudge:
    return False
  if symbol not in COMMODITIES_WEEKEND_SPOT_SYMBOLS:
    return False
  if not commodities_futures_weekend_closed():
    return False
  return (await _commodities_recent_weekend_spot_profit_lock_at(session)) is not None


async def commodities_weekend_spot_post_lock_wind_down(
  session: AsyncSession,
  *,
  bot_type: str,
  shadow_mode: bool,
  graduation_nudge: bool,
  symbol: str,
  unrealized: float,
  held_seconds: float,
  min_hold_seconds: int,
  position_opened_at: datetime | None,
) -> bool:
  """Exit weekend spot re-entries after profit lock — preserve cap for Monday futures."""
  if shadow_mode or bot_type != "commodities" or not graduation_nudge:
    return False
  if symbol not in COMMODITIES_WEEKEND_SPOT_SYMBOLS:
    return False
  if not commodities_futures_weekend_closed():
    return False
  locked_at = await _commodities_recent_weekend_spot_profit_lock_at(session)
  if not locked_at:
    return False
  min_hold = min(min_hold_seconds, COMMODITIES_GOLD_PROXY_DEDUP_MIN_HOLD_SECONDS)
  if held_seconds < min_hold:
    return False
  if position_opened_at is not None:
    opened = position_opened_at
    if opened.tzinfo is not None:
      opened = opened.replace(tzinfo=None)
    if opened < locked_at:
      return False
  return unrealized < COMMODITIES_WEEKEND_SPOT_PROFIT_LOCK_USD


def commodities_cap_pressure_loser_wind_down(
  *,
  bot_type: str,
  shadow_mode: bool,
  graduation_nudge: bool,
  symbol: str,
  unrealized: float,
  held_seconds: float,
  min_hold_seconds: int,
  open_count: int,
  gate_tightening: GateEntryTightening,
) -> bool:
  """Free gate slots by exiting small futures/forex losers when commodities is at open cap."""
  if shadow_mode or bot_type not in ACTIVE_GATE_GRADUATION_NUDGE_BOTS or not graduation_nudge:
    return False
  if symbol in COMMODITIES_WEEKEND_SPOT_SYMBOLS:
    return False
  cap = commodities_effective_open_cap(
    gate_tightening.max_commodities_open_positions,
    bot_type=bot_type,
    graduation_nudge=graduation_nudge,
    shadow_mode=shadow_mode,
  )
  if not isinstance(cap, int) or open_count < cap:
    return False
  if held_seconds < min_hold_seconds:
    return False
  return unrealized <= -COMMODITIES_CAP_PRESSURE_LOSER_WIND_DOWN_USD


def commodities_monday_cap_pressure_flat_wind_down(
  *,
  bot_type: str,
  shadow_mode: bool,
  graduation_nudge: bool,
  symbol: str,
  unrealized: float,
  held_seconds: float,
  min_hold_seconds: int,
  open_count: int,
  gate_tightening: GateEntryTightening,
) -> bool:
  """Flatten idle forex holds near cap ahead of CME reopen / during weekend prep."""
  if shadow_mode or bot_type != "commodities" or not graduation_nudge:
    return False
  if is_commodities_futures_symbol(symbol):
    return False
  if symbol in COMMODITIES_WEEKEND_SPOT_SYMBOLS:
    return False
  cap = commodities_effective_open_cap(
    gate_tightening.max_commodities_open_positions,
    bot_type=bot_type,
    graduation_nudge=graduation_nudge,
    shadow_mode=shadow_mode,
  )
  if not isinstance(cap, int):
    return False
  session = commodities_session_info()
  monday_priority = commodities_monday_scan_priority_active(
    session,
    graduation_nudge=graduation_nudge,
  )
  weekend_reserve = (
    commodities_futures_weekend_closed()
    and open_count >= max(1, cap - 1)
  )
  if not monday_priority and not weekend_reserve:
    return False
  if open_count < cap and not weekend_reserve:
    return False
  if held_seconds < min_hold_seconds:
    return False
  return abs(unrealized) <= COMMODITIES_MONDAY_CAP_PRESSURE_FLAT_BAND_USD


def stocks_session_close_wind_down(
  *,
  in_session: bool,
  minutes_until_close: int | None,
  unrealized: float,
  signal_direction: str,
) -> bool:
  """Day-trading stocks: flatten into the close and never hold after the session."""
  if not in_session:
    return True
  if minutes_until_close is None:
    return False
  if minutes_until_close <= STOCKS_SESSION_CLOSE_FORCE_MINUTES:
    return True
  if minutes_until_close <= STOCKS_SESSION_CLOSE_WIND_DOWN_MINUTES:
    return unrealized < 0 or signal_direction == "sell" or unrealized > 0
  return False


def shadow_entry_min_signal(
  bot_type: str,
  strategy_min_signal: float,
  *,
  bot_win_rate: float | None = None,
  profit_factor: float | None = None,
  total_pnl: float | None = None,
) -> float:
  """Compute shadow entry threshold — eases when a paused bot is close to graduation WR."""
  from app.engines.profitability_gate import ProfitabilityGate
  from app.engines.strategy_migration import VERIFICATION_SIGNAL_CEILINGS

  ceiling = VERIFICATION_SIGNAL_CEILINGS.get(bot_type)
  base = min(strategy_min_signal, ceiling) if ceiling else strategy_min_signal
  if (
    bot_win_rate is not None
    and in_shadow_graduation_nudge(
      bot_type,
      bot_win_rate,
      profit_factor=profit_factor,
      total_pnl=total_pnl,
    )
    and bot_type in ("commodities", "crypto")
  ):
    if bot_type != "crypto" or crypto_graduation_entry_ease_active(
      bot_type,
      True,
      bot_win_rate,
      profit_factor,
      total_pnl,
    ):
      base = max(0.16, base - 0.06)
  boost = shadow_min_signal_boost(
    bot_type,
    bot_win_rate=bot_win_rate,
    profit_factor=profit_factor,
    total_pnl=total_pnl,
  )
  return min(0.95, base + boost)


def shadow_requires_macd(
  bot_type: str,
  *,
  bot_win_rate: float | None,
  gate_tightening: GateEntryTightening,
  shadow_mode: bool,
  profit_factor: float | None = None,
  total_pnl: float | None = None,
) -> bool:
  if bot_type in ("commodities", "crypto"):
    if bot_win_rate is not None and in_shadow_graduation_nudge(
      bot_type,
      bot_win_rate,
      profit_factor=profit_factor,
      total_pnl=total_pnl,
    ):
      if (
        bot_type == "crypto"
        and shadow_mode
        and not crypto_graduation_entry_ease_active(
          bot_type,
          shadow_mode,
          bot_win_rate,
          profit_factor,
          total_pnl,
        )
      ):
        return True
      return False
    if bot_type == "crypto" and shadow_mode:
      return True
  if gate_tightening.active and gate_tightening.require_macd_bullish and bot_type == "commodities":
    return True
  if shadow_mode and bot_type == "commodities":
    return True
  return False


def early_verification_index_etf_entry_min_signal(
  symbol: str,
  entry_min_signal: float,
  *,
  early_boost: bool,
) -> float:
  """Index ETFs need stronger signals during early verification — weak SPY entries blow up PnL."""
  if early_boost and symbol in GATE_INDEX_ETF_SYMBOLS:
    return entry_min_signal + EARLY_VERIFICATION_INDEX_ETF_SIGNAL_BONUS
  return entry_min_signal


def apply_entry_min_signal_ease(
  entry_min_signal: float,
  ease: float,
  *,
  early_boost: bool,
) -> float:
  """Lower entry threshold for proven/TV/RSI setups — capped higher during early verification."""
  floor = (
    EARLY_VERIFICATION_ENTRY_MIN_SIGNAL_FLOOR
    if early_boost
    else DEFAULT_ENTRY_MIN_SIGNAL_FLOOR
  )
  return max(floor, entry_min_signal - ease)


def gate_tightening_min_signal_boost_applies(
  bot_type: str,
  *,
  gate_tightening: GateEntryTightening,
  graduation_nudge: bool,
  shadow_mode: bool,
) -> bool:
  """Active gate commodities in graduation nudge skip tightening boost — preview must match live."""
  if not gate_tightening.active or bot_type == "stocks_futures":
    return False
  if (
    graduation_nudge
    and not shadow_mode
    and bot_type in ACTIVE_GATE_GRADUATION_NUDGE_BOTS
  ):
    return False
  return True


def apply_gate_tightening_min_signal(
  min_signal: float,
  bot_type: str,
  *,
  gate_tightening: GateEntryTightening,
  graduation_nudge: bool,
  shadow_mode: bool,
  loss_streak: int = 0,
) -> float:
  """Apply gate tightening composite boost to min_signal — shared by scan preview and live trading."""
  boosted = min_signal
  if gate_tightening_min_signal_boost_applies(
    bot_type,
    gate_tightening=gate_tightening,
    graduation_nudge=graduation_nudge,
    shadow_mode=shadow_mode,
  ):
    boosted = min(0.95, boosted + gate_tightening.min_composite_boost)
  if (
    loss_streak >= 3
    and not graduation_nudge_easing_active(
      bot_type,
      graduation_nudge=graduation_nudge,
      shadow_mode=shadow_mode,
    )
  ):
    boosted = min(0.95, boosted + 0.08)
  return boosted


def early_verification_raw_signal_ok(
  signal_score: float,
  *,
  early_boost: bool,
  bot_type: str,
) -> bool:
  """Block gate entries when raw technical score is too weak — composite can inflate via TV boost."""
  if early_boost and bot_type == "stocks_futures":
    return signal_score >= EARLY_VERIFICATION_MIN_RAW_SIGNAL_SCORE
  return True
UNDERPERFORMER_MIN_TRADES = 15
UNDERPERFORMER_MAX_WIN_RATE = 0.40
CHRONIC_LOSER_MIN_TRADES = 3
CHRONIC_LOSER_MAX_WIN_RATE = 0.35
RECENT_LOSER_DAYS = 7
RECENT_LOSER_MIN_LOSSES = 2
RECENT_LARGE_LOSS_USD = 25.0
RECENT_LARGE_LOSS_USD_BY_BOT = {
  "stocks_futures": 15.0,
}
RECENT_LARGE_LOSS_HOURS = 24
FEED_ARTIFACT_LOSS_MAX_USD = 15.0
EARLY_VERIFICATION_WIND_DOWN_COOLDOWN_MULTIPLIER = 3
SHADOW_LARGE_LOSS_BYPASS_COMPOSITE = 0.55
SHADOW_LARGE_LOSS_BYPASS_COMPOSITE_BY_BOT = {
  "commodities": 0.42,
}
SHADOW_LARGE_LOSS_BYPASS_INTEGRATION = 0.10
REVIEW_LOSER_DAYS = 3
PROVEN_WINNER_MIN_TRADES = 2
PROVEN_WINNER_MIN_WIN_RATE = 0.50


def is_feed_artifact_loss(
  bot_type: str,
  symbol: str,
  pnl: float | None,
  reason: str | None,
) -> bool:
  """Exclude proxy feed-correction wind-downs from gate-skip loser tallies."""
  from app.engines.market_data import CRYPTO_LIVE_PRICE_PROXY

  if bot_type != "commodities" or symbol not in CRYPTO_LIVE_PRICE_PROXY:
    return False
  if pnl is None or abs(float(pnl)) > FEED_ARTIFACT_LOSS_MAX_USD:
    return False
  if not reason:
    return False
  lowered = reason.lower()
  return "wind-down" in lowered or "proxy" in lowered or "feed-correction" in lowered


async def _symbol_trade_stats(session: AsyncSession, bot_type: str) -> dict[str, dict[str, int]]:
  from app.models.entities import Trade

  result = await session.execute(
    select(Trade.symbol, Trade.is_winner, Trade.pnl, Trade.reason).where(
      Trade.bot_type == bot_type,
      Trade.action == "sell",
    )
  )
  stats: dict[str, dict[str, int]] = {}
  for symbol, is_winner, pnl, reason in result.all():
    if not symbol:
      continue
    if is_winner is False and is_feed_artifact_loss(bot_type, symbol, pnl, reason):
      continue
    bucket = stats.setdefault(symbol, {"wins": 0, "losses": 0})
    if is_winner is True:
      bucket["wins"] += 1
    elif is_winner is False:
      bucket["losses"] += 1
  return stats


async def get_underperforming_bots(session: AsyncSession) -> frozenset[str]:
  """Bots with enough verification-period trades and win rate below floor."""
  per_bot = await ProfitabilityGate(session).evaluate_per_bot()
  blocked: set[str] = set()
  for bot_type, stats in per_bot.items():
    total = int(stats.get("total_trades") or 0)
    win_rate = float(stats.get("win_rate") or 0)
    if total < UNDERPERFORMER_MIN_TRADES:
      continue
    if win_rate < UNDERPERFORMER_MAX_WIN_RATE:
      blocked.add(bot_type)
  return frozenset(blocked)


async def active_gate_entry_exempt_bots(session: AsyncSession) -> frozenset[str]:
  """Non-paused bots must never be blocked from new entries — they serve the active gate."""
  from app.engines.platform_settings import get_paused_bot_types

  paused = set(await get_paused_bot_types(session))
  return frozenset(bot for bot in BOT_TYPES if bot not in paused)


async def get_chronic_loser_symbols(
  session: AsyncSession,
  bot_type: str,
  *,
  min_trades: int = CHRONIC_LOSER_MIN_TRADES,
  max_win_rate: float = CHRONIC_LOSER_MAX_WIN_RATE,
) -> frozenset[str]:
  """Symbols with enough closed trades and poor win rate — skip new entries during gate."""
  stats = await _symbol_trade_stats(session, bot_type)

  blocked: set[str] = set()
  for symbol, counts in stats.items():
    decided = counts["wins"] + counts["losses"]
    if decided < min_trades:
      continue
    if counts["wins"] / decided < max_win_rate:
      blocked.add(symbol)
  return frozenset(blocked)


async def get_recent_loser_symbols(
  session: AsyncSession,
  bot_type: str,
  *,
  days: int = RECENT_LOSER_DAYS,
  min_losses: int = RECENT_LOSER_MIN_LOSSES,
) -> frozenset[str]:
  """Symbols with multiple recent losses and no wins — skip during gate."""
  from app.models.entities import Trade

  cutoff = datetime.utcnow() - timedelta(days=days)
  result = await session.execute(
    select(Trade.symbol, Trade.is_winner, Trade.pnl, Trade.reason).where(
      Trade.bot_type == bot_type,
      Trade.action == "sell",
      Trade.executed_at >= cutoff,
    )
  )
  stats: dict[str, dict[str, int]] = {}
  for symbol, is_winner, pnl, reason in result.all():
    if not symbol:
      continue
    if is_winner is False and is_feed_artifact_loss(bot_type, symbol, pnl, reason):
      continue
    bucket = stats.setdefault(symbol, {"wins": 0, "losses": 0})
    if is_winner is True:
      bucket["wins"] += 1
    elif is_winner is False:
      bucket["losses"] += 1

  blocked: set[str] = set()
  for symbol, counts in stats.items():
    if counts["losses"] >= min_losses and counts["wins"] == 0:
      blocked.add(symbol)
  return frozenset(blocked)


async def get_large_recent_loss_symbols(
  session: AsyncSession,
  bot_type: str,
  *,
  hours: int = RECENT_LARGE_LOSS_HOURS,
  min_loss_usd: float | None = None,
  recovery_win_ratio: float = 0.25,
) -> frozenset[str]:
  """Skip symbols with a recent large loss until a meaningful recovery win.

  A tiny win after a large loss (e.g. NVDA -$71 then +$0.21) must not clear the block.
  """
  from app.models.entities import Trade

  loss_floor = min_loss_usd
  if loss_floor is None:
    loss_floor = RECENT_LARGE_LOSS_USD_BY_BOT.get(bot_type, RECENT_LARGE_LOSS_USD)
  cutoff = datetime.utcnow() - timedelta(hours=hours)
  result = await session.execute(
    select(Trade.symbol, Trade.pnl, Trade.is_winner, Trade.executed_at, Trade.reason).where(
      Trade.bot_type == bot_type,
      Trade.action == "sell",
      Trade.executed_at >= cutoff,
    ).order_by(Trade.executed_at.asc())
  )
  sells_by_symbol: dict[str, list[tuple[float | None, bool | None]]] = {}
  for symbol, pnl, is_winner, _executed_at, reason in result.all():
    if not symbol:
      continue
    if is_winner is False and is_feed_artifact_loss(bot_type, symbol, pnl, reason):
      continue
    sells_by_symbol.setdefault(symbol, []).append((pnl, is_winner))

  blocked: set[str] = set()
  for symbol, sells in sells_by_symbol.items():
    pending_loss: float | None = None
    for pnl, is_winner in sells:
      if is_winner is False and pnl is not None and pnl <= -loss_floor:
        pending_loss = abs(pnl)
        continue
      if pending_loss is not None and pnl is not None and pnl >= pending_loss * recovery_win_ratio:
        pending_loss = None
    if pending_loss is not None:
      blocked.add(symbol)
  return frozenset(blocked)


def gate_entry_guards_active(
  *,
  gate_tightening: GateEntryTightening,
  shadow_mode: bool,
  live_trading_ready: bool,
) -> bool:
  """Whether loser/skip symbol guards apply to new entries."""
  return gate_tightening.active or shadow_mode or not live_trading_ready


async def get_review_blocked_symbols(
  session: AsyncSession,
  bot_type: str,
  *,
  days: int = REVIEW_LOSER_DAYS,
) -> frozenset[str]:
  """Symbols flagged as worst daily losers in recent post-mortems."""
  from app.models.entities import DailyReview

  cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
  result = await session.execute(
    select(DailyReview.patterns_found).where(
      DailyReview.bot_type == bot_type,
      DailyReview.review_date >= cutoff,
      DailyReview.losing_trades >= 2,
    )
  )
  blocked: set[str] = set()
  explicit_skip = re.compile(r"Gate skip recommended for (\S+)")
  for (patterns_found,) in result.all():
    if not patterns_found:
      continue
    for match in explicit_skip.finditer(patterns_found):
      blocked.add(match.group(1).rstrip(",.)"))
  return frozenset(blocked)


def _bot_cooldown_seconds(bot_type: str, *, after_loss: bool) -> int:
  from app.config import settings

  if bot_type == "crypto":
    return (
      settings.crypto_loss_cooldown_seconds
      if after_loss
      else settings.crypto_reentry_cooldown_seconds
    )
  if bot_type == "commodities":
    return (
      settings.commodities_loss_cooldown_seconds
      if after_loss
      else settings.commodities_reentry_cooldown_seconds
    )
  if bot_type == "stocks_futures":
    return (
      settings.stocks_loss_cooldown_seconds
      if after_loss
      else settings.stocks_reentry_cooldown_seconds
    )
  if bot_type == "polymarket":
    return (
      settings.polymarket_loss_cooldown_seconds
      if after_loss
      else settings.polymarket_reentry_cooldown_seconds
    )
  return 900


async def is_symbol_in_trade_cooldown(
  session: AsyncSession,
  bot_type: str,
  symbol: str,
  *,
  chronic_symbols: frozenset[str] = frozenset(),
  large_loss_symbols: frozenset[str] = frozenset(),
  graduation_nudge: bool = False,
  shadow_mode: bool = True,
  signal_direction: str = "buy",
  macd_signal: str = "bullish",
  composite: float = 0.0,
  proven_winners: frozenset[str] = frozenset(),
  bot_win_rate: float | None = None,
  total_trades: int = 0,
  open_count: int | None = None,
  shadow_open_cap: int | None = None,
  profit_factor: float | None = None,
  total_pnl: float | None = None,
) -> bool:
  """DB-backed re-entry cooldown — survives deploy restarts."""
  remaining = await symbol_cooldown_remaining_seconds(
    session,
    bot_type,
    symbol,
    chronic_symbols=chronic_symbols,
    large_loss_symbols=large_loss_symbols,
    graduation_nudge=graduation_nudge,
    shadow_mode=shadow_mode,
    signal_direction=signal_direction,
    macd_signal=macd_signal,
    composite=composite,
    proven_winners=proven_winners,
    bot_win_rate=bot_win_rate,
    total_trades=total_trades,
    open_count=open_count,
    shadow_open_cap=shadow_open_cap,
    profit_factor=profit_factor,
    total_pnl=total_pnl,
  )
  return remaining > 0


async def symbol_cooldown_remaining_seconds(
  session: AsyncSession,
  bot_type: str,
  symbol: str,
  *,
  chronic_symbols: frozenset[str] = frozenset(),
  large_loss_symbols: frozenset[str] = frozenset(),
  graduation_nudge: bool = False,
  shadow_mode: bool = True,
  signal_direction: str = "buy",
  macd_signal: str = "bullish",
  composite: float = 0.0,
  proven_winners: frozenset[str] = frozenset(),
  bot_win_rate: float | None = None,
  total_trades: int = 0,
  open_count: int | None = None,
  shadow_open_cap: int | None = None,
  profit_factor: float | None = None,
  total_pnl: float | None = None,
) -> int:
  """Seconds until symbol re-entry is allowed after last sell."""
  if commodities_weekend_spot_gate_skip_bypass(
    bot_type=bot_type,
    shadow_mode=shadow_mode,
    symbol=symbol,
    graduation_nudge=graduation_nudge,
    signal_direction=signal_direction,
    macd_signal=macd_signal,
    composite=composite,
  ):
    return 0
  if commodities_monday_futures_gate_skip_bypass(
    bot_type=bot_type,
    shadow_mode=shadow_mode,
    symbol=symbol,
    graduation_nudge=graduation_nudge,
    signal_direction=signal_direction,
    macd_signal=macd_signal,
    composite=composite,
  ):
    return 0
  if stocks_monday_gate_skip_bypass(
    bot_type=bot_type,
    shadow_mode=shadow_mode,
    symbol=symbol,
    proven_winners=proven_winners,
    bot_win_rate=bot_win_rate,
    total_trades=total_trades,
    signal_direction=signal_direction,
    macd_signal=macd_signal,
    composite=composite,
  ):
    return 0
  from app.models.entities import Trade

  result = await session.execute(
    select(Trade.is_winner, Trade.executed_at, Trade.reason, Trade.pnl)
    .where(
      Trade.bot_type == bot_type,
      Trade.symbol == symbol,
      Trade.action == "sell",
    )
    .order_by(Trade.executed_at.desc())
    .limit(1)
  )
  row = result.first()
  if row:
    _, _, last_reason, _ = row
    if crypto_momentum_retreat_cooldown_bypass(
      bot_type=bot_type,
      shadow_mode=shadow_mode,
      graduation_nudge=graduation_nudge,
      bot_win_rate=bot_win_rate,
      profit_factor=profit_factor,
      total_pnl=total_pnl,
      signal_direction=signal_direction,
      macd_signal=macd_signal,
      composite=composite,
      open_count=open_count,
      shadow_open_cap=shadow_open_cap,
      last_exit_reason=last_reason,
    ):
      return 0
  if not row:
    return 0
  is_winner, executed_at, reason, pnl = row
  if not executed_at or is_winner is None:
    return 0
  if executed_at.tzinfo is not None:
    executed_at = executed_at.replace(tzinfo=None)
  elapsed = (datetime.utcnow() - executed_at).total_seconds()
  seconds = _bot_cooldown_seconds(bot_type, after_loss=is_winner is False)
  if (
    is_winner is False
    and bot_type in ("commodities", "crypto")
    and symbol in chronic_symbols
  ):
    seconds = int(seconds * SHADOW_CHRONIC_LOSS_COOLDOWN_MULTIPLIER)
  large_mult = LARGE_LOSS_COOLDOWN_MULTIPLIER_BY_BOT.get(bot_type)
  if is_winner is False and large_mult and symbol in large_loss_symbols:
    seconds = int(seconds * large_mult)
  if (
    is_winner is False
    and reason
    and "Early verification wind-down" in reason
    and bot_type == "stocks_futures"
  ):
    seconds = int(seconds * EARLY_VERIFICATION_WIND_DOWN_COOLDOWN_MULTIPLIER)
  if (
    is_winner is False
    and graduation_nudge
    and bot_type in ("crypto", "commodities")
  ):
    seconds = int(seconds * SHADOW_GRADUATION_LOSS_COOLDOWN_MULTIPLIER)
  if is_winner is False and is_feed_artifact_loss(bot_type, symbol, pnl, reason):
    seconds = int(seconds * FEED_ARTIFACT_COOLDOWN_MULTIPLIER)
  if (
    bot_type == "commodities"
    and symbol in COMMODITIES_WEEKEND_SPOT_SYMBOLS
    and commodities_futures_weekend_closed()
    and not is_feed_artifact_loss(bot_type, symbol, pnl, reason)
  ):
    seconds = int(seconds * COMMODITIES_WEEKEND_SPOT_COOLDOWN_MULTIPLIER)
  return max(0, int(seconds - elapsed))


@dataclass(frozen=True)
class HardGateSkipSets:
  recent: frozenset[str]
  large: frozenset[str]
  review: frozenset[str]

  @property
  def all(self) -> frozenset[str]:
    return self.recent | self.large | self.review


async def get_hard_gate_skip_components(
  session: AsyncSession, bot_type: str
) -> HardGateSkipSets:
  """Split hard gate-skip sources — graduation nudge may bypass recent/large with strong intel."""
  return HardGateSkipSets(
    recent=await get_recent_loser_symbols(session, bot_type),
    large=await get_large_recent_loss_symbols(session, bot_type),
    review=await get_review_blocked_symbols(session, bot_type),
  )


def hard_skip_blocks_shadow_entry(
  symbol: str,
  *,
  bot_type: str,
  recent_skip: frozenset[str],
  large_skip: frozenset[str],
  review_skip: frozenset[str],
  graduation_nudge: bool,
  shadow_mode: bool,
  intel_override: bool,
  composite: float,
  integration_boost: float,
  signal_direction: str = "buy",
  macd_signal: str = "bullish",
  proven_winners: frozenset[str] | None = None,
  bot_win_rate: float | None = None,
  total_trades: int = 0,
  profit_factor: float | None = None,
  total_pnl: float | None = None,
  open_count: int | None = None,
  shadow_open_cap: int | None = None,
) -> bool:
  """Hard gate-skip during graduation nudge — review blocks ease on strong active-gate composites."""
  recovery_ok = (
    stocks_proven_winner_recovery_entry_ok(
      bot_type=bot_type,
      shadow_mode=shadow_mode,
      symbol=symbol,
      proven_winners=proven_winners or frozenset(),
      bot_win_rate=bot_win_rate,
      composite=composite,
      signal_direction=signal_direction,
      macd_signal=macd_signal,
      total_trades=total_trades,
    )
    or commodities_high_composite_recovery_entry_ok(
      bot_type=bot_type,
      shadow_mode=shadow_mode,
      symbol=symbol,
      composite=composite,
      signal_direction=signal_direction,
      macd_signal=macd_signal,
      graduation_nudge=graduation_nudge,
    )
  )
  if symbol in review_skip:
    if (
      not shadow_mode
      and bot_type in ACTIVE_GATE_GRADUATION_NUDGE_BOTS
      and graduation_nudge
    ):
      composite_only = SHADOW_INTEL_COMPOSITE_ONLY_BY_BOT.get(bot_type)
      if composite_only is not None and composite >= composite_only:
        return False
      if (
        intel_override
        and composite_only is not None
        and composite >= composite_only - 0.02
      ):
        return False
    if (
      shadow_mode
      and bot_type == "crypto"
      and graduation_nudge
      and intel_override
      and composite >= CRYPTO_SHADOW_REVIEW_BYPASS_COMPOSITE
    ):
      return False
    if (
      shadow_mode
      and bot_type == "crypto"
      and graduation_nudge
      and composite >= CRYPTO_SHADOW_REVIEW_BYPASS_COMPOSITE
      and signal_direction == "buy"
      and macd_signal == "bullish"
    ):
      return False
    if stocks_monday_gate_skip_bypass(
      bot_type=bot_type,
      shadow_mode=shadow_mode,
      symbol=symbol,
      proven_winners=proven_winners or frozenset(),
      bot_win_rate=bot_win_rate,
      total_trades=total_trades,
      signal_direction=signal_direction,
      macd_signal=macd_signal,
      composite=composite,
    ):
      return False
    return True
  large_bypass_floor = SHADOW_LARGE_LOSS_BYPASS_COMPOSITE_BY_BOT.get(
    bot_type, SHADOW_LARGE_LOSS_BYPASS_COMPOSITE
  )
  if symbol in large_skip:
    if recovery_ok:
      return False
    if commodities_weekend_spot_gate_skip_bypass(
      bot_type=bot_type,
      shadow_mode=shadow_mode,
      symbol=symbol,
      graduation_nudge=graduation_nudge,
      signal_direction=signal_direction,
      macd_signal=macd_signal,
      composite=composite,
    ):
      return False
    if commodities_monday_futures_gate_skip_bypass(
      bot_type=bot_type,
      shadow_mode=shadow_mode,
      symbol=symbol,
      graduation_nudge=graduation_nudge,
      signal_direction=signal_direction,
      macd_signal=macd_signal,
      composite=composite,
    ):
      return False
    if stocks_monday_gate_skip_bypass(
      bot_type=bot_type,
      shadow_mode=shadow_mode,
      symbol=symbol,
      proven_winners=proven_winners or frozenset(),
      bot_win_rate=bot_win_rate,
      total_trades=total_trades,
      signal_direction=signal_direction,
      macd_signal=macd_signal,
      composite=composite,
    ):
      return False
    if crypto_momentum_retreat_gate_skip_bypass(
      bot_type=bot_type,
      shadow_mode=shadow_mode,
      graduation_nudge=graduation_nudge,
      bot_win_rate=bot_win_rate,
      profit_factor=profit_factor,
      total_pnl=total_pnl,
      signal_direction=signal_direction,
      macd_signal=macd_signal,
      composite=composite,
      open_count=open_count,
      shadow_open_cap=shadow_open_cap,
    ):
      return False
    if graduation_nudge_easing_active(
      bot_type,
      graduation_nudge=graduation_nudge,
      shadow_mode=shadow_mode,
    ):
      if composite >= large_bypass_floor and integration_boost >= SHADOW_LARGE_LOSS_BYPASS_INTEGRATION:
        return False
      composite_only = SHADOW_INTEL_COMPOSITE_ONLY_BY_BOT.get(bot_type)
      if composite_only is not None and composite >= composite_only:
        return False
    return True
  if symbol in recent_skip:
    if recovery_ok:
      return False
    if commodities_weekend_spot_gate_skip_bypass(
      bot_type=bot_type,
      shadow_mode=shadow_mode,
      symbol=symbol,
      graduation_nudge=graduation_nudge,
      signal_direction=signal_direction,
      macd_signal=macd_signal,
      composite=composite,
    ):
      return False
    if commodities_monday_futures_gate_skip_bypass(
      bot_type=bot_type,
      shadow_mode=shadow_mode,
      symbol=symbol,
      graduation_nudge=graduation_nudge,
      signal_direction=signal_direction,
      macd_signal=macd_signal,
      composite=composite,
    ):
      return False
    if stocks_monday_gate_skip_bypass(
      bot_type=bot_type,
      shadow_mode=shadow_mode,
      symbol=symbol,
      proven_winners=proven_winners or frozenset(),
      bot_win_rate=bot_win_rate,
      total_trades=total_trades,
      signal_direction=signal_direction,
      macd_signal=macd_signal,
      composite=composite,
    ):
      return False
    if crypto_momentum_retreat_gate_skip_bypass(
      bot_type=bot_type,
      shadow_mode=shadow_mode,
      graduation_nudge=graduation_nudge,
      bot_win_rate=bot_win_rate,
      profit_factor=profit_factor,
      total_pnl=total_pnl,
      signal_direction=signal_direction,
      macd_signal=macd_signal,
      composite=composite,
      open_count=open_count,
      shadow_open_cap=shadow_open_cap,
    ):
      return False
    if graduation_nudge_easing_active(
      bot_type,
      graduation_nudge=graduation_nudge,
      shadow_mode=shadow_mode,
    ) and intel_override:
      return False
    return True
  return False


async def get_hard_gate_skip_symbols(session: AsyncSession, bot_type: str) -> frozenset[str]:
  """Symbols that must never be bypassed — recent streaks, large losses, post-mortem blocks."""
  components = await get_hard_gate_skip_components(session, bot_type)
  return components.all


async def get_gate_skip_symbols(session: AsyncSession, bot_type: str) -> frozenset[str]:
  """Union of chronic, recent, large-loss, and daily-review loser symbols during gate."""
  chronic = await get_chronic_loser_symbols(session, bot_type)
  return chronic | await get_hard_gate_skip_symbols(session, bot_type)


async def get_proven_winner_symbols(
  session: AsyncSession,
  bot_type: str,
  *,
  min_trades: int = PROVEN_WINNER_MIN_TRADES,
  min_win_rate: float = PROVEN_WINNER_MIN_WIN_RATE,
) -> frozenset[str]:
  """Symbols with strong historical win rate — easier entries during gate."""
  stats = await _symbol_trade_stats(session, bot_type)

  winners: set[str] = set()
  for symbol, counts in stats.items():
    decided = counts["wins"] + counts["losses"]
    if decided < min_trades:
      continue
    if counts["wins"] / decided >= min_win_rate:
      winners.add(symbol)
  return frozenset(winners)


async def bot_allows_new_entries(session: AsyncSession, bot_type: str) -> bool:
  """Block new entries for chronic underperformers while gate is active."""
  tightening = await get_gate_entry_tightening(session)
  if not tightening.active:
    return True
  return bot_type not in tightening.blocked_new_entries


async def sync_gate_bot_pauses(session: AsyncSession) -> list[str]:
  """Pause chronic underperformers during verification so gate metrics focus on viable bots.

  Uses aggregate win rate (all bots) to decide pauses; does not auto-unpause — only paper
  reset or admin unpause clears pauses once set.
  """
  from app.engines.platform_settings import is_bot_paused, set_bot_paused

  gate = await ProfitabilityGate(session).evaluate()
  aggregate = gate.get("aggregate") or {}
  agg_wr = float(aggregate.get("win_rate") or gate.get("win_rate") or 0)
  agg_total = int(aggregate.get("total_trades") or 0)

  if agg_total < 30 or agg_wr >= ProfitabilityGate.MIN_WIN_RATE:
    return []

  blocked = await get_underperforming_bots(session)
  paused_now: list[str] = []
  active_bots = [
    bot for bot in BOT_TYPES
    if not await is_bot_paused(session, bot)
  ]
  for bot_type in blocked:
    if bot_type == "stocks_futures":
      continue
    if bot_type in active_bots and len(active_bots) == 1:
      continue
    if await is_bot_paused(session, bot_type):
      continue
    await set_bot_paused(session, bot_type, True)
    paused_now.append(bot_type)
  return paused_now


def _gate_recovery_candidate_score(stats: dict[str, Any]) -> float | None:
  """Rank paused shadow bots eligible to replace a losing active gate."""
  pf = stats.get("profit_factor")
  pnl = float(stats.get("total_pnl") or 0)
  wr = float(stats.get("win_rate") or 0)
  if pf is None or pf < GATE_RECOVERY_MIN_PF or pnl <= 0:
    return None
  return float(pf) * (1.0 + wr)


async def _best_gate_recovery_candidate(session: AsyncSession) -> str | None:
  """Pick the best paused shadow bot to serve as active gate."""
  from app.engines.platform_settings import get_paused_bot_types

  paused = set(await get_paused_bot_types(session))
  per_bot = await ProfitabilityGate(session).evaluate_per_bot()

  best_bot: str | None = None
  best_score = -1.0
  for bot_type in GATE_RECOVERY_ROTATION_CANDIDATES:
    if bot_type not in paused:
      continue
    stats = per_bot.get(bot_type) or {}
    wr = float(stats.get("win_rate") or 0)
    pf = stats.get("profit_factor")
    pnl = float(stats.get("total_pnl") or 0)
    if not in_shadow_graduation_nudge(
      bot_type,
      wr,
      profit_factor=pf,
      total_pnl=pnl,
    ):
      continue
    score = _gate_recovery_candidate_score(stats)
    if score is None or score <= best_score:
      continue
    best_bot = bot_type
    best_score = score
  return best_bot


async def sync_gate_recovery_rotation(session: AsyncSession) -> dict[str, str] | None:
  """Pause a losing stocks gate during early verification and activate a profitable shadow bot."""
  from app.engines.platform_settings import get_paused_bot_types, is_bot_paused, set_bot_paused

  paused_types = set(await get_paused_bot_types(session))
  active_bots = [bot for bot in BOT_TYPES if bot not in paused_types]

  if not active_bots:
    best_bot = await _best_gate_recovery_candidate(session)
    if best_bot is None:
      return None
    await set_bot_paused(session, best_bot, False)
    return {"paused": "all", "activated": best_bot}

  gate = await ProfitabilityGate(session).evaluate()
  active_trades = int(gate.get("total_trades") or 0)
  active_pf = gate.get("profit_factor")
  active_pnl = float(gate.get("total_pnl") or 0)

  if active_trades >= EARLY_VERIFICATION_MAX_TRADES:
    return None
  if active_pf is not None and active_pf >= GATE_RECOVERY_MIN_PF and active_pnl > 0:
    return None
  if await is_bot_paused(session, "stocks_futures"):
    return None

  best_bot = await _best_gate_recovery_candidate(session)
  if best_bot is None:
    return None

  await set_bot_paused(session, "stocks_futures", True)
  await set_bot_paused(session, best_bot, False)
  return {"paused": "stocks_futures", "activated": best_bot}


async def try_graduate_paused_bots(session: AsyncSession) -> list[str]:
  """Unpause bots that meet per-bot graduation thresholds without hurting active gate.

  Only graduates when the active (non-paused) gate win rate is at or above target,
  or when active gate has fewer than 30 trades (early verification).
  """
  from app.engines.platform_settings import is_bot_paused, set_bot_paused

  gate = ProfitabilityGate(session)
  active = await gate.evaluate()
  active_wr = float(active.get("win_rate") or 0)
  active_total = int(active.get("total_trades") or 0)
  if active_total >= 30 and active_wr < ProfitabilityGate.MIN_WIN_RATE:
    return []

  per_bot = await gate.evaluate_per_bot()
  graduated: list[str] = []
  for bot_type, stats in per_bot.items():
    if not stats.get("paused"):
      continue
    if not stats.get("graduation_ready"):
      continue
    if not await is_bot_paused(session, bot_type):
      continue
    await set_bot_paused(session, bot_type, False)
    graduated.append(bot_type)
  return graduated


async def get_gate_entry_tightening(session: AsyncSession) -> GateEntryTightening:
  """Return stricter entry rules while aggregate gate win rate is below target."""
  gate = await ProfitabilityGate(session).evaluate()
  win_rate = float(gate.get("win_rate") or 0)
  total = int(gate.get("total_trades") or 0)
  per_bot = await ProfitabilityGate(session).evaluate_per_bot()
  comm = per_bot.get("commodities") or {}
  commodities_nudge_cap: int | None = None
  if not comm.get("paused") and is_profitable_graduation_nudge(
    "commodities",
    comm.get("win_rate"),
    profit_factor=comm.get("profit_factor"),
    total_pnl=comm.get("total_pnl"),
  ):
    commodities_nudge_cap = ACTIVE_GATE_GRADUATION_NUDGE_MAX_OPEN

  if total < 30 or win_rate >= ProfitabilityGate.MIN_WIN_RATE:
    return GateEntryTightening(
      active=False,
      win_rate=win_rate,
      min_sentiment=0.0,
      require_macd_bullish=False,
      min_composite_boost=0.0,
      max_commodities_open_positions=commodities_nudge_cap,
    )

  deficit = ProfitabilityGate.MIN_WIN_RATE - win_rate
  boost = min(0.08, deficit * 0.4)

  pm_cap = 1 if deficit >= 0.05 else (2 if deficit >= 0.02 else None)
  crypto_cap = 1 if deficit >= 0.05 else (2 if deficit >= 0.02 else None)
  commodities_cap = 2 if deficit >= 0.02 else None
  if commodities_nudge_cap is not None:
    commodities_cap = (
      max(commodities_cap, commodities_nudge_cap)
      if commodities_cap is not None
      else commodities_nudge_cap
    )
  blocked = await get_underperforming_bots(session)
  blocked -= await active_gate_entry_exempt_bots(session)
  stocks_cap = 3 if "stocks_futures" not in blocked and deficit >= 0.02 else None

  return GateEntryTightening(
    active=True,
    win_rate=win_rate,
    min_sentiment=0.04 + boost,
    require_macd_bullish=deficit >= 0.02,
    min_composite_boost=boost,
    max_pm_open_positions=pm_cap,
    max_crypto_open_positions=crypto_cap,
    max_commodities_open_positions=commodities_cap,
    max_stocks_open_positions=stocks_cap,
    blocked_new_entries=blocked,
  )


def bot_min_sentiment(bot_type: str, tightening: GateEntryTightening) -> float:
  if not tightening.active:
    return 0.0
  return max(tightening.min_sentiment, BOT_MIN_SENTIMENT.get(bot_type, 0.05))


def stocks_in_us_session() -> bool:
  """US regular session ~9:30–16:00 ET (13:30–21:00 UTC); extend 30m for closes."""
  now = datetime.utcnow()
  if now.weekday() >= 5:
    return False
  minutes = now.hour * 60 + now.minute
  return 13 * 60 + 30 <= minutes <= 21 * 60 + 30


def is_commodities_futures_symbol(symbol: str) -> bool:
  return symbol.endswith("=F")


COMMODITIES_CME_SUNDAY_REOPEN_HOUR_UTC = 22
COMMODITIES_CME_SUNDAY_REOPEN_MINUTE_UTC = 0


def _commodities_cme_sunday_reopen_utc(day: datetime) -> datetime:
  """Sunday evening CME Globex reopen (5pm CT ≈ 22:00 UTC)."""
  return day.replace(
    hour=COMMODITIES_CME_SUNDAY_REOPEN_HOUR_UTC,
    minute=COMMODITIES_CME_SUNDAY_REOPEN_MINUTE_UTC,
    second=0,
    microsecond=0,
  )


def _commodities_cme_next_reopen_utc(now: datetime | None = None) -> datetime:
  """Next CME futures reopen after *now* (always a Sunday 22:00 UTC)."""
  now = now or datetime.utcnow()
  reopen = _commodities_cme_sunday_reopen_utc(now)
  weekday = now.weekday()
  if weekday == 6 and now < reopen:
    return reopen
  if weekday < 6:
    days_ahead = 6 - weekday
    return _commodities_cme_sunday_reopen_utc(now + timedelta(days=days_ahead))
  # Saturday — reopen is tomorrow (Sunday) evening.
  return _commodities_cme_sunday_reopen_utc(now + timedelta(days=1))


def commodities_futures_weekend_closed() -> bool:
  """CME metals/energy futures are closed Sat and until Sunday 22:00 UTC reopen."""
  now = datetime.utcnow()
  weekday = now.weekday()
  if weekday == 5:
    return True
  if weekday == 6:
    reopen = _commodities_cme_sunday_reopen_utc(now)
    return now < reopen
  return False


def commodities_weekend_stale_signal_exit_blocked(
  *,
  symbol: str,
  unrealized: float,
  signal_direction: str,
) -> bool:
  """Hold flat futures over the weekend — stale MACD crosses should not force exits."""
  if not is_commodities_futures_symbol(symbol):
    return False
  if not commodities_futures_weekend_closed():
    return False
  if signal_direction != "sell":
    return False
  return abs(unrealized) < COMMODITIES_FUTURES_WEEKEND_FLAT_EXIT_BAND_USD


def commodities_weekend_futures_entry_blocked(symbol: str) -> bool:
  """Block new CME futures entries on stale weekend Yahoo feeds."""
  return is_commodities_futures_symbol(symbol) and commodities_futures_weekend_closed()


def commodities_weekend_forex_entry_blocked(
  *,
  bot_type: str,
  shadow_mode: bool,
  symbol: str,
  graduation_nudge: bool,
) -> bool:
  """Block idle forex re-entry during weekend prep — reserve slots for CME recovery futures."""
  if shadow_mode or bot_type != "commodities" or not graduation_nudge:
    return False
  if not commodities_futures_weekend_closed():
    return False
  if is_commodities_futures_symbol(symbol) or symbol in COMMODITIES_WEEKEND_SPOT_SYMBOLS:
    return False
  return symbol.endswith("=X")


def commodities_weekend_spot_entry_blocked(
  *,
  bot_type: str,
  shadow_mode: bool,
  symbol: str,
  graduation_nudge: bool,
) -> bool:
  """Block weekend spot proxy entries while CME closed — prefer futures at reopen."""
  if shadow_mode or bot_type != "commodities" or not graduation_nudge:
    return False
  if not commodities_futures_weekend_closed():
    return False
  return symbol in COMMODITIES_WEEKEND_SPOT_SYMBOLS


def commodities_session_info() -> dict[str, Any]:
  """UTC schedule for CME futures — weekend stale-feed guard aligns with session closed."""
  now = datetime.utcnow()
  if not commodities_futures_weekend_closed():
    if now.weekday() == 6 and now.hour >= COMMODITIES_CME_SUNDAY_REOPEN_HOUR_UTC:
      open_at = _commodities_cme_sunday_reopen_utc(now)
    else:
      open_at = now.replace(hour=0, minute=0, second=0, microsecond=0)
    minutes_since_open = max(0, int((now - open_at).total_seconds() // 60))
    return {
      "in_session": True,
      "mode": "entries",
      "session_open_utc": open_at.isoformat(),
      "minutes_until_open": 0,
      "minutes_until_close": None,
      "minutes_since_open": minutes_since_open,
    }

  open_at = _commodities_cme_next_reopen_utc(now)
  minutes_until_open = max(0, int((open_at - now).total_seconds() // 60))
  mode = "pre_session" if minutes_until_open <= 90 else "weekend_closed"
  return {
    "in_session": False,
    "mode": mode,
    "session_open_utc": open_at.isoformat(),
    "minutes_until_open": minutes_until_open,
    "minutes_until_close": None,
    "minutes_since_open": 0,
  }


COMMODITIES_MONDAY_SCAN_OPEN_HOUR_MINUTES = 60
COMMODITIES_MONDAY_SCAN_PREP_MINUTES = 90
COMMODITIES_GRADUATION_PREP_MINUTES = 4320  # 72h — weekend TV refresh before CME reopen
# NG first — typical Sunday CME reopen leader; then energy/metals breadth.
COMMODITIES_MONDAY_FUTURES_SCAN_ORDER = ("NG=F", "CL=F", "GC=F", "SI=F", "HG=F")


def _apply_commodities_monday_futures_order(symbols: list[str]) -> list[str]:
  """Put CME futures ahead of spot proxies when Monday scan priority is active."""
  futures_first = [s for s in COMMODITIES_MONDAY_FUTURES_SCAN_ORDER if s in symbols]
  futures_rest = [
    s for s in symbols if is_commodities_futures_symbol(s) and s not in futures_first
  ]
  non_futures = [s for s in symbols if not is_commodities_futures_symbol(s)]
  return futures_first + futures_rest + non_futures


def commodities_pre_session_prep_window_minutes(graduation_nudge: bool) -> int:
  """How far ahead of CME reopen to refresh TradingView boosts for commodities prep."""
  if graduation_nudge:
    return COMMODITIES_GRADUATION_PREP_MINUTES
  return COMMODITIES_MONDAY_SCAN_PREP_MINUTES


def commodities_monday_scan_priority_active(
  session_info: dict[str, Any],
  *,
  graduation_nudge: bool = False,
) -> bool:
  """Prioritize chronic futures recovery symbols pre-open and during the first hour."""
  if graduation_nudge and commodities_graduation_prep_active(graduation_nudge):
    return True
  if session_info.get("in_session"):
    since = session_info.get("minutes_since_open")
    return since is not None and since <= COMMODITIES_MONDAY_SCAN_OPEN_HOUR_MINUTES
  minutes_until = session_info.get("minutes_until_open")
  return (
    minutes_until is not None
    and minutes_until <= COMMODITIES_MONDAY_SCAN_PREP_MINUTES
  )


def prioritize_commodities_monday_scan(
  symbols: list[str],
  *,
  chronic_losers: frozenset[str],
  proven_winners: frozenset[str],
  session_info: dict[str, Any],
  graduation_nudge: bool = False,
) -> list[str]:
  """Scan chronic CME futures first ahead of Monday reopen / open hour."""
  recovery = [
    s for s in symbols
    if s in chronic_losers and is_commodities_futures_symbol(s)
  ]
  if graduation_nudge and recovery:
    winners = [s for s in symbols if s in proven_winners and s not in recovery]
    rest = [s for s in symbols if s not in recovery and s not in winners]
    if not commodities_monday_scan_priority_active(
      session_info,
      graduation_nudge=graduation_nudge,
    ):
      return recovery + winners + rest
  if not commodities_monday_scan_priority_active(
    session_info,
    graduation_nudge=graduation_nudge,
  ):
    if proven_winners:
      winners = [s for s in symbols if s in proven_winners]
      rest = [s for s in symbols if s not in proven_winners]
      return winners + rest
    return symbols

  winners = [s for s in symbols if s in proven_winners and s not in recovery]
  rest = [s for s in symbols if s not in recovery and s not in winners]
  return recovery + winners + _apply_commodities_monday_futures_order(rest)


def stocks_session_info() -> dict[str, Any]:
  """UTC schedule for US cash session — used by CRM status and pre-session prep."""
  now = datetime.utcnow()
  open_minutes = 13 * 60 + 30
  close_minutes = 21 * 60 + 30
  weekday = now.weekday()
  now_minutes = now.hour * 60 + now.minute

  def at_minutes(day: datetime, minutes: int) -> datetime:
    return day.replace(hour=minutes // 60, minute=minutes % 60, second=0, microsecond=0)

  def next_weekday(start: datetime) -> datetime:
    day = start
    while day.weekday() >= 5:
      day += timedelta(days=1)
    return day

  in_session = weekday < 5 and open_minutes <= now_minutes <= close_minutes
  if in_session:
    open_at = at_minutes(now, open_minutes)
    close_at = at_minutes(now, close_minutes)
    minutes_since_open = max(0, int((now - open_at).total_seconds() // 60))
    minutes_until_close = max(0, int((close_at - now).total_seconds() // 60))
    mode = "entries"
    if minutes_until_close <= STOCKS_SESSION_CLOSE_WIND_DOWN_MINUTES:
      mode = "winddown"
    return {
      "in_session": True,
      "mode": mode,
      "session_open_utc": open_at.isoformat(),
      "session_close_utc": close_at.isoformat(),
      "minutes_until_open": 0,
      "minutes_until_close": minutes_until_close,
      "minutes_since_open": minutes_since_open,
    }

  if weekday < 5 and now_minutes < open_minutes:
    open_at = at_minutes(now, open_minutes)
  else:
    open_at = at_minutes(next_weekday(now + timedelta(days=1)), open_minutes)

  minutes_until_open = max(0, int((open_at - now).total_seconds() // 60))
  after_close_today = weekday < 5 and now_minutes > close_minutes
  if after_close_today:
    mode = "winddown_only"
  elif minutes_until_open <= 90:
    mode = "pre_session"
  else:
    mode = "outside_session"
  return {
    "in_session": False,
    "mode": mode,
    "session_open_utc": open_at.isoformat(),
    "session_close_utc": at_minutes(open_at, close_minutes).isoformat(),
    "minutes_until_open": minutes_until_open,
    "minutes_until_close": None,
    "minutes_since_open": 0,
  }


STOCKS_MONDAY_SCAN_OPEN_HOUR_MINUTES = 60
STOCKS_MONDAY_SCAN_PREP_MINUTES = 90
STOCKS_TRADE_COUNT_PREP_MINUTES = 4320  # 72h — weekend TV refresh before Monday open


def build_session_prep_status(
  *,
  stocks_session: dict[str, Any],
  commodities_session: dict[str, Any],
  stocks_trade_count_nudge: bool,
  commodities_graduation_nudge: bool,
) -> dict[str, Any]:
  """Summarize whether extended weekend TV prep windows are active."""
  stocks_minutes = stocks_session.get("minutes_until_open")
  commodities_minutes = commodities_session.get("minutes_until_open")
  stocks_window = stocks_pre_session_prep_window_minutes(stocks_trade_count_nudge)
  commodities_window = commodities_pre_session_prep_window_minutes(
    commodities_graduation_nudge
  )

  def _prep_entry(
    bot_type: str,
    session_info: dict[str, Any],
    prep_window: int,
    nudge: bool,
    nudge_label: str,
    *,
    gate_fast_scan_active: bool,
  ) -> dict[str, Any]:
    minutes_until = session_info.get("minutes_until_open")
    in_session = bool(session_info.get("in_session"))
    prep_active = (
      not in_session
      and minutes_until is not None
      and minutes_until <= prep_window
    )
    return {
      "bot_type": bot_type,
      "prep_active": prep_active,
      "prep_window_minutes": prep_window,
      "minutes_until_open": minutes_until,
      "in_session": in_session,
      "extended_weekend_prep": nudge and prep_window > 90,
      "nudge_active": nudge,
      "nudge_label": nudge_label if nudge else None,
      "session_mode": session_info.get("mode"),
      "gate_fast_scan_active": gate_fast_scan_active,
    }

  return {
    "stocks_futures": _prep_entry(
      "stocks_futures",
      stocks_session,
      stocks_window,
      stocks_trade_count_nudge,
      "trade-count nudge",
      gate_fast_scan_active=stocks_gate_fast_scan_active(
        stocks_session,
        trade_count_nudge=stocks_trade_count_nudge,
      ),
    ),
    "commodities": _prep_entry(
      "commodities",
      commodities_session,
      commodities_window,
      commodities_graduation_nudge,
      "graduation nudge",
      gate_fast_scan_active=commodities_gate_fast_scan_active(
        commodities_session,
        graduation_nudge=commodities_graduation_nudge,
      ),
    ),
  }


def stocks_pre_session_prep_window_minutes(trade_count_nudge: bool) -> int:
  """How far ahead of US open to refresh TradingView boosts for stocks prep."""
  if trade_count_nudge:
    return STOCKS_TRADE_COUNT_PREP_MINUTES
  return STOCKS_MONDAY_SCAN_PREP_MINUTES


def stocks_monday_scan_priority_active(session_info: dict[str, Any]) -> bool:
  """Prioritize chronic recovery symbols pre-US open and during the first hour."""
  if session_info.get("in_session"):
    since = session_info.get("minutes_since_open")
    return since is not None and since <= STOCKS_MONDAY_SCAN_OPEN_HOUR_MINUTES
  minutes_until = session_info.get("minutes_until_open")
  return (
    minutes_until is not None
    and minutes_until <= STOCKS_MONDAY_SCAN_PREP_MINUTES
  )


def prioritize_stocks_monday_scan(
  symbols: list[str],
  *,
  chronic_losers: frozenset[str],
  proven_winners: frozenset[str],
  session_info: dict[str, Any],
  trade_count_nudge: bool = False,
) -> list[str]:
  """Scan chronic stock recovery symbols first ahead of Monday US open / open hour."""
  if trade_count_nudge and proven_winners:
    winners = sorted(s for s in symbols if s in proven_winners)
    if not stocks_monday_scan_priority_active(session_info):
      rest = [s for s in symbols if s not in proven_winners]
      return winners + rest
    recovery = [s for s in symbols if s in chronic_losers and s not in proven_winners]
    rest = [s for s in symbols if s not in winners and s not in recovery]
    return winners + recovery + rest
  if not stocks_monday_scan_priority_active(session_info):
    if proven_winners:
      winners = [s for s in symbols if s in proven_winners]
      rest = [s for s in symbols if s not in proven_winners]
      return winners + rest
    return symbols

  recovery = [s for s in symbols if s in chronic_losers]
  winners = [s for s in symbols if s in proven_winners and s not in recovery]
  rest = [s for s in symbols if s not in recovery and s not in winners]
  return recovery + winners + rest


def stocks_gate_entry_sentiment_ok(sentiment: float, integration_boost: float) -> bool:
  """During gate tightening, stocks need non-negative sentiment or a TV/integration boost."""
  return sentiment >= 0 or integration_boost > 0.03


def stocks_negative_pf_blocks_entry(
  *,
  bot_type: str,
  symbol: str,
  composite: float,
  proven_winners: frozenset[str],
  profit_factor: float | None,
  total_trades: int,
  bot_win_rate: float | None = None,
) -> bool:
  """During early verification with negative PF, only allow strong proven-winner entries."""
  from app.engines.profitability_gate import ProfitabilityGate

  if bot_type != "stocks_futures":
    return False
  if total_trades >= EARLY_VERIFICATION_MAX_TRADES:
    return False
  if profit_factor is None or profit_factor >= 1.0:
    return False
  min_composite = STOCKS_NEGATIVE_PF_MIN_COMPOSITE
  if (
    bot_win_rate is not None
    and bot_win_rate >= ProfitabilityGate.GRADUATION_MIN_WIN_RATE
  ):
    min_composite = STOCKS_NEGATIVE_PF_HIGH_WR_MIN_COMPOSITE
    if stocks_trade_count_graduation_nudge(
      bot_type, True, bot_win_rate, total_trades
    ):
      min_composite = STOCKS_TRADE_COUNT_RECOVERY_MIN_COMPOSITE
  if symbol in proven_winners and composite >= min_composite:
    return False
  return True


def stocks_proven_winner_recovery_entry_ok(
  *,
  bot_type: str,
  shadow_mode: bool,
  symbol: str,
  proven_winners: frozenset[str],
  bot_win_rate: float | None,
  composite: float,
  signal_direction: str,
  macd_signal: str,
  total_trades: int = 0,
) -> bool:
  """High-WR stocks shadow can re-enter proven winners with aligned bullish signals."""
  from app.engines.profitability_gate import ProfitabilityGate

  if not (shadow_mode and bot_type == "stocks_futures"):
    return False
  if symbol not in proven_winners:
    return False
  if bot_win_rate is None or bot_win_rate < ProfitabilityGate.GRADUATION_MIN_WIN_RATE:
    return False
  if signal_direction != "buy" or macd_signal != "bullish":
    return False
  min_composite = STOCKS_PROVEN_RECOVERY_MIN_COMPOSITE
  if stocks_trade_count_graduation_nudge(
    bot_type, shadow_mode, bot_win_rate, total_trades
  ):
    min_composite = STOCKS_TRADE_COUNT_RECOVERY_MIN_COMPOSITE
  return composite >= min_composite


def commodities_weekend_spot_gate_skip_bypass(
  *,
  bot_type: str,
  shadow_mode: bool,
  symbol: str,
  graduation_nudge: bool,
  signal_direction: str,
  macd_signal: str,
  composite: float,
) -> bool:
  """Weekend spot gold proxies can bypass recent/large gate_skip and chronic blocks."""
  if shadow_mode or bot_type != "commodities":
    return False
  if not graduation_nudge:
    return False
  if symbol not in COMMODITIES_WEEKEND_SPOT_SYMBOLS:
    return False
  if not commodities_futures_weekend_closed():
    return False
  if signal_direction != "buy" or macd_signal != "bullish":
    return False
  return composite >= COMMODITIES_WEEKEND_SPOT_GATE_SKIP_COMPOSITE_FLOOR


def commodities_monday_futures_gate_skip_bypass(
  *,
  bot_type: str,
  shadow_mode: bool,
  symbol: str,
  graduation_nudge: bool,
  signal_direction: str,
  macd_signal: str,
  composite: float,
) -> bool:
  """CME futures bypass gate_skip/chronic blocks pre-open and first hour after reopen."""
  if shadow_mode or bot_type != "commodities":
    return False
  if not graduation_nudge:
    return False
  if not is_commodities_futures_symbol(symbol):
    return False
  if not commodities_monday_scan_priority_active(
    commodities_session_info(),
    graduation_nudge=graduation_nudge,
  ):
    return False
  if signal_direction != "buy" or macd_signal != "bullish":
    return False
  return composite >= commodities_recovery_composite_floor(graduation_nudge)


def commodities_recovery_composite_floor(graduation_nudge: bool = False) -> float:
  """Eased composite floor for gate commodities during graduation prep/open window."""
  if commodities_graduation_prep_active(graduation_nudge):
    return COMMODITIES_GRADUATION_OPEN_COMPOSITE_FLOOR
  return COMMODITIES_HIGH_COMPOSITE_RECOVERY_FLOOR


def commodities_graduation_prep_active(graduation_nudge: bool = False) -> bool:
  """Whether gate commodities graduation prep easings apply (72h pre-open + first hour)."""
  if not graduation_nudge:
    return False
  session = commodities_session_info()
  if session.get("in_session"):
    since = session.get("minutes_since_open")
    return since is not None and since <= COMMODITIES_MONDAY_SCAN_OPEN_HOUR_MINUTES
  minutes_until = session.get("minutes_until_open")
  if minutes_until is None:
    return False
  return minutes_until <= COMMODITIES_GRADUATION_PREP_MINUTES


def commodities_gate_fast_scan_active(
  session_info: dict[str, Any] | None = None,
  *,
  graduation_nudge: bool = False,
) -> bool:
  """Whether active-gate commodities should scan at gate_active_scan_interval."""
  session = session_info or commodities_session_info()
  if session.get("in_session"):
    return True
  if commodities_monday_scan_priority_active(session, graduation_nudge=graduation_nudge):
    return True
  return commodities_graduation_prep_active(graduation_nudge)


def stocks_gate_fast_scan_active(
  session_info: dict[str, Any] | None = None,
  *,
  trade_count_nudge: bool = False,
) -> bool:
  """Whether shadow stocks should scan at gate_active_scan_interval during trade-count prep."""
  if not trade_count_nudge:
    return False
  session = session_info or stocks_session_info()
  if session.get("in_session"):
    return True
  if stocks_monday_scan_priority_active(session):
    return True
  minutes_until = session.get("minutes_until_open")
  return (
    minutes_until is not None
    and minutes_until <= STOCKS_TRADE_COUNT_PREP_MINUTES
  )


def stocks_monday_gate_skip_bypass(
  *,
  bot_type: str,
  shadow_mode: bool,
  symbol: str,
  proven_winners: frozenset[str],
  bot_win_rate: float | None,
  total_trades: int,
  signal_direction: str,
  macd_signal: str,
  composite: float,
) -> bool:
  """Proven stock shadow winners bypass gate_skip/chronic blocks pre-US open and first hour."""
  if not shadow_mode or bot_type != "stocks_futures":
    return False
  if not stocks_trade_count_graduation_nudge(
    bot_type, shadow_mode, bot_win_rate, total_trades
  ):
    return False
  if symbol not in proven_winners:
    return False
  if not stocks_monday_scan_priority_active(stocks_session_info()):
    return False
  if signal_direction != "buy" or macd_signal != "bullish":
    return False
  return composite >= STOCKS_TRADE_COUNT_RECOVERY_MIN_COMPOSITE


def commodities_high_composite_recovery_entry_ok(
  *,
  bot_type: str,
  shadow_mode: bool,
  symbol: str,
  composite: float,
  signal_direction: str,
  macd_signal: str,
  graduation_nudge: bool = False,
) -> bool:
  """Active-gate commodities can re-enter chronic futures with strong aligned composites."""
  from app.engines.market_data import CRYPTO_LIVE_PRICE_PROXY

  if shadow_mode or bot_type != "commodities":
    return False
  if symbol in CRYPTO_LIVE_PRICE_PROXY:
    return False
  if signal_direction != "buy" or macd_signal != "bullish":
    return False
  return composite >= commodities_recovery_composite_floor(graduation_nudge)


def stocks_proven_winner_sentiment_gate_ok(
  *,
  bot_type: str,
  shadow_mode: bool,
  symbol: str,
  proven_winners: frozenset[str],
  bot_win_rate: float | None,
  composite: float,
  signal_direction: str,
  macd_signal: str,
  sentiment: float,
  integration_boost: float,
  total_trades: int = 0,
) -> bool:
  """Allow proven-winner recovery entries despite weak sentiment during gate tightening."""
  if stocks_gate_entry_sentiment_ok(sentiment, integration_boost):
    return True
  return stocks_proven_winner_recovery_entry_ok(
    bot_type=bot_type,
    shadow_mode=shadow_mode,
    symbol=symbol,
    proven_winners=proven_winners,
    bot_win_rate=bot_win_rate,
    composite=composite,
    signal_direction=signal_direction,
    macd_signal=macd_signal,
    total_trades=total_trades,
  )


COMMODITIES_MONDAY_RECOVERY_SOFT_BLOCKERS = frozenset({
  "weekend_futures_closed",
  "signal_sell",
  "open_cap",
  "open_cap_proxy",
  "gate_skip",
  "chronic_loser",
  "symbol_cooldown",
  "macd",
  "volume",
  "sentiment_gate",
})

COMMODITIES_MONDAY_OPEN_READY_BLOCKERS = frozenset({"weekend_futures_closed"})


def commodities_monday_open_ready(
  *,
  bot_type: str,
  shadow_mode: bool,
  symbol: str,
  composite: float,
  signal_direction: str,
  macd_signal: str,
  blockers: list[str],
  graduation_nudge: bool = False,
) -> bool:
  """Bullish high-composite futures that will enter as soon as CME reopens."""
  if not commodities_high_composite_recovery_entry_ok(
    bot_type=bot_type,
    shadow_mode=shadow_mode,
    symbol=symbol,
    composite=composite,
    signal_direction=signal_direction,
    macd_signal=macd_signal,
    graduation_nudge=graduation_nudge,
  ):
    return False
  if not blockers:
    return False
  return set(blockers).issubset(COMMODITIES_MONDAY_OPEN_READY_BLOCKERS)


def commodities_monday_recovery_ready(
  *,
  bot_type: str,
  shadow_mode: bool,
  symbol: str,
  composite: float,
  blockers: list[str],
  graduation_nudge: bool = False,
) -> bool:
  """High-composite commodities futures blocked only by weekend or sell signal."""
  if not commodities_high_composite_recovery_entry_ok(
    bot_type=bot_type,
    shadow_mode=shadow_mode,
    symbol=symbol,
    composite=composite,
    signal_direction="buy",
    macd_signal="bullish",
    graduation_nudge=graduation_nudge,
  ):
    return False
  if not blockers:
    return False
  return set(blockers).issubset(COMMODITIES_MONDAY_RECOVERY_SOFT_BLOCKERS)


STOCKS_MONDAY_RECOVERY_SOFT_BLOCKERS = frozenset({
  "signal_sell",
  "macd",
  "volume",
  "sentiment_gate",
  "gate_skip",
  "stocks_negative_pf",
})

STOCKS_MONDAY_OPEN_READY_BLOCKERS = frozenset({"gate_skip"})


def stocks_monday_open_ready(
  *,
  bot_type: str,
  shadow_mode: bool,
  symbol: str,
  proven_winners: frozenset[str],
  bot_win_rate: float | None,
  composite: float,
  signal_direction: str,
  macd_signal: str,
  blockers: list[str],
  total_trades: int = 0,
) -> bool:
  """Proven stock shadow winner that will enter when gate_skip clears pre-US open."""
  if not stocks_proven_winner_recovery_entry_ok(
    bot_type=bot_type,
    shadow_mode=shadow_mode,
    symbol=symbol,
    proven_winners=proven_winners,
    bot_win_rate=bot_win_rate,
    composite=composite,
    signal_direction=signal_direction,
    macd_signal=macd_signal,
    total_trades=total_trades,
  ):
    return False
  if not blockers:
    return False
  return set(blockers).issubset(STOCKS_MONDAY_OPEN_READY_BLOCKERS)


def stocks_monday_recovery_ready(
  *,
  bot_type: str,
  shadow_mode: bool,
  symbol: str,
  proven_winners: frozenset[str],
  bot_win_rate: float | None,
  composite: float,
  blockers: list[str],
  total_trades: int = 0,
) -> bool:
  """Proven stock shadow winner blocked only by session/signal gates that flip on aligned setups."""
  if not stocks_proven_winner_recovery_entry_ok(
    bot_type=bot_type,
    shadow_mode=shadow_mode,
    symbol=symbol,
    proven_winners=proven_winners,
    bot_win_rate=bot_win_rate,
    composite=composite,
    signal_direction="buy",
    macd_signal="bullish",
    total_trades=total_trades,
  ):
    return False
  if not blockers:
    return False
  remaining = {
    b for b in blockers
    if not b.startswith("composite<") and not b.startswith("sentiment<")
  }
  return remaining.issubset(STOCKS_MONDAY_RECOVERY_SOFT_BLOCKERS)


async def build_gate_ws_payload(session: AsyncSession) -> dict[str, Any]:
  """Gate tightening + profitability summary for WebSocket and status APIs."""
  gate_tightening = await get_gate_entry_tightening(session)
  profitability = await ProfitabilityGate(session).evaluate()

  chronic_loser_symbols: dict[str, list[str]] = {}
  recent_loser_symbols: dict[str, list[str]] = {}
  proven_winner_symbols: dict[str, list[str]] = {}
  from app.engines.platform_settings import is_bot_paused

  for bot_type in BOT_TYPES:
    shadow = await is_bot_paused(session, bot_type)
    if not gate_tightening.active and not shadow:
      continue
    skip = await get_gate_skip_symbols(session, bot_type)
    chronic = await get_chronic_loser_symbols(session, bot_type)
    recent = await get_recent_loser_symbols(session, bot_type)
    if skip:
      chronic_loser_symbols[bot_type] = sorted(skip)
    if recent - chronic:
      recent_loser_symbols[bot_type] = sorted(recent - chronic)
    if bot_type in ("stocks_futures", "commodities"):
      winners = await get_proven_winner_symbols(session, bot_type)
      if winners:
        proven_winner_symbols[bot_type] = sorted(winners)

  in_session = stocks_in_us_session()
  session_info = stocks_session_info()
  commodities_session = commodities_session_info()
  per_bot = await ProfitabilityGate(session).evaluate_per_bot()
  return {
    "profitability_gate": profitability,
    "per_bot_gate": per_bot,
    "gate_entry_tightening": {
      "active": gate_tightening.active,
      "win_rate": gate_tightening.win_rate,
      "min_sentiment": gate_tightening.min_sentiment,
      "require_macd_bullish": gate_tightening.require_macd_bullish,
      "min_composite_boost": gate_tightening.min_composite_boost,
      "max_pm_open_positions": gate_tightening.max_pm_open_positions,
      "max_crypto_open_positions": gate_tightening.max_crypto_open_positions,
      "max_commodities_open_positions": gate_tightening.max_commodities_open_positions,
      "max_stocks_open_positions": gate_tightening.max_stocks_open_positions,
      "blocked_new_entries": sorted(gate_tightening.blocked_new_entries),
      "chronic_loser_symbols": chronic_loser_symbols,
      "recent_loser_symbols": recent_loser_symbols,
      "proven_winner_symbols": proven_winner_symbols,
      "stocks_proven_winners_only": bool(
        gate_tightening.active and proven_winner_symbols.get("stocks_futures")
      ),
    },
    "bot_sessions": {
      "stocks_futures": session_info,
      "commodities": commodities_session,
    },
  }
