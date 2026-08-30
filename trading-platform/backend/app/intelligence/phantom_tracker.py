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
from app.intelligence.memecoin_whales import DEFAULT_SOLANA_WHALE_ADDRESSES
from app.intelligence.scanner import categorize
from app.models.entities import IntelligenceItem

PHANTOM_SOURCE = "phantom"
TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
KNOWN_SOLANA_MINT_SYMBOLS: dict[str, str] = {
  "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263": "BONK",
  "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm": "WIF",
  "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr": "POPCAT",
  "ukHH6c7mMyiWCf1b9pnWe25TSpkDDt3H5pQZgZ74J82": "BOME",
}
STABLECOIN_MINTS = frozenset({
  "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
  "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
})
DEXSCREENER_TOKEN_URL = "https://api.dexscreener.com/latest/dex/tokens"


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


def phantom_poll_wallet_addresses() -> list[str]:
  """Wallets for 24/7 Helius portfolio poll — explicit PHANTOM_WALLET_ADDRESSES or default whales."""
  explicit = parse_phantom_wallet_addresses()
  if explicit:
    return explicit
  if settings.wallet_tracker_use_defaults:
    return list(DEFAULT_SOLANA_WHALE_ADDRESSES)
  return []


def phantom_portfolio_poll_active() -> bool:
  return bool(
    settings.phantom_enabled
    and settings.phantom_portfolio_poll_enabled
    and phantom_poll_wallet_addresses()
    and (
      settings.helius_api_key
      or settings.wallet_tracker_use_blockscout_fallback
    )
  )


def phantom_portfolio_poll_mode() -> str:
  if not phantom_portfolio_poll_active():
    return "off"
  if settings.helius_api_key:
    return "helius"
  return "rpc"


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

  from app.engines.intel_source_status import intel_source_feed_active

  if not await intel_source_feed_active(session, "phantom"):
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
  max_symbols = settings.phantom_hot_symbols_max
  for item in result.scalars().all():
    sym = normalize_fomo_symbol(item.symbols_mentioned or "")
    if sym in seen:
      continue
    seen.add(sym)
    symbols.append(sym)
    if len(symbols) >= max_symbols:
      break
  return symbols


async def _resolve_mint_symbols(client, mints: list[str]) -> dict[str, str]:
  """Resolve Solana mint addresses to ticker symbols via DexScreener."""
  resolved = {mint: symbol for mint, symbol in KNOWN_SOLANA_MINT_SYMBOLS.items() if mint in mints}
  pending = [mint for mint in mints if mint not in resolved]
  for offset in range(0, len(pending), 30):
    batch = pending[offset : offset + 30]
    if not batch:
      continue
    try:
      response = await client.get(f"{DEXSCREENER_TOKEN_URL}/{','.join(batch)}", timeout=20)
      if response.status_code != 200:
        continue
      pairs = response.json().get("pairs") or []
      if not isinstance(pairs, list):
        continue
      for pair in pairs:
        if not isinstance(pair, dict):
          continue
        base = pair.get("baseToken") or {}
        mint = str(base.get("address") or "")
        symbol = str(base.get("symbol") or "").strip().upper()
        if mint and symbol and len(symbol) <= 12 and symbol.isalnum():
          resolved[mint] = symbol
    except Exception as exc:
      print(f"[phantom] DexScreener mint resolve error: {exc}")
  return resolved


def _top_token_holdings(accounts: list[dict], *, limit: int = 8) -> list[tuple[str, float]]:
  """Return top SPL holdings by uiAmount, excluding stablecoins."""
  holdings: list[tuple[str, float]] = []
  for entry in accounts:
    parsed = (((entry.get("account") or {}).get("data") or {}).get("parsed") or {})
    info = parsed.get("info") or {}
    mint = str(info.get("mint") or "")
    if not mint or mint in STABLECOIN_MINTS:
      continue
    amount = float((info.get("tokenAmount") or {}).get("uiAmount") or 0)
    if amount <= 0:
      continue
    holdings.append((mint, amount))
  holdings.sort(key=lambda item: item[1], reverse=True)
  return holdings[:limit]


async def _ingest_phantom_holding(
  session: AsyncSession,
  *,
  address: str,
  symbol: str,
  amount: float,
  balance_usd: float,
  hour_bucket: str,
  mint: str = "",
) -> bool:
  result = await ingest_phantom_webhook(
    session,
    {
      "event_type": "holdings",
      "symbol": symbol,
      "wallet_address": address,
      "chain": "solana",
      "balance_usd": balance_usd,
      "message": f"Phantom portfolio holding {symbol} ({amount:,.4f})",
      "url": f"phantom:holdings:{address}:{mint or symbol}:{hour_bucket}",
      "relevance": 0.78 if balance_usd >= settings.phantom_min_holding_usd else 0.74,
      "token_address": mint,
    },
  )
  return result.get("status") == "received"


