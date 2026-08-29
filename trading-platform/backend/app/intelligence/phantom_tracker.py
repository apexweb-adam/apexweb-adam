"""Phantom wallet intel — portfolio snapshots and watchlist alerts via webhook bridge.

The Phantom MCP in Cursor is documentation-only; live wallet data flows through
POST /api/webhooks/phantom (userscript / Phantom Connect forwarding).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.intelligence.fomo_tracker import normalize_fomo_symbol, trader_sentiment
from app.intelligence.scanner import categorize
from app.models.entities import IntelligenceItem

PHANTOM_SOURCE = "phantom"


def phantom_configured() -> bool:
  if not settings.phantom_enabled:
    return False
  if parse_phantom_wallet_addresses():
    return True
  return bool(settings.tradingview_webhook_secret)


def parse_phantom_wallet_addresses() -> list[str]:
  raw = [
    a.strip()
    for a in settings.phantom_wallet_addresses.split(",")
    if a.strip()
  ]
  seen: set[str] = set()
  unique: list[str] = []
  for addr in raw:
    if addr not in seen:
      seen.add(addr)
      unique.append(addr)
  return unique


async def ingest_phantom_webhook(session: AsyncSession, payload: dict) -> dict:
  """Accept Phantom portfolio / balance / watchlist events."""
  event_type = str(payload.get("event_type", payload.get("type", "balance"))).lower()
  symbol_raw = str(payload.get("symbol", payload.get("token", payload.get("ticker", "")))).strip()
  symbol = normalize_fomo_symbol(symbol_raw) if symbol_raw else "SOLUSDT"
  wallet_address = str(payload.get("wallet_address", payload.get("address", payload.get("wallet", "")))).strip()
  chain = str(payload.get("chain", payload.get("network", "solana")))
  action = str(payload.get("action", event_type)).lower()
  balance_usd = float(payload.get("balance_usd", payload.get("portfolio_usd", payload.get("usd", 0))) or 0)
  message = str(payload.get("message", payload.get("content", ""))).strip()

  if event_type in ("portfolio", "snapshot", "holdings"):
    sentiment = 0.15
    relevance = 0.7
  elif action in ("buy", "swap_in", "receive", "accumulate"):
    sentiment = trader_sentiment("buy", explicit=payload.get("sentiment"))
    relevance = 0.82
  elif action in ("sell", "swap_out", "send", "dump"):
    sentiment = trader_sentiment("sell", explicit=payload.get("sentiment"))
    relevance = 0.8
  else:
    sentiment = float(payload.get("sentiment", 0.0))
    relevance = float(payload.get("relevance", 0.75))

  wallet_tag = (
    f"{wallet_address[:6]}…{wallet_address[-4:]}" if len(wallet_address) > 12 else wallet_address or "phantom"
  )
  title = payload.get("title") or f"[phantom] {event_type} {symbol_raw or chain}"
  if balance_usd:
    title = f"{title} ${balance_usd:,.0f}"

  content = message or payload.get(
    "content",
    f"Phantom {event_type} on {chain}"
    + (f" | {symbol_raw}" if symbol_raw else "")
    + (f" | wallet {wallet_tag}" if wallet_address else ""),
  )
  url = str(
    payload.get("url")
    or payload.get("tx_hash")
    or f"phantom:{wallet_address or 'wallet'}:{event_type}:{datetime.utcnow().isoformat()}"
  )[:1000]

  existing = await session.execute(select(IntelligenceItem).where(IntelligenceItem.url == url))
  if existing.scalar_one_or_none():
    return {"status": "duplicate", "symbol": symbol, "source": PHANTOM_SOURCE}

  full_text = f"{title} {content} {symbol}"
  session.add(
    IntelligenceItem(
      source=PHANTOM_SOURCE,
      category=payload.get("category") or categorize(full_text) or "crypto",
      title=str(title)[:500],
      content=str(content)[:2000],
      url=url,
      sentiment=sentiment,
      relevance_score=relevance,
      symbols_mentioned=payload.get("symbols_mentioned") or symbol,
    )
  )
  await session.commit()
  return {
    "status": "received",
    "symbol": symbol,
    "source": PHANTOM_SOURCE,
    "event_type": event_type,
    "wallet": wallet_tag,
  }


async def get_phantom_watch_symbols(session: AsyncSession, *, max_age_hours: int = 72) -> list[str]:
  if not settings.phantom_enabled:
    return []

  cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
  result = await session.execute(
    select(IntelligenceItem)
    .where(
      IntelligenceItem.source == PHANTOM_SOURCE,
      IntelligenceItem.fetched_at >= cutoff,
    )
    .order_by(IntelligenceItem.fetched_at.desc())
    .limit(25)
  )
  symbols: list[str] = []
  seen: set[str] = set()
  for item in result.scalars().all():
    sym = normalize_fomo_symbol(item.symbols_mentioned or "")
    if sym in seen:
      continue
    seen.add(sym)
    symbols.append(sym)
    if len(symbols) >= 8:
      break
  return symbols
