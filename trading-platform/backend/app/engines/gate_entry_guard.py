"""Tighten entry criteria when the verification gate win rate is below target."""

from __future__ import annotations

from dataclasses import dataclass

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
