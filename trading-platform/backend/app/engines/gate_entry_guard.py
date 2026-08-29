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
PROFITABLE_SHADOW_LOSS_WIND_DOWN_USD = 5.0
GRADUATION_NUDGE_PROFIT_LOCK_USD = 3.0
PROFITABLE_SHADOW_PROFIT_LOCK_USD = 4.0
SHADOW_GRADUATION_LOSS_COOLDOWN_MULTIPLIER = 2
GRADUATION_NUDGE_SENTIMENT_EASE_BY_BOT = {
  "crypto": 0.04,
  "commodities": 0.02,
}
COMMODITIES_GRADUATION_BULLISH_SIGNAL_EASE = 0.09
COMMODITIES_GRADUATION_BULLISH_SIGNAL_FLOOR = 0.20
CRYPTO_GRADUATION_BULLISH_SIGNAL_EASE = 0.06
CRYPTO_GRADUATION_BULLISH_SIGNAL_FLOOR = 0.24
CRYPTO_SHADOW_REVIEW_BYPASS_COMPOSITE = 0.32
CRYPTO_SHADOW_COMPOSITE_SENTIMENT_MARGIN = 0.01
CRYPTO_SHADOW_BULLISH_SENTIMENT_COMPOSITE_FLOOR = 0.26


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
  if (
    bot_type in ("crypto", "commodities")
    and in_shadow_graduation_nudge(
      bot_type,
      bot_win_rate,
      profit_factor=profit_factor,
      total_pnl=total_pnl,
    )
  ):
    nudge_cap = SHADOW_GRADUATION_NUDGE_MAX_OPEN
    if is_profitable_graduation_nudge(
      bot_type,
      bot_win_rate,
      profit_factor=profit_factor,
      total_pnl=total_pnl,
    ):
      nudge_cap = SHADOW_PROFITABLE_GRADUATION_NUDGE_MAX_OPEN
    return max(base, nudge_cap)
  return base


def open_position_cap_blocks_entry(
  bot_type: str,
  *,
  shadow_mode: bool,
  open_count: int,
  gate_tightening: GateEntryTightening,
  shadow_open_cap: int | None,
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
  cap = gate_caps.get(bot_type)
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
STOCKS_SESSION_CLOSE_WIND_DOWN_MINUTES = 30
STOCKS_SESSION_CLOSE_FORCE_MINUTES = 15
DEFAULT_ENTRY_MIN_SIGNAL_FLOOR = 0.08


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
  """True when whale tracker aligns with DexScreener or Hyperliquid on the same symbol."""
  reason = integration_reason.lower()
  if integration_boost < 0.10:
    return False
  has_whale = "wallet" in reason
  has_meme_intel = "dexscreener" in reason or "hyperliquid" in reason or "memecoin_confluence" in reason
  return has_whale and has_meme_intel


def shadow_intel_composite_override(
  bot_type: str,
  *,
  graduation_nudge: bool,
  shadow_mode: bool,
  composite: float,
  entry_min_signal: float,
  integration_boost: float,
  whale_aligned: bool = False,
) -> bool:
  """Allow shadow long when intel composite is strong despite technical sell/hold."""
  if not graduation_nudge_easing_active(
    bot_type,
    graduation_nudge=graduation_nudge,
    shadow_mode=shadow_mode,
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
) -> float:
  """Ease sentiment floor during graduation nudge for shadow and active gate bots."""
  if not graduation_nudge:
    return base_min_sentiment
  ease = GRADUATION_NUDGE_SENTIMENT_EASE_BY_BOT.get(bot_type, 0.0)
  if ease <= 0:
    return base_min_sentiment
  if shadow_mode and bot_type in ("crypto", "commodities"):
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
  return eased


def crypto_graduation_entry_min_signal(
  entry_min_signal: float,
  *,
  bot_type: str,
  graduation_nudge: bool,
  shadow_mode: bool,
  signal_direction: str,
  macd_signal: str,
) -> float:
  """Ease entry threshold for aligned bullish shadow crypto during graduation nudge."""
  if not (graduation_nudge and shadow_mode and bot_type == "crypto"):
    return entry_min_signal
  if signal_direction == "buy" and macd_signal == "bullish":
    return max(
      CRYPTO_GRADUATION_BULLISH_SIGNAL_FLOOR,
      entry_min_signal - CRYPTO_GRADUATION_BULLISH_SIGNAL_EASE,
    )
  return entry_min_signal


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
) -> bool:
  """Allow strong-composite shadow crypto entries during graduation nudge despite weak sentiment."""
  if sentiment + integration_boost >= min_sentiment:
    return True
  if (
    graduation_nudge
    and shadow_mode
    and bot_type == "crypto"
    and composite >= entry_min_signal + CRYPTO_SHADOW_COMPOSITE_SENTIMENT_MARGIN
  ):
    return True
  if (
    graduation_nudge
    and shadow_mode
    and bot_type == "crypto"
    and signal_direction == "buy"
    and macd_signal == "bullish"
    and composite >= CRYPTO_SHADOW_BULLISH_SENTIMENT_COMPOSITE_FLOOR
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
) -> bool:
  """Chronic losers are skippable during graduation nudge when intel override applies."""
  if symbol not in chronic_symbols:
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
  if not graduation_nudge_easing_active(
    bot_type, graduation_nudge=graduation_nudge, shadow_mode=shadow_mode
  ):
    return False
  if held_seconds < min_hold_seconds:
    return False
  if is_profitable_graduation_nudge(
    bot_type,
    bot_win_rate,
    profit_factor=profit_factor,
    total_pnl=total_pnl,
  ):
    threshold = PROFITABLE_SHADOW_LOSS_WIND_DOWN_USD
  else:
    threshold = GRADUATION_NUDGE_LOSS_WIND_DOWN_USD
  return unrealized <= -threshold


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
) -> bool:
  """Bank winners during graduation nudge instead of round-tripping gains."""
  if not graduation_nudge_easing_active(
    bot_type, graduation_nudge=graduation_nudge, shadow_mode=shadow_mode
  ):
    return False
  if held_seconds < min_hold_seconds:
    return False
  if is_profitable_graduation_nudge(
    bot_type,
    bot_win_rate,
    profit_factor=profit_factor,
    total_pnl=total_pnl,
  ):
    threshold = PROFITABLE_SHADOW_PROFIT_LOCK_USD
  else:
    threshold = GRADUATION_NUDGE_PROFIT_LOCK_USD
  return unrealized >= threshold


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
EARLY_VERIFICATION_WIND_DOWN_COOLDOWN_MULTIPLIER = 3
SHADOW_LARGE_LOSS_BYPASS_COMPOSITE = 0.55
SHADOW_LARGE_LOSS_BYPASS_COMPOSITE_BY_BOT = {
  "commodities": 0.42,
}
SHADOW_LARGE_LOSS_BYPASS_INTEGRATION = 0.10
REVIEW_LOSER_DAYS = 3
PROVEN_WINNER_MIN_TRADES = 2
PROVEN_WINNER_MIN_WIN_RATE = 0.50


