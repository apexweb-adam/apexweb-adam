"""Boost/penalty from TradingView alerts and Polymarket prediction markets."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import IntelligenceItem

INTEGRATION_SOURCES = (
  "tradingview",
  "polymarket",
  "polymarket_account",
  "wallet_tracker",
  "hyperliquid",
  "dexscreener",
)
MAX_AGE_HOURS = 24


def _normalize_symbol(symbol: str) -> set[str]:
  if symbol.upper().startswith("PM:"):
    slug = symbol[3:].lower().replace("-", " ")
    parts = {w for w in slug.split() if len(w) > 3}
    return parts | {slug.replace(" ", ""), symbol.upper()}
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
    if item.source == "wallet_tracker":
      weight = 0.22 if item.sentiment > 0.4 else 0.16
    if item.source == "hyperliquid":
      weight = 0.16
    if item.source == "dexscreener":
      weight = 0.14
    fetched = item.fetched_at
    if fetched and fetched.tzinfo is not None:
      fetched = fetched.replace(tzinfo=None)
    age_hours = (datetime.utcnow() - fetched).total_seconds() / 3600 if fetched else MAX_AGE_HOURS
    freshness = max(0.25, 1.0 - age_hours / MAX_AGE_HOURS)
    boost += item.sentiment * weight * min(1.0, item.relevance_score) * freshness
    tag = item.source.replace("_", " ")
    reasons.append(f"{tag}:{item.sentiment:+.2f}")

  dex_bullish = any(i.source == "dexscreener" and i.sentiment > 0.1 for i in items)
  hl_bullish = any(i.source == "hyperliquid" and i.sentiment > 0.1 for i in items)
  if dex_bullish and hl_bullish:
    boost += 0.06
    reasons.append("memecoin_confluence:+0.06")

  boost = max(-0.25, min(0.25, boost))
  return boost, "; ".join(reasons[:3])


async def refresh_tradingview_signals(
  session: AsyncSession,
  symbols: list[str],
  *,
  action: str = "buy",
  max_age_hours: float = 12,
  reason_prefix: str = "Pre-session refresh",
  force_refresh: bool = False,
) -> list[str]:
  """Inject TradingView intel for symbols missing a recent alert (keeps TV boost fresh at open)."""
  if not symbols:
    return []

  refreshed: list[str] = []
  cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
  for symbol in symbols:
    if not force_refresh:
      result = await session.execute(
        select(IntelligenceItem)
        .where(
          IntelligenceItem.source == "tradingview",
          IntelligenceItem.fetched_at >= cutoff,
          IntelligenceItem.symbols_mentioned.ilike(f"%{symbol}%"),
        )
        .limit(1)
      )
      if result.scalar_one_or_none():
        continue

    action_lower = action.lower()
    sentiment = 0.5 if "buy" in action_lower else -0.5 if "sell" in action_lower else 0.0
    session.add(
      IntelligenceItem(
        source="tradingview",
        category="technical",
        title=f"TradingView: {action} {symbol}",
        content=f"{reason_prefix}: {action} {symbol}",
        sentiment=sentiment,
        relevance_score=0.9,
        symbols_mentioned=symbol,
      )
    )
    refreshed.append(symbol)

  if refreshed:
    await session.commit()
  return refreshed
