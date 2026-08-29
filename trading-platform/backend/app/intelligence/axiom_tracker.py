"""axiom.trade memecoin terminal intel — multi-wallet tracking, X/news alerts.

axiom.trade has no official public API; ingest via POST /api/webhooks/axiom (browser
bridge / Tampermonkey on axiom.trade) and optional session token for polling hooks.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.intelligence.fomo_tracker import normalize_fomo_symbol, trader_relevance, trader_sentiment
from app.intelligence.scanner import categorize
from app.models.entities import IntelligenceItem

AXIOM_SOURCE = "axiom"
AXIOM_ORIGIN = "https://axiom.trade"


def axiom_configured() -> bool:
  if not settings.axiom_enabled:
    return False
  if settings.axiom_session_token:
    return True
  return bool(settings.tradingview_webhook_secret)


def parse_axiom_wallet_addresses() -> list[str]:
  raw = [
    a.strip()
    for a in (
      settings.axiom_wallet_addresses
      + ","
      + settings.solana_tracker_addresses
    ).split(",")
    if a.strip() and not a.strip().startswith("0x")
  ]
  seen: set[str] = set()
  unique: list[str] = []
  for addr in raw:
    if addr not in seen:
      seen.add(addr)
      unique.append(addr)
  return unique


from app.intelligence.solana_wallet_tracker import tracked_solana_addresses, tracked_solana_wallet_count


def axiom_multi_wallet_ready() -> bool:
  """True when at least wallet_tracker_min_wallets Solana wallets are tracked."""
  return len(tracked_solana_addresses()) >= settings.wallet_tracker_min_wallets


def wallet_track_relevance(wallet_label: str | None, wallet_rank: int | None = None) -> float:
  base = 0.74
  if wallet_rank is not None and wallet_rank > 0:
    if wallet_rank <= 5:
      base = 0.96
    elif wallet_rank <= 20:
      base = 0.90
    elif wallet_rank <= 100:
      base = 0.82
  label = (wallet_label or "").lower()
  if any(k in label for k in ("smart", "whale", "kol", "insider", "alpha")):
    base = min(0.98, base + 0.04)
  return base


async def get_axiom_session_status(session: AsyncSession) -> dict[str, object]:
  from app.engines.platform_settings import get_axiom_session_token

  token = await get_axiom_session_token(session)
  poll_mode = axiom_poll_mode(token)
  if not token:
    return {
      "configured": False,
      "polling_active": poll_mode != "off",
      "poll_mode": poll_mode,
      "multi_wallet_ready": axiom_multi_wallet_ready(),
      "tracked_wallets": tracked_solana_wallet_count(),
      "min_wallets_required": settings.wallet_tracker_min_wallets,
    }
  return {
    "configured": True,
    "polling_active": poll_mode != "off",
    "poll_mode": poll_mode,
    "multi_wallet_ready": axiom_multi_wallet_ready(),
    "tracked_wallets": len(parse_axiom_wallet_addresses()),
    "min_wallets_required": settings.wallet_tracker_min_wallets,
  }


def axiom_poll_mode(session_token: str | None = None) -> str:
  if not settings.axiom_enabled:
    return "off"
  if session_token:
    return "session"
  if axiom_multi_wallet_ready() and settings.wallet_tracker_use_defaults:
    return "mirror"
  return "off"


async def ingest_axiom_webhook(session: AsyncSession, payload: dict) -> dict:
  """Accept axiom.trade wallet trades, alerts, and news into intel pipeline."""
  event_type = str(payload.get("event_type", payload.get("type", "trade"))).lower()
  symbol_raw = str(payload.get("symbol", payload.get("token", payload.get("ticker", "UNKNOWN"))))
  symbol = normalize_fomo_symbol(symbol_raw)
  action = str(payload.get("action", payload.get("side", event_type))).lower()
  wallet_address = str(payload.get("wallet_address", payload.get("address", payload.get("wallet", "")))).strip()
  wallet_label = str(payload.get("wallet_label", payload.get("wallet_name", payload.get("label", "")))).strip()
  wallet_rank = payload.get("wallet_rank", payload.get("rank"))
  chain = str(payload.get("chain", payload.get("network", "solana")))
  amount_usd = float(payload.get("amount_usd", payload.get("usd", 0)) or 0)
  token_address = str(payload.get("token_address", payload.get("mint", ""))).strip()
  message = str(payload.get("message", payload.get("content", ""))).strip()
  wallets_watching = payload.get("wallets_watching", payload.get("multi_wallet_count"))

  rank_int: int | None = None
  if wallet_rank is not None:
    try:
      rank_int = int(wallet_rank)
    except (TypeError, ValueError):
      rank_int = None

  sentiment = trader_sentiment(action, explicit=payload.get("sentiment"))
  relevance = float(payload.get("relevance", wallet_track_relevance(wallet_label or None, rank_int)))

  wallet_tag = wallet_label or (f"{wallet_address[:6]}…{wallet_address[-4:]}" if wallet_address else "axiom_wallet")
  title = payload.get("title") or f"[axiom] {wallet_tag} {action} {symbol_raw}"
  if amount_usd:
    title = f"{title} ${amount_usd:,.0f}"

  content_parts = [
    message or f"{wallet_tag} {action} {symbol_raw} on {chain}",
  ]
  if wallet_address:
    content_parts.append(f"wallet={wallet_address[:12]}…")
  if rank_int:
    content_parts.append(f"wallet_rank={rank_int}")
  if token_address:
    content_parts.append(f"token={token_address[:16]}…")
  if wallets_watching is not None:
    content_parts.append(f"multi_wallet_watch={wallets_watching}")
  content = " | ".join(p for p in content_parts if p)

  url = str(
    payload.get("url")
    or payload.get("alert_id")
    or f"axiom:{wallet_address or wallet_tag}:{symbol}:{action}:{datetime.utcnow().isoformat()}"
  )[:1000]

  existing = await session.execute(select(IntelligenceItem).where(IntelligenceItem.url == url))
  if existing.scalar_one_or_none():
    return {"status": "duplicate", "symbol": symbol, "source": AXIOM_SOURCE}

  full_text = f"{title} {content} {symbol}"
  session.add(
    IntelligenceItem(
      source=AXIOM_SOURCE,
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
    "source": AXIOM_SOURCE,
    "action": action,
    "wallet": wallet_tag,
    "relevance": relevance,
  }


async def get_axiom_hot_symbols(session: AsyncSession, *, max_age_hours: int = 48) -> list[str]:
  if not settings.axiom_hot_symbols_enabled:
    return []

  cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
  result = await session.execute(
    select(IntelligenceItem)
    .where(
      IntelligenceItem.source == AXIOM_SOURCE,
      IntelligenceItem.fetched_at >= cutoff,
      IntelligenceItem.sentiment > 0.2,
    )
    .order_by(IntelligenceItem.fetched_at.desc())
    .limit(30)
  )
  base = {s.strip().upper() for s in settings.crypto_symbols.split(",") if s.strip()}
  hot: list[str] = []
  seen: set[str] = set()
  for item in result.scalars().all():
    sym = normalize_fomo_symbol(item.symbols_mentioned or "")
    if sym in seen or sym in base:
      continue
    if item.relevance_score < settings.axiom_hot_symbol_min_relevance:
      continue
    seen.add(sym)
    hot.append(sym)
    if len(hot) >= settings.axiom_hot_symbols_max:
      break
  return hot


def normalize_axiom_feed_response(payload: object) -> list[dict]:
  if isinstance(payload, list):
    return [row for row in payload if isinstance(row, dict)]
  if isinstance(payload, dict):
    for key in ("trades", "items", "data", "results", "feed", "activity", "alerts"):
      rows = payload.get(key)
      if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
  return []


def feed_row_to_payload(row: dict) -> dict:
  wallet = row.get("wallet") if isinstance(row.get("wallet"), dict) else {}
  token = row.get("token") if isinstance(row.get("token"), dict) else {}
  symbol = row.get("symbol") or token.get("symbol") or token.get("ticker") or "UNKNOWN"
  action = str(row.get("side") or row.get("action") or row.get("type") or "buy").lower()
  wallet_address = str(wallet.get("address") or row.get("walletAddress") or row.get("address") or "")
  wallet_label = str(wallet.get("label") or wallet.get("name") or row.get("walletLabel") or "")
  amount_usd = row.get("amountUsd") or row.get("usd") or row.get("totalUsd") or 0
  alert_id = str(row.get("id") or row.get("alertId") or "")
  return {
    "event_type": "trade",
    "symbol": symbol,
    "action": action,
    "wallet_address": wallet_address,
    "wallet_label": wallet_label,
    "chain": "solana",
    "amount_usd": float(amount_usd or 0),
    "token_address": str(token.get("mint") or token.get("address") or row.get("mint") or ""),
    "url": f"axiom:feed:{alert_id}" if alert_id else None,
    "alert_id": alert_id or None,
  }


async def scan_axiom_wallet_mirror(session: AsyncSession) -> int:
  """Mirror recent Solana whale wallet intel into axiom feed when session poll is unavailable."""
  if not settings.axiom_enabled or not axiom_multi_wallet_ready():
    return 0

  from app.engines.platform_settings import get_axiom_session_token

  if await get_axiom_session_token(session):
    return 0

  cutoff = datetime.utcnow() - timedelta(hours=3)
  result = await session.execute(
    select(IntelligenceItem)
    .where(
      IntelligenceItem.source == "wallet_tracker",
      IntelligenceItem.fetched_at >= cutoff,
      IntelligenceItem.category == "crypto",
    )
    .order_by(IntelligenceItem.fetched_at.desc())
    .limit(25)
  )

  wallet_count = tracked_solana_wallet_count()
  ingested = 0
  for item in result.scalars().all():
    haystack = f"{item.title} {item.content}".upper()
    if "SOL WHALE" not in haystack and "SOLANA" not in haystack:
      continue
    symbol_raw = (item.symbols_mentioned or "SOL").split(",")[0].replace("USDT", "")
    action = "buy" if (item.sentiment or 0) > 0.15 else "sell" if (item.sentiment or 0) < -0.1 else "watch"
    mirror_url = f"axiom:mirror:{item.url}"[:1000]
    mirror_result = await ingest_axiom_webhook(
      session,
      {
        "event_type": "trade",
        "symbol": symbol_raw,
        "action": action,
        "message": f"Multi-wallet mirror from Solana whale tracker | {item.title[:120]}",
        "url": mirror_url,
        "wallets_watching": wallet_count,
        "relevance": min(0.94, float(item.relevance_score or 0.72) + 0.04),
        "sentiment": item.sentiment,
      },
    )
    if mirror_result.get("status") == "received":
      ingested += 1

  phantom_cutoff = datetime.utcnow() - timedelta(hours=6)
  phantom_result = await session.execute(
    select(IntelligenceItem)
    .where(
      IntelligenceItem.source == "phantom",
      IntelligenceItem.fetched_at >= phantom_cutoff,
    )
    .order_by(IntelligenceItem.fetched_at.desc())
    .limit(20)
  )
  for item in phantom_result.scalars().all():
    if "holding" not in f"{item.title} {item.content}".lower():
      continue
    symbol_raw = (item.symbols_mentioned or "SOL").split(",")[0].replace("USDT", "")
    mirror_url = f"axiom:phantom-mirror:{item.url}"[:1000]
    mirror_result = await ingest_axiom_webhook(
      session,
      {
        "event_type": "holdings",
        "symbol": symbol_raw,
        "action": "watch",
        "message": f"Phantom portfolio mirror | {item.title[:120]}",
        "url": mirror_url,
        "wallets_watching": wallet_count,
        "relevance": min(0.9, float(item.relevance_score or 0.74) + 0.03),
        "sentiment": item.sentiment or 0.15,
      },
    )
    if mirror_result.get("status") == "received":
      ingested += 1
  return ingested


async def scan_axiom_feed(session: AsyncSession) -> int:
  """Poll axiom session feed when configured; otherwise mirror Solana whale wallet intel."""
  if not settings.axiom_enabled:
    return 0

  ingested = await _scan_axiom_session_feed(session)
  if ingested == 0:
    ingested += await scan_axiom_wallet_mirror(session)
  return ingested


async def _scan_axiom_session_feed(session: AsyncSession) -> int:
  """Best-effort axiom.trade session polling when a token is stored."""
  from app.engines.platform_settings import get_axiom_session_token

  token = await get_axiom_session_token(session)
  if not token:
    return 0

  headers = {
    "Accept": "application/json",
    "Authorization": f"Bearer {token}",
    "Origin": AXIOM_ORIGIN,
    "Referer": f"{AXIOM_ORIGIN}/",
    "User-Agent": "ApexTradingPlatform/1.0",
  }
  endpoints = [
    f"{AXIOM_ORIGIN}/api/feed?limit={settings.axiom_poll_limit}",
    f"{AXIOM_ORIGIN}/api/trades?limit={settings.axiom_poll_limit}",
  ]

  ingested = 0
  async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
    for url in endpoints:
      try:
        response = await client.get(url, headers=headers)
        if response.status_code in (401, 403, 404):
          continue
        response.raise_for_status()
        payload = response.json()
      except (httpx.HTTPError, json.JSONDecodeError) as exc:
        print(f"[axiom] poll skip {url}: {exc}")
        continue

      for row in normalize_axiom_feed_response(payload):
        result = await ingest_axiom_webhook(session, feed_row_to_payload(row))
        if result.get("status") == "received":
          ingested += 1
      if ingested:
        break
  return ingested
