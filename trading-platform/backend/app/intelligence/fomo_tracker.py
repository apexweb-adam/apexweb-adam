"""fomo.family social copy-trading intel — leaderboard traders, alerts, and feed events.

fomo.family has no public API; ingest via POST /api/webhooks/fomo (browser bridge,
Zapier, or manual forwarding from alerts). See platform status for payload schema.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.intelligence.scanner import categorize
from app.models.entities import IntelligenceItem

FOMO_SOURCE = "fomo"
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
  return bool(settings.fomo_enabled and settings.tradingview_webhook_secret)


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
