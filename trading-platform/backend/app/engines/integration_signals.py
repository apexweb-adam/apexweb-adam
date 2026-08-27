"""Boost/penalty from TradingView alerts and Polymarket prediction markets."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import IntelligenceItem

INTEGRATION_SOURCES = ("tradingview", "polymarket", "polymarket_account")
MAX_AGE_HOURS = 24


def _normalize_symbol(symbol: str) -> set[str]:
  clean = symbol.upper().replace("=F", "").replace("=X", "").replace("USDT", "")
  aliases = {clean, symbol.upper()}
  if clean in ("BTC", "BITCOIN"):
    aliases.update({"BTC", "BITCOIN", "BTCUSDT"})
  if clean in ("ETH", "ETHEREUM"):
    aliases.update({"ETH", "ETHEREUM", "ETHUSDT"})
  if clean in ("GOLD", "GC", "XAU"):
    aliases.update({"GOLD", "GC", "XAU", "GC=F", "XAUUSDT", "PAXGUSDT"})
  if clean in ("TSLA", "TESLA"):
    aliases.update({"TSLA", "TESLA"})
  return aliases


def _matches_symbol(item: IntelligenceItem, aliases: set[str]) -> bool:
  mentioned = (item.symbols_mentioned or "").upper()
  haystack = f"{item.title} {item.content} {mentioned}".upper()
  return any(alias in haystack for alias in aliases)


async def get_integration_boost(session: AsyncSession, symbol: str) -> tuple[float, str]:
  """
  Returns (score_adjustment, reason) from recent TV/Polymarket intel.
  Adjustment range roughly -0.25 .. +0.25 applied to composite score.
  """
  aliases = _normalize_symbol(symbol)
  cutoff = datetime.utcnow() - timedelta(hours=MAX_AGE_HOURS)

  result = await session.execute(
    select(IntelligenceItem)
    .where(
      IntelligenceItem.source.in_(INTEGRATION_SOURCES),
      IntelligenceItem.fetched_at >= cutoff,
    )
    .order_by(IntelligenceItem.fetched_at.desc())
    .limit(50)
  )
  items = [i for i in result.scalars().all() if _matches_symbol(i, aliases)]
  if not items:
    return 0.0, ""

  boost = 0.0
  reasons: list[str] = []
  for item in items[:5]:
    weight = 0.15 if item.source == "tradingview" else 0.10
    if item.source == "polymarket_account":
      weight = 0.12
    boost += item.sentiment * weight * min(1.0, item.relevance_score)
    tag = item.source.replace("_", " ")
    reasons.append(f"{tag}:{item.sentiment:+.2f}")

  boost = max(-0.25, min(0.25, boost))
  return boost, "; ".join(reasons[:3])
