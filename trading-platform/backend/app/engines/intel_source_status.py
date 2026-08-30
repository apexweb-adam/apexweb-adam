"""Shared intelligence source health for REST and WebSocket APIs."""

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.intelligence.axiom_tracker import axiom_configured, get_axiom_session_status
from app.intelligence.fomo_tracker import fomo_configured, get_fomo_bearer_status
from app.intelligence.phantom_tracker import (
  phantom_configured,
  phantom_poll_wallet_addresses,
  phantom_portfolio_poll_active,
  phantom_portfolio_poll_mode,
)
from app.intelligence.solana_wallet_tracker import tracked_solana_wallet_count
from app.intelligence.wallet_tracker import wallet_tracker_configured
from app.models.entities import IntelligenceItem

INTEL_SOURCE_ORDER = [
  "news",
  "reddit",
  "youtube",
  "x",
  "tiktok",
  "dexscreener",
  "hyperliquid",
  "fomo",
  "axiom",
  "phantom",
  "polymarket",
  "polymarket_account",
  "wallet_tracker",
  "political",
  "tradingview",
  "newsapi",
]


def _source_status(
  source: str,
  *,
  source_counts: dict[str, int],
  source_latest: dict[str, datetime],
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
    latest = source_latest.get(source)
    if latest and has_items:
      now = datetime.now(timezone.utc)
      latest_utc = latest if latest.tzinfo else latest.replace(tzinfo=timezone.utc)
      if latest_utc.tzinfo != timezone.utc:
        latest_utc = latest_utc.astimezone(timezone.utc)
      age = now - latest_utc
      if age <= timedelta(hours=12):
        return "active"
    return "degraded"
  if source == "reddit" and has_items and not configured.get("reddit_oauth"):
    latest = source_latest.get(source)
    if latest is not None:
      now = datetime.now(timezone.utc)
      latest_utc = latest if latest.tzinfo else latest.replace(tzinfo=timezone.utc)
      if latest_utc.tzinfo != timezone.utc:
        latest_utc = latest_utc.astimezone(timezone.utc)
      if now - latest_utc <= timedelta(hours=24):
        return "active"
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

  reddit_oauth = bool(settings.reddit_client_id and settings.reddit_client_secret)
  configured = {
    "news": True,
    "reddit": reddit_oauth or source_counts.get("reddit", 0) > 0,
    "reddit_oauth": reddit_oauth,
    "youtube": True,
    "polymarket": True,
    "polymarket_account": bool(
      settings.polymarket_wallet_address or settings.polymarket_deposit_address
    ),
    "wallet_tracker": wallet_tracker_configured()
    or bool(settings.tradingview_webhook_secret),
    "political": True,
    "tiktok": True,
    "dexscreener": True,
    "hyperliquid": settings.hyperliquid_enabled,
    "fomo": fomo_configured(),
    "axiom": axiom_configured(),
    "phantom": phantom_configured() or phantom_portfolio_poll_active(),
    "tradingview": bool(settings.tradingview_webhook_secret),
    "x": bool(settings.twitter_bearer_token) or bool(settings.newsapi_key),
    "newsapi": bool(settings.newsapi_key),
  }

  fomo_bearer = await get_fomo_bearer_status(session)
  axiom_session = await get_axiom_session_status(session)

  rows: list[dict[str, Any]] = []
  for source in INTEL_SOURCE_ORDER:
    status = _source_status(
      source,
      source_counts=source_counts,
      source_latest=source_latest,
      configured=configured,
    )
    if source == "fomo" and fomo_bearer.get("configured") and not fomo_bearer.get("polling_active"):
      latest = source_latest.get("fomo")
      recent_webhook = False
      if latest is not None:
        latest_naive = latest.replace(tzinfo=None) if latest.tzinfo else latest
        recent_webhook = (datetime.utcnow() - latest_naive).total_seconds() < 6 * 3600
      if not recent_webhook:
        status = "degraded"
    if source == "axiom" and axiom_session.get("configured") and axiom_session.get("poll_mode") == "session" and not axiom_session.get("polling_active"):
      status = "degraded"
    if source == "axiom" and axiom_session.get("poll_mode") == "off":
      status = "degraded"
    if source == "axiom" and not axiom_session.get("multi_wallet_ready"):
      status = "degraded"
    if source == "phantom" and settings.phantom_portfolio_poll_enabled and not phantom_portfolio_poll_active():
      status = "degraded"
    row: dict[str, Any] = {
      "source": source,
      "status": status,
      "items_collected": source_counts.get(source, 0),
      "last_fetched": source_latest.get(source).isoformat() if source in source_latest else None,
    }
    if source == "reddit":
      row["oauth_configured"] = reddit_oauth
      if not reddit_oauth and source_counts.get("reddit", 0) > 0:
        row["collection_mode"] = "rss"
    if source == "fomo" and fomo_bearer.get("configured"):
      row["bearer_expires_at"] = fomo_bearer.get("expires_at")
      row["bearer_minutes_remaining"] = fomo_bearer.get("minutes_remaining")
      row["bearer_polling_active"] = fomo_bearer.get("polling_active")
      row["webhook_fallback_active"] = bool(
        fomo_bearer.get("configured") and not fomo_bearer.get("polling_active")
      )
      latest = source_latest.get("fomo")
      if latest is not None:
        latest_naive = latest.replace(tzinfo=None) if latest.tzinfo else latest
        row["webhook_recent"] = (datetime.utcnow() - latest_naive).total_seconds() < 6 * 3600
    if source == "axiom":
      row["session_configured"] = axiom_session.get("configured")
      row["session_polling_active"] = axiom_session.get("polling_active")
      row["poll_mode"] = axiom_session.get("poll_mode")
      row["multi_wallet_ready"] = axiom_session.get("multi_wallet_ready")
      row["tracked_wallets"] = axiom_session.get("tracked_wallets", tracked_solana_wallet_count())
      row["min_wallets_required"] = settings.wallet_tracker_min_wallets
    if source == "phantom":
      row["portfolio_poll_active"] = phantom_portfolio_poll_active()
      row["portfolio_poll_mode"] = phantom_portfolio_poll_mode()
      row["tracked_wallets"] = len(phantom_poll_wallet_addresses())
      row["using_default_wallets"] = not bool(settings.phantom_wallet_addresses.strip())
    rows.append(row)
  return rows


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