async def scan_phantom_portfolios(session: AsyncSession) -> int:
  """Poll token balances for Phantom-tracked wallets (Helius or Solana RPC fallback)."""
  if not settings.phantom_enabled or not settings.phantom_portfolio_poll_enabled:
    return 0

  addresses = phantom_poll_wallet_addresses()
  if not addresses:
    return 0

  ingested = 0
  if settings.helius_api_key:
    ingested += await _scan_phantom_helius(session, addresses)
  if ingested == 0 and settings.wallet_tracker_use_blockscout_fallback:
    ingested += await _scan_phantom_rpc(session, addresses)
  return ingested


async def _scan_phantom_helius(session: AsyncSession, addresses: list[str]) -> int:
  import httpx

  ingested = 0
  hour_bucket = datetime.utcnow().strftime("%Y%m%d%H")
  async with httpx.AsyncClient(timeout=25) as client:
    for address in addresses:
      try:
        response = await client.get(
          f"https://api.helius.xyz/v0/addresses/{address}/balances",
          params={"api-key": settings.helius_api_key},
        )
        if response.status_code != 200:
          continue
        payload = response.json()
      except Exception as exc:
        print(f"[phantom] Helius balance poll error for {address[:8]}…: {exc}")
        continue

      tokens = payload.get("tokens") if isinstance(payload, dict) else None
      if not isinstance(tokens, list):
        continue

      for token in tokens[:20]:
        if not isinstance(token, dict):
          continue
        symbol = str(token.get("symbol") or token.get("ticker") or "").strip().upper()
        if not symbol or symbol in ("USDC", "USDT"):
          continue
        amount = float(token.get("amount") or token.get("uiAmount") or 0)
        if amount <= 0:
          continue
        price_usd = float(token.get("priceUsd") or token.get("price_usd") or 0)
        balance_usd = float(token.get("valueUsd") or token.get("value_usd") or price_usd * amount or 0)
        if balance_usd and balance_usd < settings.phantom_min_holding_usd:
          continue

        mint = str(token.get("mint") or token.get("address") or "")
        if await _ingest_phantom_holding(
          session,
          address=address,
          symbol=symbol,
          amount=amount,
          balance_usd=balance_usd,
          hour_bucket=hour_bucket,
          mint=mint,
        ):
          ingested += 1
  return ingested


async def _scan_phantom_rpc(session: AsyncSession, addresses: list[str]) -> int:
  """Free Solana JSON-RPC fallback when Helius API key is not set."""
  import httpx

  ingested = 0
  hour_bucket = datetime.utcnow().strftime("%Y%m%d%H")
  rpc = settings.solana_rpc_url.strip() or "https://api.mainnet-beta.solana.com"
  async with httpx.AsyncClient(timeout=45) as client:
    for address in addresses[:8]:
      try:
        balance_response = await client.post(
          rpc,
          json={"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [address]},
        )
        if balance_response.status_code == 200:
          lamports = int((balance_response.json().get("result") or {}).get("value") or 0)
          sol_amount = lamports / 1e9
          if sol_amount >= 100:
            if await _ingest_phantom_holding(
              session,
              address=address,
              symbol="SOL",
              amount=sol_amount,
              balance_usd=sol_amount * 150,
              hour_bucket=hour_bucket,
            ):
              ingested += 1
      except Exception as exc:
        print(f"[phantom] RPC SOL balance error for {address[:8]}…: {exc}")

      try:
        response = await client.post(
          rpc,
          json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenAccountsByOwner",
            "params": [
              address,
              {"programId": TOKEN_PROGRAM_ID},
              {"encoding": "jsonParsed"},
            ],
          },
        )
        if response.status_code != 200:
          continue
        accounts = (response.json().get("result") or {}).get("value") or []
      except Exception as exc:
        print(f"[phantom] RPC balance poll error for {address[:8]}…: {exc}")
        continue

      top_holdings = _top_token_holdings(accounts, limit=8)
      if not top_holdings:
        continue
      mints = [mint for mint, _ in top_holdings]
      symbols = await _resolve_mint_symbols(client, mints)
      for mint, amount in top_holdings:
        symbol = symbols.get(mint, "")
        if not symbol or symbol in ("USDC", "USDT"):
          continue
        if await _ingest_phantom_holding(
          session,
          address=address,
          symbol=symbol,
          amount=amount,
          balance_usd=0,
          hour_bucket=hour_bucket,
          mint=mint,
        ):
          ingested += 1
  return ingested

