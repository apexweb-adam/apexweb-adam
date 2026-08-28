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
from app.models.entities import Portfolio


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

GRADUATION_NUDGE_MIN_WR = 0.48
GRADUATION_NUDGE_MIN_WR_BY_BOT = {
  "crypto": 0.45,
  "commodities": 0.48,
}


def shadow_min_signal_boost(bot_type: str, *, bot_win_rate: float | None = None) -> float:
  base = SHADOW_MIN_SIGNAL_BOOST_BY_BOT.get(bot_type, SHADOW_MIN_SIGNAL_BOOST)
  if bot_win_rate is None:
    return base
  if in_shadow_graduation_nudge(bot_type, bot_win_rate):
    if bot_type == "commodities":
      return max(0.08, base - 0.05)
    if bot_type == "crypto":
      return max(0.08, base - 0.02)
  return base


def in_shadow_graduation_nudge(bot_type: str, bot_win_rate: float | None) -> bool:
  """Paused bot is close to per-bot graduation WR — ease shadow filters."""
  if bot_win_rate is None:
    return False
  from app.engines.profitability_gate import ProfitabilityGate

  floor = GRADUATION_NUDGE_MIN_WR_BY_BOT.get(bot_type, GRADUATION_NUDGE_MIN_WR)
  return (
    bot_type in ("commodities", "crypto")
    and floor <= bot_win_rate < ProfitabilityGate.GRADUATION_MIN_WIN_RATE
  )