async def _symbol_trade_stats(session: AsyncSession, bot_type: str) -> dict[str, dict[str, int]]:
  from app.models.entities import Trade

  result = await session.execute(
    select(Trade.symbol, Trade.is_winner).where(
      Trade.bot_type == bot_type,
      Trade.action == "sell",
    )
  )
  stats: dict[str, dict[str, int]] = {}
  for symbol, is_winner in result.all():
    if not symbol:
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
    select(Trade.symbol, Trade.is_winner).where(
      Trade.bot_type == bot_type,
      Trade.action == "sell",
      Trade.executed_at >= cutoff,
    )
  )
  stats: dict[str, dict[str, int]] = {}
  for symbol, is_winner in result.all():
    if not symbol:
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
    select(Trade.symbol, Trade.pnl, Trade.is_winner, Trade.executed_at).where(
      Trade.bot_type == bot_type,
      Trade.action == "sell",
      Trade.executed_at >= cutoff,
    ).order_by(Trade.executed_at.asc())
  )
  sells_by_symbol: dict[str, list[tuple[float | None, bool | None]]] = {}
  for symbol, pnl, is_winner, _executed_at in result.all():
    if not symbol:
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
) -> bool:
  """DB-backed re-entry cooldown — survives deploy restarts."""
  remaining = await symbol_cooldown_remaining_seconds(
    session,
    bot_type,
    symbol,
    chronic_symbols=chronic_symbols,
    large_loss_symbols=large_loss_symbols,
    graduation_nudge=graduation_nudge,
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
) -> int:
  """Seconds until symbol re-entry is allowed after last sell."""
  from app.models.entities import Trade

  result = await session.execute(
    select(Trade.is_winner, Trade.executed_at, Trade.reason)
    .where(
      Trade.bot_type == bot_type,
      Trade.symbol == symbol,
      Trade.action == "sell",
    )
    .order_by(Trade.executed_at.desc())
    .limit(1)
  )
  row = result.first()
  if not row:
    return 0
  is_winner, executed_at, reason = row
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
) -> bool:
  """Hard gate-skip during graduation nudge — review blocks ease on strong active-gate composites."""
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
    return True
  large_bypass_floor = SHADOW_LARGE_LOSS_BYPASS_COMPOSITE_BY_BOT.get(
    bot_type, SHADOW_LARGE_LOSS_BYPASS_COMPOSITE
  )
  if symbol in large_skip:
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
    close_at = at_minutes(now, close_minutes)
    minutes_until_close = max(0, int((close_at - now).total_seconds() // 60))
    mode = "entries"
    if minutes_until_close <= STOCKS_SESSION_CLOSE_WIND_DOWN_MINUTES:
      mode = "winddown"
    return {
      "in_session": True,
      "mode": mode,
      "session_open_utc": at_minutes(now, open_minutes).isoformat(),
      "session_close_utc": close_at.isoformat(),
      "minutes_until_open": 0,
      "minutes_until_close": minutes_until_close,
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
  }


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
) -> bool:
  """During early verification with negative PF, only allow strong proven-winner entries."""
  if bot_type != "stocks_futures":
    return False
  if total_trades >= EARLY_VERIFICATION_MAX_TRADES:
    return False
  if profit_factor is None or profit_factor >= 1.0:
    return False
  if symbol in proven_winners and composite >= STOCKS_NEGATIVE_PF_MIN_COMPOSITE:
    return False
  return True


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
    },
  }
