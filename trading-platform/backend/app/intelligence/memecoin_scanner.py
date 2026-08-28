"""DexScreener + Hyperliquid memecoin intelligence scanners."""

from __future__ import annotations

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.intelligence.scanner import analyze_sentiment, categorize, extract_symbols, relevance_score
from app.models.entities import IntelligenceItem

DEXSCREENER_BOOSTS_URL = "https://api.dexscreener.com/token-boosts/top/v1"
DEXSCREENER_SEARCH_URL = "https://api.dexscreener.com/latest/dex/search"
HL_INFO_URL = "https://api.hyperliquid.xyz/info"

MEMECOIN_SEARCH_QUERIES = (
  "pump solana",
  "memecoin sol",
  "bonk wif pepe",
  "hyperliquid perp",
)

HL_MEME_COINS = ("kPEPE", "kBONK", "WIF", "DOGE", "MEME", "TRUMP", "SOL")

_MAX_DEX_SYMBOL_LEN = 20


def _sanitize_dex_symbol(symbol: str) -> str | None:
  """Reject spam concatenated tickers; keep short alphanumeric symbols only."""
  raw = (symbol or "").strip().upper()
  if not raw or len(raw) > _MAX_DEX_SYMBOL_LEN:
    return None
  if not raw.replace("$", "").isalnum():
    return None
  return raw


def _normalize_symbols_field(symbol: str) -> str:
  return symbol[:200]


def _map_dex_chain_symbol(chain_id: str, token_address: str, description: str) -> str:
  text = f"{description} {token_address}".upper()
  for sym in ("WIF", "BONK", "PEPE", "DOGE", "SHIB", "TRUMP", "MEME", "SOL"):
    if sym in text:
      return f"{sym}USDT" if sym != "SOL" else "SOLUSDT"
  if chain_id == "solana":
    return "SOLUSDT"
  return "BTCUSDT"


async def _add_intel(
  session: AsyncSession,
  *,
  source: str,
  title: str,
  content: str,
  url: str,
  sentiment: float,
  symbols: str,
  relevance: float,
) -> bool:
  existing = await session.execute(
    select(IntelligenceItem).where(
      (IntelligenceItem.url == url[:1000]) | (IntelligenceItem.title == title[:500])
    )
  )
  if existing.scalar_one_or_none():
    return False
  full_text = f"{title} {content}"
  session.add(
    IntelligenceItem(
      source=source,
      category=categorize(full_text) or "crypto",
      title=title[:500],
      content=content[:2000],
      url=url[:1000],
      sentiment=sentiment,
      relevance_score=relevance,
      symbols_mentioned=_normalize_symbols_field(symbols or extract_symbols(full_text)),
    )
  )
  return True


