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

UNDERPERFORMER_MIN_TRADES = 15
UNDERPERFORMER_MAX_WIN_RATE = 0.40
CHRONIC_LOSER_MIN_TRADES = 3
CHRONIC_LOSER_MAX_WIN_RATE = 0.35
RECENT_LOSER_DAYS = 7
RECENT_LOSER_MIN_LOSSES = 2
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


async def get_gate_skip_symbols(session: AsyncSession, bot_type: str) -> frozenset[str]:
  """Union of chronic, recent, and daily-review loser symbols during gate."""
  chronic = await get_chronic_loser_symbols(session, bot_type)
  recent = await get_recent_loser_symbols(session, bot_type)
  review = await get_review_blocked_symbols(session, bot_type)
  return chronic | recent | review


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


async def build_gate_ws_payload(session: AsyncSession) -> dict[str, Any]:
  """Gate tightening + profitability summary for WebSocket and status APIs."""
  gate_tightening = await get_gate_entry_tightening(session)
  profitability = await ProfitabilityGate(session).evaluate()

  chronic_loser_symbols: dict[str, list[str]] = {}
  recent_loser_symbols: dict[str, list[str]] = {}
  proven_winner_symbols: dict[str, list[str]] = {}
  if gate_tightening.active:
    for bot_type in BOT_TYPES:
      skip = await get_gate_skip_symbols(session, bot_type)
      chronic = await get_chronic_loser_symbols(session, bot_type)
      recent = await get_recent_loser_symbols(session, bot_type)
      if skip:
        chronic_loser_symbols[bot_type] = sorted(skip)
      if recent - chronic:
        recent_loser_symbols[bot_type] = sorted(recent - chronic)
      winners = await get_proven_winner_symbols(session, bot_type)
      if winners:
        proven_winner_symbols[bot_type] = sorted(winners)

  in_session = stocks_in_us_session()
  return {
    "profitability_gate": profitability,
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
      "stocks_futures": {
        "in_session": in_session,
        "mode": "entries" if in_session else "winddown_only",
      },
    },
  }
