"""Polymarket prediction market data for paper trading."""

import json
from datetime import datetime, timedelta

import httpx
import pandas as pd

from app.config import settings

# slug -> list of (timestamp, yes_price)
_pm_history: dict[str, list[tuple[datetime, float]]] = {}
_markets_cache: list[dict] = []
_markets_cache_at: datetime | None = None


async def fetch_top_markets(limit: int | None = None) -> list[dict]:
  global _markets_cache, _markets_cache_at
  cap = limit or settings.polymarket_max_markets
  if _markets_cache_at and (datetime.utcnow() - _markets_cache_at).seconds < 300 and _markets_cache:
    return _markets_cache[:cap]

  try:
    async with httpx.AsyncClient(timeout=20) as client:
      resp = await client.get(
        f"{settings.polymarket_api_url}/markets",
        params={
          "active": "true",
          "closed": "false",
          "limit": max(cap, 50),
          "order": "volume24hr",
          "ascending": "false",
        },
      )
      if resp.status_code != 200:
        return _markets_cache[:cap] if _markets_cache else []

      markets = resp.json()
      _markets_cache = [m for m in markets if m.get("slug") and is_macro_relevant_market(m)]
      _markets_cache_at = datetime.utcnow()
      return _markets_cache[:cap]
  except Exception as e:
    print(f"Polymarket markets fetch error: {e}")
    return _markets_cache[:cap] if _markets_cache else []


def _parse_yes_price(market: dict) -> float:
  try:
    prices = json.loads(market.get("outcomePrices", "[]"))
    if prices:
      return float(prices[0])
  except Exception:
    pass
  return 0.0


PM_SYMBOL_MAX_LEN = 64

# Macro/political markets aligned with intel keywords — excludes sports noise
MACRO_MARKET_KEYWORDS = [
  "bitcoin", "btc", "crypto", "ethereum", "solana", "trump", "fed",
  "tariff", "election", "gold", "oil", "recession", "rate cut", "inflation",
  "gdp", "war", "sanction", "debt", "default", "sec", "etf", "halving",
]

SPORTS_MARKET_EXCLUDE = [
  "mlb", "nba", "nfl", "nhl", "mls", "uefa", "atp", "wta", "f1", "formula",
  "soccer", "football", "basketball", "baseball", "tennis", "golf", "cricket",
  "champions league", "premier league", "world cup", "super bowl", "march madness",
  "ncaa", "pga", "ufc", "boxing", "nascar", "olympics",
  "lal-", "efl-", "epl-", "bundesliga", "serie-a", "la-liga", "spread", "bo3",
  "counter-strike", "cs2", "dota", "esports", "-draw", "-total", " vs ",
]


def is_macro_relevant_symbol(symbol: str) -> bool:
  """Heuristic macro check from PM: symbol slug when market metadata is unavailable."""
  if not symbol.startswith("PM:"):
    return True
  slug = symbol[3:]
  return is_macro_relevant_market({"slug": slug, "question": slug.replace("-", " ")})


def is_macro_relevant_market(market: dict) -> bool:
  """True when market question/slug matches macro/political themes (not sports)."""
  text = " ".join(
    str(market.get(k) or "")
    for k in ("question", "slug", "description", "groupItemTitle")
  ).lower()
  if any(ex in text for ex in SPORTS_MARKET_EXCLUDE):
    return False
  return any(kw in text for kw in MACRO_MARKET_KEYWORDS)


def pm_symbol(slug: str) -> str:
  max_slug = PM_SYMBOL_MAX_LEN - 3  # "PM:"
  return f"PM:{slug[:max_slug]}"


def pm_symbols_match(a: str, b: str) -> bool:
  """True when two PM: symbols refer to the same market (truncation-safe)."""
  if not a.startswith("PM:") or not b.startswith("PM:"):
    return a == b
  sa, sb = a[3:], b[3:]
  if sa == sb or sa.startswith(sb) or sb.startswith(sa):
    return True
  # VARCHAR truncation can clip the same slug at different lengths (-bps-a vs -bps-after)
  min_len = min(len(sa), len(sb))
  for length in range(min_len, 29, -1):
    if sa[:length] == sb[:length]:
      return True
  return False


def canonical_pm_symbol(symbol: str, market: dict | None) -> str:
  """Normalize to a single canonical symbol using the market's full slug."""
  if market and market.get("slug"):
    return pm_symbol(market["slug"])
  return symbol


def find_pm_position(positions: list, symbol: str):
  """Find open position matching symbol, including truncated slug variants."""
  for pos in positions:
    if pm_symbols_match(pos.symbol, symbol):
      return pos
  return None


def _match_stored_slug(stored: str, full_slug: str) -> bool:
  """Match truncated PM: slug prefix against full Polymarket slug."""
  if not stored or not full_slug:
    return False
  if full_slug == stored:
    return True
  return full_slug.startswith(stored)


async def _find_market_by_slug(stored_slug: str) -> dict | None:
  """Resolve market for a possibly truncated slug prefix."""
  markets = await fetch_top_markets(limit=max(settings.polymarket_max_markets, 200))
  for m in markets:
    s = m.get("slug", "")
    if _match_stored_slug(stored_slug, s):
      return m

  try:
    async with httpx.AsyncClient(timeout=15) as client:
      resp = await client.get(
        f"{settings.polymarket_api_url}/markets",
        params={
          "active": "true",
          "closed": "false",
          "limit": 200,
          "order": "volume24hr",
          "ascending": "false",
        },
      )
      if resp.status_code == 200:
        for m in resp.json():
          s = m.get("slug", "")
          if s and _match_stored_slug(stored_slug, s):
            return m
      resp = await client.get(
        f"{settings.polymarket_api_url}/markets",
        params={"slug": stored_slug, "limit": 1},
      )
      if resp.status_code == 200 and resp.json():
        return resp.json()[0]
  except Exception as e:
    print(f"Polymarket slug resolve error for {stored_slug[:24]}: {e}")
  return None


async def fetch_polymarket_data(symbol: str) -> tuple[float, pd.DataFrame | None]:
  """Symbol format PM:{slug}. Price = Yes share price (0–1)."""
  if not symbol.startswith("PM:"):
    return 0.0, None

  slug = symbol[3:]
  market = await _find_market_by_slug(slug)

  if not market:
    return 0.0, None

  full_slug = market.get("slug", slug)
  price = _parse_yes_price(market)
  if price <= 0 or price >= 1:
    return 0.0, None

  now = datetime.utcnow()
  hist = _pm_history.setdefault(full_slug, [])
  hist.append((now, price))
  _pm_history[full_slug] = [(t, p) for t, p in hist if t > now - timedelta(hours=48)][-200:]

  if len(_pm_history[full_slug]) >= 10:
    rows = []
    for ts, p in _pm_history[full_slug]:
      rows.append({
        "timestamp": ts,
        "open": p,
        "high": min(0.99, p * 1.002),
        "low": max(0.01, p * 0.998),
        "close": p,
        "volume": market.get("volume24hr", 1000) or 1000,
      })
    df = pd.DataFrame(rows)
    return price, df

  # No synthetic OHLCV — avoids fake MACD/momentum whipsaws on fresh markets
  return price, None


async def get_polymarket_symbols() -> list[str]:
  markets = await fetch_top_markets()
  return [pm_symbol(m["slug"]) for m in markets if m.get("slug")]


async def get_market_meta(symbol: str) -> dict | None:
  """Return gamma market dict for PM:{slug} symbol."""
  if not symbol.startswith("PM:"):
    return None
  slug = symbol[3:]
  market = await _find_market_by_slug(slug)
  if market:
    return market
  return None