SHADOW_INTEL_COMPOSITE_FLOOR = 0.50
SHADOW_INTEL_COMPOSITE_FLOOR_BY_BOT = {
  "crypto": 0.32,
}
SHADOW_INTEL_COMPOSITE_ONLY_BY_BOT = {
  "crypto": 0.40,
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


def shadow_intel_composite_override(
  bot_type: str,
  *,
  graduation_nudge: bool,
  shadow_mode: bool,
  composite: float,
  entry_min_signal: float,
  integration_boost: float,
) -> bool:
  """Allow shadow long when intel composite is strong despite technical sell/hold."""
  if not (graduation_nudge and shadow_mode and bot_type in ("commodities", "crypto")):
    return False
  composite_floor = SHADOW_INTEL_COMPOSITE_FLOOR_BY_BOT.get(
    bot_type, SHADOW_INTEL_COMPOSITE_FLOOR
  )
  composite_only_floor = SHADOW_INTEL_COMPOSITE_ONLY_BY_BOT.get(bot_type)
  if composite_only_floor is not None:
    if composite >= max(composite_only_floor, entry_min_signal + 0.12):
      return True
  boost_floor = SHADOW_INTEL_BOOST_FLOOR_BY_BOT.get(bot_type, SHADOW_INTEL_BOOST_FLOOR)
  composite_margin = 0.05 if bot_type == "crypto" else 0.15
  return (
    composite >= max(entry_min_signal + composite_margin, composite_floor)
    and integration_boost >= boost_floor
  )


def chronic_loser_blocks_shadow_entry(
  symbol: str,
  chronic_symbols: frozenset[str],
  *,
  graduation_nudge: bool,
  shadow_mode: bool,
  intel_override: bool,
) -> bool:
  """Chronic losers are skippable during graduation nudge when intel override applies."""
  if symbol not in chronic_symbols:
    return False
  if graduation_nudge and shadow_mode and intel_override:
    return False
  return True


def shadow_entry_min_signal(
  bot_type: str,
  strategy_min_signal: float,
  *,
  bot_win_rate: float | None = None,
) -> float:
  """Compute shadow entry threshold — eases when a paused bot is close to graduation WR."""
  from app.engines.profitability_gate import ProfitabilityGate
  from app.engines.strategy_migration import VERIFICATION_SIGNAL_CEILINGS

  ceiling = VERIFICATION_SIGNAL_CEILINGS.get(bot_type)
  base = min(strategy_min_signal, ceiling) if ceiling else strategy_min_signal
  if (
    bot_win_rate is not None
    and in_shadow_graduation_nudge(bot_type, bot_win_rate)
    and bot_type in ("commodities", "crypto")
  ):
    base = max(0.16, base - 0.06)
  boost = shadow_min_signal_boost(bot_type, bot_win_rate=bot_win_rate)
  return min(0.95, base + boost)


def shadow_requires_macd(
  bot_type: str,
  *,
  bot_win_rate: float | None,
  gate_tightening: GateEntryTightening,
  shadow_mode: bool,
) -> bool:
  if shadow_mode and bot_type in ("commodities", "crypto"):
    if bot_win_rate is not None and in_shadow_graduation_nudge(bot_type, bot_win_rate):
      return False
    if bot_type == "crypto":
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
RECENT_LARGE_LOSS_HOURS = 24
SHADOW_LARGE_LOSS_BYPASS_COMPOSITE = 0.55
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
  """Bots with enough closed trades and win rate below floor during verification."""
  blocked: set[str] = set()
  for bot_type in BOT_TYPES:
    portfolio = (
      await session.execute(select(Portfolio).where(Portfolio.bot_type == bot_type))
    ).scalar_one_or_none()
    if not portfolio or portfolio.total_trades < UNDERPERFORMER_MIN_TRADES:
      continue
    if portfolio.win_rate < UNDERPERFORMER_MAX_WIN_RATE:
      blocked.add(bot_type)
  return frozenset(blocked)


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
  min_loss_usd: float = RECENT_LARGE_LOSS_USD,
  recovery_win_ratio: float = 0.25,
) -> frozenset[str]:
  """Skip symbols with a recent large loss until a meaningful recovery win.

  A tiny win after a large loss (e.g. NVDA -$71 then +$0.21) must not clear the block.
  """
  from app.models.entities import Trade

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
      if is_winner is False and pnl is not None and pnl <= -min_loss_usd:
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
  patterns = (
    re.compile(r"Most losses on (\S+)"),
    re.compile(r"Gate skip recommended for (\S+)"),
  )
  for (patterns_found,) in result.all():
    if not patterns_found:
      continue
    for pattern in patterns:
      for match in pattern.finditer(patterns_found):
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
) -> bool:
  """DB-backed re-entry cooldown — survives deploy restarts."""
  from app.models.entities import Trade

  result = await session.execute(
    select(Trade.is_winner, Trade.executed_at)
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
    return False
  is_winner, executed_at = row
  if not executed_at or is_winner is None:
    return False
  if executed_at.tzinfo is not None:
    executed_at = executed_at.replace(tzinfo=None)
  elapsed = (datetime.utcnow() - executed_at).total_seconds()
  seconds = _bot_cooldown_seconds(bot_type, after_loss=is_winner is False)
  return elapsed < seconds


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
  recent_skip: frozenset[str],
  large_skip: frozenset[str],
  review_skip: frozenset[str],
  graduation_nudge: bool,
  shadow_mode: bool,
  intel_override: bool,
  composite: float,
  integration_boost: float,
) -> bool:
  """Hard gate-skip during shadow graduation nudge — review blocks are never bypassed."""
  if symbol in review_skip:
    return True
  if symbol in large_skip:
    if (
      graduation_nudge
      and shadow_mode
      and composite >= SHADOW_LARGE_LOSS_BYPASS_COMPOSITE
      and integration_boost >= SHADOW_LARGE_LOSS_BYPASS_INTEGRATION
    ):
      return False
    return True
  if symbol in recent_skip:
    if graduation_nudge and shadow_mode and intel_override:
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
  for bot_type in blocked:
    if bot_type == "stocks_futures":
      continue
    if await is_bot_paused(session, bot_type):
      continue
    await set_bot_paused(session, bot_type, True)
    paused_now.append(bot_type)
  return paused_now


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

  if total < 30 or win_rate >= ProfitabilityGate.MIN_WIN_RATE:
    return GateEntryTightening(
      active=False,
      win_rate=win_rate,
      min_sentiment=0.0,
      require_macd_bullish=False,
      min_composite_boost=0.0,
    )

  deficit = ProfitabilityGate.MIN_WIN_RATE - win_rate
  boost = min(0.08, deficit * 0.4)

  pm_cap = 1 if deficit >= 0.05 else (2 if deficit >= 0.02 else None)
  crypto_cap = 1 if deficit >= 0.05 else (2 if deficit >= 0.02 else None)
  commodities_cap = 2 if deficit >= 0.02 else None
  blocked = await get_underperforming_bots(session)
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
    return {
      "in_session": True,
      "mode": "entries",
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