async def scan_dexscreener_trending(session: AsyncSession) -> int:
  """Top boosted Solana/EVM tokens from DexScreener — early memecoin discovery."""
  count = 0
  try:
    async with httpx.AsyncClient(timeout=20) as client:
      response = await client.get(DEXSCREENER_BOOSTS_URL)
      if response.status_code != 200:
        return 0
      boosts = response.json()
      if not isinstance(boosts, list):
        return 0
      for item in boosts[:12]:
        chain = item.get("chainId", "solana")
        token = item.get("tokenAddress", "")
        desc = item.get("description", "Trending memecoin")
        url = item.get("url", f"dexscreener:{chain}:{token}")
        symbol = _map_dex_chain_symbol(chain, token, desc)
        title = f"[DexScreener boost] {desc[:120]}"
        content = (
          f"Trending on DexScreener | chain={chain} | token={token[:12]}… | "
          f"boost={item.get('totalAmount', 0)}"
        )
        twitter = next(
          (l.get("url") for l in item.get("links", []) if l.get("type") == "twitter"),
          None,
        )
        if twitter:
          content += f" | X: {twitter}"
        if await _add_intel(
          session,
          source="dexscreener",
          title=title,
          content=content,
          url=url,
          sentiment=0.35,
          symbols=symbol,
          relevance=0.72,
        ):
          count += 1

      for query in MEMECOIN_SEARCH_QUERIES:
        search = await client.get(DEXSCREENER_SEARCH_URL, params={"q": query})
        if search.status_code != 200:
          continue
        pairs = search.json().get("pairs", [])[:5]
        for pair in pairs:
          base = pair.get("baseToken", {})
          symbol = _sanitize_dex_symbol(base.get("symbol", ""))
          if not symbol:
            continue
          mapped = f"{symbol}USDT" if not symbol.endswith("USDT") else symbol
          price_chg = float(pair.get("priceChange", {}).get("h24", 0) or 0)
          vol = float(pair.get("volume", {}).get("h24", 0) or 0)
          liq_raw = pair.get("liquidity", {}).get("usd")
          if liq_raw is None:
            continue
          liq = float(liq_raw or 0)
          if liq < settings.memecoin_min_liquidity_usd:
            continue
          title = f"[DexScreener] {symbol} {price_chg:+.1f}% 24h vol ${vol:,.0f}"
          content = (
            f"Query={query} | chain={pair.get('chainId')} | "
            f"liq=${liq:,.0f} | fdv=${float(pair.get('fdv', 0) or 0):,.0f}"
          )
          url = pair.get("url", f"dexscreener:search:{query}:{symbol}")
          sentiment = 0.45 if price_chg > 10 else 0.2 if price_chg > 0 else -0.25
          if await _add_intel(
            session,
            source="dexscreener",
            title=title,
            content=content,
            url=url,
            sentiment=sentiment,
            symbols=mapped,
            relevance=min(0.9, 0.5 + abs(price_chg) / 100),
          ):
            count += 1
  except Exception as e:
    print(f"DexScreener scan error: {e}")
  return count


async def scan_hyperliquid_memecoins(session: AsyncSession) -> int:
  """Hyperliquid perp mids + momentum for memecoin perps (kPEPE, WIF, kBONK, etc.)."""
  if not settings.hyperliquid_enabled:
    return 0
  count = 0
  try:
    async with httpx.AsyncClient(timeout=15) as client:
      meta = await client.post(HL_INFO_URL, json={"type": "metaAndAssetCtxs"})
      if meta.status_code != 200:
        return 0
      data = meta.json()
      if not isinstance(data, list) or len(data) < 2:
        return 0
      universe = data[0].get("universe", [])
      ctxs = data[1]
      for asset, ctx in zip(universe, ctxs):
        name = asset.get("name", "")
        if name not in HL_MEME_COINS:
          continue
        funding = float(ctx.get("funding", 0) or 0)
        prev_day = float(ctx.get("prevDayPx", 0) or 0)
        mark = float(ctx.get("markPx", 0) or 0)
        if prev_day <= 0 or mark <= 0:
          continue
        chg_pct = (mark - prev_day) / prev_day * 100
        mapped = name.replace("k", "") + "USDT" if name.startswith("k") else f"{name}USDT"
        if name == "SOL":
          mapped = "SOLUSDT"
        title = f"[Hyperliquid] {name} perp {chg_pct:+.1f}% 24h | funding {funding:.5f}"
        content = (
          f"HL perp mark=${mark:.6f} | prevDay=${prev_day:.6f} | "
          f"openInterest={ctx.get('openInterest', 'n/a')}"
        )
        sentiment = 0.4 if chg_pct > 5 else 0.15 if chg_pct > 0 else -0.3 if chg_pct < -5 else 0.0
        if funding > 0.0001:
          sentiment += 0.1
        elif funding < -0.0001:
          sentiment -= 0.1
        url = f"hyperliquid:perp:{name}"
        if await _add_intel(
          session,
          source="hyperliquid",
          title=title,
          content=content,
          url=url,
          sentiment=max(-0.85, min(0.85, sentiment)),
          symbols=mapped,
          relevance=0.78,
        ):
          count += 1
  except Exception as e:
    print(f"Hyperliquid intel scan error: {e}")
  return count


async def scan_memecoin_intel(session: AsyncSession) -> int:
  count = 0
  count += await scan_dexscreener_trending(session)
  count += await scan_hyperliquid_memecoins(session)
  return count
