"""Per-bot, per-source intelligence scoring — routes TikTok/political/X/YouTube to the right bots."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import IntelligenceItem

# Source weights by bot type (1.0 = baseline). Higher = more influence on composite sentiment.
BOT_SOURCE_WEIGHTS: dict[str, dict[str, float]] = {
  "crypto": {
    "x": 1.25,
    "tiktok": 1.35,
    "reddit": 1.05,
    "youtube": 0.85,
    "news": 0.9,
    "newsapi": 0.85,
    "political": 0.45,
    "polymarket": 0.55,
    "tradingview": 1.1,
    "polymarket_account": 0.5,
  },
  "stocks_futures": {
    "news": 1.25,
    "newsapi": 1.15,
    "youtube": 1.0,
    "x": 0.95,
    "reddit": 0.9,
    "political": 1.15,
    "tiktok": 0.35,
    "polymarket": 0.5,
    "tradingview": 1.2,
    "polymarket_account": 0.4,
  },
  "commodities": {
    "political": 1.45,
    "news": 1.2,
    "newsapi": 1.05,
    "youtube": 0.95,
    "x": 0.75,
    "reddit": 0.7,
    "tiktok": 0.3,
    "polymarket": 0.65,
    "tradingview": 1.0,
    "polymarket_account": 0.35,
  },
  "polymarket": {
    "polymarket": 1.5,
    "polymarket_account": 1.35,
    "political": 1.25,
    "x": 0.85,
    "news": 0.9,
    "newsapi": 0.85,
    "reddit": 0.75,
    "youtube": 0.6,
    "tiktok": 0.4,
    "tradingview": 0.9,
  },
}

DEFAULT_WEIGHT = 0.6
MAX_ITEMS = 25
MAX_AGE_HOURS = 48


def _symbol_aliases(symbol: str) -> set[str]:
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
  if clean in ("OIL", "CL", "CRUDE"):
    aliases.update({"OIL", "CL", "CRUDE", "CL=F", "WTI"})
  return aliases


def _matches_symbol(item: IntelligenceItem, aliases: set[str]) -> bool:
  mentioned = (item.symbols_mentioned or "").upper()
  haystack = f"{item.title} {item.content} {mentioned}".upper()
  return any(alias in haystack for alias in aliases)


def _source_weight(bot_type: str, source: str) -> float:
  return BOT_SOURCE_WEIGHTS.get(bot_type, {}).get(source, DEFAULT_WEIGHT)


async def compute_bot_sentiment(
  session: AsyncSession,
  bot_type: str,
  symbol: str,
) -> tuple[float, str]:
  """
  Weighted sentiment for a bot/symbol using per-source routing.
  Returns (score in [-1, 1], human-readable breakdown).
  """
  aliases = _symbol_aliases(symbol)
  cutoff = datetime.utcnow() - timedelta(hours=MAX_AGE_HOURS)

  result = await session.execute(
    select(IntelligenceItem)
    .where(IntelligenceItem.fetched_at >= cutoff)
    .order_by(IntelligenceItem.fetched_at.desc())
    .limit(80)
  )
  all_items = list(result.scalars().all())

  symbol_items = [i for i in all_items if _matches_symbol(i, aliases)]
  items = symbol_items[:MAX_ITEMS] if symbol_items else all_items[:MAX_ITEMS]

  if not items:
    return 0.0, ""

  weighted_sum = 0.0
  weight_total = 0.0
  breakdown: list[str] = []

  for item in items:
    src_weight = _source_weight(bot_type, item.source)
    relevance = max(0.1, min(1.0, item.relevance_score or 0.5))
    w = src_weight * relevance
    weighted_sum += item.sentiment * w
    weight_total += w
    if abs(item.sentiment) > 0.15 and len(breakdown) < 4:
      breakdown.append(f"{item.source}:{item.sentiment:+.2f}")

  if weight_total <= 0:
    return 0.0, ""

  score = max(-1.0, min(1.0, weighted_sum / weight_total))
  reason = ", ".join(breakdown)
  return score, reason
