"""Polymarket prediction market data for paper trading."""

import json
from datetime import datetime, timedelta

import httpx
import pandas as pd

from app.config import settings
from app.engines.market_data import generate_synthetic_ohlcv

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
      _markets_cache = [m for m in markets if m.get("slug")]
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


def pm_symbol(slug: str) -> str:
  return f"PM:{slug[:48]}"


async def fetch_polymarket_data(symbol: str) -> tuple[float, pd.DataFrame | None]:
  """Symbol format PM:{slug}. Price = Yes share price (0–1)."""
  if not symbol.startswith("PM:"):
    return 0.0, None

  slug = symbol[3:]
  markets = await fetch_top_markets()
  market = next((m for m in markets if m.get("slug") == slug or m.get("slug", "").startswith(slug)), None)

  if not market:
    async with httpx.AsyncClient(timeout=15) as client:
      resp = await client.get(
        f"{settings.polymarket_api_url}/markets",
        params={"slug": slug, "limit": 1},
      )
      if resp.status_code == 200 and resp.json():
        market = resp.json()[0]

  if not market:
    return 0.0, None

  price = _parse_yes_price(market)
  if price <= 0.01 or price >= 0.99:
    return 0.0, None

  now = datetime.utcnow()
  hist = _pm_history.setdefault(slug, [])
  hist.append((now, price))
  _pm_history[slug] = [(t, p) for t, p in hist if t > now - timedelta(hours=48)][-200:]

  if len(_pm_history[slug]) >= 10:
    rows = []
    for ts, p in _pm_history[slug]:
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

  return price, generate_synthetic_ohlcv(price, 60)


async def get_polymarket_symbols() -> list[str]:
  markets = await fetch_top_markets()
  return [pm_symbol(m["slug"]) for m in markets if m.get("slug")]


async def get_market_meta(symbol: str) -> dict | None:
  """Return gamma market dict for PM:{slug} symbol."""
  if not symbol.startswith("PM:"):
    return None
  slug = symbol[3:]
  markets = await fetch_top_markets()
  for m in markets:
    s = m.get("slug", "")
    if s == slug or s.startswith(slug):
      return m
  async with httpx.AsyncClient(timeout=15) as client:
    resp = await client.get(
      f"{settings.polymarket_api_url}/markets",
      params={"slug": slug, "limit": 1},
    )
    if resp.status_code == 200 and resp.json():
      return resp.json()[0]
  return None
