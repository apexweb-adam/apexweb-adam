"""fomo.family social copy-trading intel — leaderboard traders, alerts, and feed events.

fomo.family has no public API; ingest via POST /api/webhooks/fomo (browser bridge,
Zapier, or manual forwarding from alerts). See platform status for payload schema.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.intelligence.scanner import categorize
from app.models.entities import IntelligenceItem

FOMO_SOURCE = "fomo"
FOMO_API_BASE = "https://prod-api.fomo.family"
FOMO_SUPPORTED_CHAINS = "56,143,4663,8453,1399811149"
NETWORK_ID_TO_CHAIN = {
  1399811149: "solana",
  8453: "base",
  56: "bnb",
  143: "monad",
  4663: "robinhood",
  1: "ethereum",
}
KNOWN_MEME_ALIASES: dict[str, str] = {
  "DOGE": "DOGEUSDT",
  "DOGECOIN": "DOGEUSDT",
  "PEPE": "PEPEUSDT",
  "SHIB": "SHIBUSDT",
  "SHIBA": "SHIBUSDT",
  "WIF": "WIFUSDT",
  "DOGWIFHAT": "WIFUSDT",
  "BONK": "BONKUSDT",
  "FLOKI": "FLOKIUSDT",
  "TRUMP": "TRUMPUSDT",
  "MEME": "MEMEUSDT",
  "NEIRO": "NEIROUSDT",
  "PNUT": "PNUTUSDT",
  "PEOPLE": "PEOPLEUSDT",
  "1000SATS": "1000SATSUSDT",
  "SOL": "SOLUSDT",
  "ETH": "ETHUSDT",
  "BTC": "BTCUSDT",
}


def fomo_configured() -> bool:
  if settings.fomo_bearer_token:
    return settings.fomo_enabled
  return bool(settings.fomo_enabled and settings.tradingview_webhook_secret)


def decode_bearer_expiry(bearer: str) -> dict[str, object] | None:
  """Decode Privy/JWT exp claim without verifying signature (expiry hint only)."""
  token = (bearer or "").strip()
  if token.count(".") < 2:
    return None
  payload_b64 = token.split(".")[1]
  padding = "=" * (-len(payload_b64) % 4)
  try:
    payload = json.loads(base64.urlsafe_b64decode(payload_b64 + padding))
  except (json.JSONDecodeError, ValueError, TypeError):
    return None
  exp = payload.get("exp")
  if not isinstance(exp, (int, float)):
    return None
  expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
  minutes_remaining = int((expires_at - datetime.now(timezone.utc)).total_seconds() // 60)
  return {
    "expires_at": expires_at.isoformat(),
    "minutes_remaining": minutes_remaining,
    "expired": minutes_remaining <= 0,
  }


async def get_fomo_bearer_status(session: AsyncSession) -> dict[str, object]:
  """Whether server-side fomo polling is configured and when the bearer expires."""
  from app.engines.platform_settings import get_fomo_bearer_token

  bearer = await get_fomo_bearer_token(session)
  if not bearer:
    return {
      "configured": False,
      "polling_active": False,
    }
  expiry = decode_bearer_expiry(bearer)
  expired = bool(expiry and expiry.get("expired"))
  status: dict[str, object] = {
    "configured": True,
    "polling_active": not expired,
  }
  if expiry:
    status.update(expiry)
  return status


def normalize_fomo_symbol(symbol: str) -> str:
  """Map fomo token tickers to Binance-style symbols the crypto bot can trade."""
  raw = (symbol or "").strip().upper().replace("$", "")
  if not raw:
    return "BTCUSDT"
  if raw.endswith("USDT"):
    return raw
  if raw in KNOWN_MEME_ALIASES:
    return KNOWN_MEME_ALIASES[raw]
  if raw.isalnum() and len(raw) <= 12:
    return f"{raw}USDT"
  return raw[:20]


def trader_relevance(rank: int | None, pnl_pct: float | None = None) -> float:
  """Higher relevance for top leaderboard traders."""
  base = 0.72
  if rank is not None and rank > 0:
    if rank <= 10:
      base = 0.95
    elif rank <= 50:
      base = 0.88
    elif rank <= 200:
      base = 0.80
    else:
      base = 0.72
  if pnl_pct is not None and pnl_pct > 100:
    base = min(0.98, base + 0.04)
  elif pnl_pct is not None and pnl_pct > 50:
    base = min(0.95, base + 0.02)
  return base


def trader_sentiment(action: str, *, explicit: float | None = None) -> float:
  if explicit is not None:
    return max(-1.0, min(1.0, explicit))
  act = (action or "").lower()
  if act in ("buy", "long", "open", "enter", "accumulate", "ape"):
    return 0.62
  if act in ("sell", "short", "close", "exit", "dump", "take_profit"):
    return -0.58
  if act in ("alert", "watch", "follow"):
    return 0.35
  return 0.0


async def ingest_fomo_webhook(session: AsyncSession, payload: dict) -> dict:
  """Accept fomo.family trader alerts / copy-trade signals into intel pipeline."""
  event_type = str(payload.get("event_type", payload.get("type", "trade"))).lower()
  symbol_raw = str(payload.get("symbol", payload.get("token", payload.get("ticker", "UNKNOWN"))))
  symbol = normalize_fomo_symbol(symbol_raw)
  action = str(payload.get("action", payload.get("side", event_type))).lower()
  trader_id = str(payload.get("trader_id", payload.get("user_id", ""))).strip()
  trader_name = str(payload.get("trader_name", payload.get("username", trader_id or "fomo_trader")))
  trader_rank = payload.get("trader_rank", payload.get("rank"))
  trader_pnl = payload.get("trader_pnl_pct", payload.get("pnl_pct"))
  chain = str(payload.get("chain", payload.get("network", "multichain")))
  amount_usd = float(payload.get("amount_usd", payload.get("usd", 0)) or 0)
  token_address = str(payload.get("token_address", payload.get("mint", ""))).strip()
  message = str(payload.get("message", payload.get("content", ""))).strip()

  rank_int: int | None = None
  if trader_rank is not None:
    try:
      rank_int = int(trader_rank)
    except (TypeError, ValueError):
      rank_int = None

  pnl_float: float | None = None
  if trader_pnl is not None:
    try:
      pnl_float = float(trader_pnl)
    except (TypeError, ValueError):
      pnl_float = None

  sentiment = trader_sentiment(
    action,
    explicit=payload.get("sentiment"),
  )
  relevance = float(payload.get("relevance", trader_relevance(rank_int, pnl_float)))

  rank_label = f"#{rank_int}" if rank_int else "trader"
  title = payload.get("title") or f"[fomo] {trader_name} ({rank_label}) {action} {symbol_raw}"
  if amount_usd:
    title = f"{title} ${amount_usd:,.0f}"

  content_parts = [
    message or f"{trader_name} {action} {symbol_raw} on {chain}",
  ]
  if trader_id:
    content_parts.append(f"trader_id={trader_id}")
  if rank_int:
    content_parts.append(f"rank={rank_int}")
  if pnl_float is not None:
    content_parts.append(f"pnl_pct={pnl_float:.1f}")
  if token_address:
    content_parts.append(f"token={token_address[:16]}…")
  content = " | ".join(p for p in content_parts if p)

  url = str(
    payload.get("url")
    or payload.get("alert_id")
    or f"fomo:{trader_id or trader_name}:{symbol}:{action}:{datetime.utcnow().isoformat()}"
  )[:1000]

  existing = await session.execute(
    select(IntelligenceItem).where(IntelligenceItem.url == url)
  )
  if existing.scalar_one_or_none():
    return {"status": "duplicate", "symbol": symbol, "source": FOMO_SOURCE}

  full_text = f"{title} {content} {symbol}"
  session.add(
    IntelligenceItem(
      source=FOMO_SOURCE,
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
    "source": FOMO_SOURCE,
    "action": action,
    "trader": trader_name,
    "trader_rank": rank_int,
    "relevance": relevance,
  }


async def get_fomo_hot_symbols(session: AsyncSession, *, max_age_hours: int = 48) -> list[str]:
  """Symbols with recent bullish fomo leaderboard / alert intel (for crypto scan expansion)."""
  if not settings.fomo_hot_symbols_enabled:
    return []

  cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
  result = await session.execute(
    select(IntelligenceItem)
    .where(
      IntelligenceItem.source == FOMO_SOURCE,
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
    if item.relevance_score < settings.fomo_hot_symbol_min_relevance:
      continue
    seen.add(sym)
    hot.append(sym)
    if len(hot) >= settings.fomo_hot_symbols_max:
      break
  return hot


def _network_chain(network_id: int | None) -> str:
  if network_id is None:
    return "multichain"
  return NETWORK_ID_TO_CHAIN.get(int(network_id), f"chain_{network_id}")


def trade_row_to_payload(trade: dict) -> dict:
  """Map prod-api.fomo.family trade JSON to webhook ingest payload."""
  token = trade.get("token") if isinstance(trade.get("token"), dict) else {}
  user = trade.get("user") if isinstance(trade.get("user"), dict) else {}
  if not user and isinstance(trade.get("trader"), dict):
    user = trade["trader"]

  symbol = (
    trade.get("symbol")
    or token.get("symbol")
    or trade.get("tokenSymbol")
    or "UNKNOWN"
  )
  action = str(
    trade.get("side")
    or trade.get("action")
    or trade.get("type")
    or trade.get("tradeType")
    or "buy"
  ).lower()

  network_id = trade.get("networkId") or token.get("networkId") or trade.get("chainId")
  amount_usd = (
    trade.get("totalUsd")
    or trade.get("amountUsd")
    or trade.get("usdValue")
    or trade.get("notionalUsd")
    or trade.get("totalUsdc")
    or 0
  )

  trade_id = str(trade.get("id") or trade.get("tradeId") or trade.get("uuid") or "")
  trader_id = str(user.get("id") or user.get("userId") or trade.get("userId") or "")
  trader_name = str(
    user.get("handle")
    or user.get("username")
    or user.get("displayName")
    or user.get("name")
    or trade.get("userHandle")
    or trader_id
    or "fomo_trader"
  )

  rank_raw = user.get("rank") or user.get("leaderboardRank") or trade.get("userRank")
  rank_int: int | None = None
  if rank_raw is not None:
    try:
      rank_int = int(rank_raw)
    except (TypeError, ValueError):
      rank_int = None

  pnl_raw = user.get("pnlPct") or user.get("pnl") or trade.get("pnlPct")
  pnl_float: float | None = None
  if pnl_raw is not None:
    try:
      pnl_float = float(pnl_raw)
    except (TypeError, ValueError):
      pnl_float = None

  token_address = str(
    trade.get("tokenAddress")
    or trade.get("mint")
    or token.get("address")
    or token.get("tokenAddress")
    or ""
  ).strip()

  return {
    "event_type": "trade",
    "symbol": symbol,
    "action": action,
    "trader_id": trader_id,
    "trader_name": trader_name,
    "trader_rank": rank_int,
    "trader_pnl_pct": pnl_float,
    "chain": _network_chain(int(network_id) if network_id is not None else None),
    "amount_usd": float(amount_usd or 0),
    "token_address": token_address,
    "url": f"fomo:trade:{trade_id}" if trade_id else None,
    "alert_id": trade_id or None,
    "relevance": trader_relevance(rank_int, pnl_float),
  }


def normalize_trades_response(payload: object) -> list[dict]:
  if isinstance(payload, list):
    return [row for row in payload if isinstance(row, dict)]
  if isinstance(payload, dict):
    for key in ("trades", "items", "data", "results", "feed", "activity"):
      rows = payload.get(key)
      if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
  return []


async def scan_fomo_trades(session: AsyncSession) -> int:
  """Poll fomo.family authenticated trades feed when bearer token is configured."""
  if not settings.fomo_enabled:
    return 0

  from app.engines.platform_settings import get_fomo_bearer_token

  bearer = await get_fomo_bearer_token(session)
  if not bearer:
    return 0

  url = f"{FOMO_API_BASE}/trades?limit={settings.fomo_poll_limit}"
  headers = {
    "Accept": "application/json",
    "Authorization": f"Bearer {bearer}",
    "X-Supported-Chains": FOMO_SUPPORTED_CHAINS,
    "Origin": "https://fomo.family",
    "Referer": "https://fomo.family/",
    "User-Agent": "ApexTradingPlatform/1.0",
  }

  try:
    async with httpx.AsyncClient(timeout=25) as client:
      response = await client.get(url, headers=headers)
      if response.status_code == 401:
        print("[fomo] bearer token expired — update FOMO_BEARER_TOKEN or POST /api/admin/set-fomo-bearer")
        return 0
      response.raise_for_status()
      payload = response.json()
  except Exception as exc:
    print(f"[fomo] trade poll error: {exc}")
    return 0

  ingested = 0
  for trade in normalize_trades_response(payload):
    result = await ingest_fomo_webhook(session, trade_row_to_payload(trade))
    if result.get("status") == "received":
      ingested += 1
  return ingested
