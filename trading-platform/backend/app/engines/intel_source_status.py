"""Shared intelligence source health for REST and WebSocket APIs."""

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.entities import IntelligenceItem

INTEL_SOURCE_ORDER = [
  "news",
  "reddit",
  "youtube",
  "x",
  "tiktok",
  "polymarket",
  "polymarket_account",
  "political",
  "tradingview",
  "newsapi",
]


def _source_status(
  source: str,
  *,
  source_counts: dict[str, int],
  configured: dict[str, bool],
) -> str:
  has_items = source_counts.get(source, 0) > 0
  is_configured = configured.get(source, has_items)
  if source == "tradingview" and is_configured:
    return "active"
  if source == "x" and is_configured:
    if settings.newsapi_key and not settings.twitter_bearer_token:
      return "degraded"
    if not has_items:
      return "degraded"
    return "active"
  if source == "tiktok" and (is_configured or has_items):
    return "degraded"
  if is_configured or has_items:
    return "active"
  return "pending"


async def build_intel_sources(session: AsyncSession) -> list[dict[str, Any]]:
  result = await session.execute(select(IntelligenceItem.source, IntelligenceItem.fetched_at))
  rows = result.all()
  source_counts: dict[str, int] = {}
  source_latest: dict[str, datetime] = {}
  for source, fetched_at in rows:
    source_counts[source] = source_counts.get(source, 0) + 1
    if source not in source_latest or (fetched_at and fetched_at > source_latest[source]):
      source_latest[source] = fetched_at

  configured = {
    "news": True,
    "reddit": True,
    "youtube": True,
    "polymarket": True,
    "polymarket_account": bool(
      settings.polymarket_wallet_address or settings.polymarket_deposit_address
    ),
    "political": True,
    "tiktok": True,
    "tradingview": bool(settings.tradingview_webhook_secret),
    "x": bool(settings.twitter_bearer_token) or bool(settings.newsapi_key),
    "newsapi": bool(settings.newsapi_key),
  }

  return [
    {
      "source": source,
      "status": _source_status(source, source_counts=source_counts, configured=configured),
      "items_collected": source_counts.get(source, 0),
      "last_fetched": source_latest.get(source).isoformat() if source in source_latest else None,
    }
    for source in INTEL_SOURCE_ORDER
  ]


def serialize_strategy_config(config) -> dict[str, Any]:
  return {
    "bot_type": config.bot_type,
    "rsi_oversold": config.rsi_oversold,
    "rsi_overbought": config.rsi_overbought,
    "min_signal_score": config.min_signal_score,
    "min_sentiment_score": config.min_sentiment_score,
    "stop_loss_pct": config.stop_loss_pct,
    "take_profit_pct": config.take_profit_pct,
    "max_position_pct": config.max_position_pct,
    "momentum_weight": config.momentum_weight,
    "sentiment_weight": config.sentiment_weight,
    "technical_weight": config.technical_weight,
    "version": config.version,
    "updated_at": config.updated_at.isoformat() if config.updated_at else None,
  }


def serialize_intel_item(item: IntelligenceItem) -> dict[str, Any]:
  return {
    "id": item.id,
    "source": item.source,
    "category": item.category,
    "title": item.title,
    "content": item.content,
    "url": item.url,
    "sentiment": item.sentiment,
    "relevance_score": item.relevance_score,
    "symbols_mentioned": item.symbols_mentioned,
    "fetched_at": item.fetched_at.isoformat() if item.fetched_at else None,
  }
