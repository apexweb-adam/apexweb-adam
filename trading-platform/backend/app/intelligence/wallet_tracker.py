"""On-chain wallet activity scanner — whale moves feed crypto bot sentiment."""

from __future__ import annotations

from datetime import datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.intelligence.scanner import (
  analyze_sentiment,
  categorize,
  extract_symbols,
  relevance_score,
)
from app.models.entities import IntelligenceItem

# Well-known exchange hot wallets (outflow from whale → exchange ≈ distribution).
_EXCHANGE_HINTS = (
  "binance",
  "coinbase",
  "kraken",
  "okex",
  "okx",
  "huobi",
  "kucoin",
)

_TOKEN_SYMBOL_MAP = {
  "WBTC": "BTC",
  "WETH": "ETH",
  "STETH": "ETH",
}


def parse_wallet_addresses(raw: str) -> list[str]:
  return [a.strip().lower() for a in raw.split(",") if a.strip().startswith("0x")]


def _token_value_usd(value_raw: str, decimals: str | int, symbol: str) -> float:
  try:
    dec = int(decimals)
    amount = int(value_raw) / (10**dec)
  except (TypeError, ValueError):
    return 0.0
  # Rough USD proxy for major tokens when price oracle unavailable.
  sym = symbol.upper()
  if sym in ("USDT", "USDC", "DAI", "BUSD"):
    return amount
  if sym in ("WBTC", "BTC"):
    return amount * 60_000
  if sym in ("WETH", "ETH", "STETH"):
    return amount * 3_000
  if sym in ("SOL"):
    return amount * 150
  return amount * 1.0


def _transfer_sentiment(
  *,
  watched: str,
  from_addr: str,
  to_addr: str,
  usd_estimate: float,
) -> float:
  """Accumulation into watched wallet is bullish; outflow to exchange is bearish."""
  watched = watched.lower()
  from_addr = from_addr.lower()
  to_addr = to_addr.lower()
  if to_addr == watched and from_addr != watched:
    base = 0.45
    if usd_estimate >= settings.wallet_tracker_min_usd * 5:
      base = 0.65
    return min(0.85, base)
  if from_addr == watched and to_addr != watched:
    base = -0.35
    if any(hint in to_addr for hint in _EXCHANGE_HINTS):
      base = -0.55
    if usd_estimate >= settings.wallet_tracker_min_usd * 5:
      base = min(-0.35, base - 0.15)
    return max(-0.85, base)
  return 0.0


async def scan_wallet_tracker(session: AsyncSession) -> int:
  """Poll Etherscan token transfers for configured whale/smart-money addresses."""
  addresses = parse_wallet_addresses(settings.wallet_tracker_addresses)
  if not addresses:
    return 0

  api_key = settings.etherscan_api_key or "YourApiKeyToken"
  count = 0

  async with httpx.AsyncClient(timeout=20) as client:
    for address in addresses:
      try:
        response = await client.get(
          "https://api.etherscan.io/api",
          params={
            "module": "account",
            "action": "tokentx",
            "address": address,
            "page": 1,
            "offset": 15,
            "sort": "desc",
            "apikey": api_key,
          },
        )
        data = response.json()
        if data.get("status") != "1":
          continue
        for tx in data.get("result", []):
          tx_hash = tx.get("hash", "")
          if not tx_hash:
            continue
          existing = await session.execute(
            select(IntelligenceItem).where(
              IntelligenceItem.source == "wallet_tracker",
              IntelligenceItem.url == tx_hash[:1000],
            )
          )
          if existing.scalar_one_or_none():
            continue

          token_symbol = tx.get("tokenSymbol", "TOKEN")
          mapped = _TOKEN_SYMBOL_MAP.get(token_symbol.upper(), token_symbol.upper())
          from_addr = tx.get("from", "")
          to_addr = tx.get("to", "")
          usd_est = _token_value_usd(
            tx.get("value", "0"),
            tx.get("tokenDecimal", 18),
            token_symbol,
          )
          if usd_est < settings.wallet_tracker_min_usd:
            continue

          direction = "IN" if to_addr.lower() == address else "OUT"
          sentiment = _transfer_sentiment(
            watched=address,
            from_addr=from_addr,
            to_addr=to_addr,
            usd_estimate=usd_est,
          )
          title = (
            f"[Whale {direction}] {mapped} ${usd_est:,.0f} "
            f"({address[:6]}…{address[-4:]})"
          )
          content = (
            f"Token {token_symbol} transfer {direction} | "
            f"from {from_addr[:10]}… to {to_addr[:10]}… | "
            f"est ${usd_est:,.0f} | tx {tx_hash[:18]}…"
          )
          full_text = f"{title} {content} {mapped}"
          session.add(
            IntelligenceItem(
              source="wallet_tracker",
              category=categorize(full_text) or "crypto",
              title=title[:500],
              content=content[:2000],
              url=tx_hash[:1000],
              sentiment=sentiment if sentiment != 0 else analyze_sentiment(full_text),
              relevance_score=max(0.65, relevance_score(full_text, "crypto")),
              symbols_mentioned=extract_symbols(full_text) or mapped,
            )
          )
          count += 1
      except Exception as e:
        print(f"Wallet tracker scan error for {address[:10]}…: {e}")
  return count


async def ingest_wallet_webhook(session: AsyncSession, payload: dict) -> dict:
  """Accept external wallet-tracker / social-monitor events via webhook."""
  address = str(payload.get("address", payload.get("wallet", ""))).strip()
  symbol = str(payload.get("symbol", payload.get("token", "UNKNOWN"))).upper()
  action = str(payload.get("action", payload.get("direction", "transfer"))).lower()
  amount_usd = float(payload.get("amount_usd", payload.get("usd", 0)) or 0)
  chain = str(payload.get("chain", "ethereum"))
  tx_hash = str(payload.get("tx_hash", payload.get("hash", ""))).strip()
  source = str(payload.get("source", "wallet_tracker"))
  if source not in ("wallet_tracker", "x", "reddit"):
    source = "wallet_tracker"

  if action in ("buy", "in", "accumulate", "deposit"):
    sentiment = 0.55
  elif action in ("sell", "out", "distribute", "withdraw"):
    sentiment = -0.55
  else:
    sentiment = float(payload.get("sentiment", 0.0))

  title = payload.get("title") or f"[{source}] {action} {symbol}"
  if amount_usd:
    title = f"{title} ${amount_usd:,.0f}"
  content = payload.get(
    "message",
    payload.get(
      "content",
      f"{action} {symbol} on {chain}"
      + (f" | wallet {address[:10]}…" if address else "")
      + (f" | ${amount_usd:,.0f}" if amount_usd else ""),
    ),
  )
  url = tx_hash or payload.get("url", f"webhook:{source}:{datetime.utcnow().isoformat()}")

  existing = await session.execute(
    select(IntelligenceItem).where(IntelligenceItem.url == url[:1000])
  )
  if existing.scalar_one_or_none():
    return {"status": "duplicate", "symbol": symbol}

  full_text = f"{title} {content} {symbol}"
  session.add(
    IntelligenceItem(
      source=source,
      category=payload.get("category") or categorize(full_text) or "crypto",
      title=str(title)[:500],
      content=str(content)[:2000],
      url=url[:1000],
      sentiment=sentiment,
      relevance_score=float(payload.get("relevance", 0.85)),
      symbols_mentioned=payload.get("symbols_mentioned") or symbol,
    )
  )
  await session.commit()
  return {"status": "received", "symbol": symbol, "source": source, "action": action}
