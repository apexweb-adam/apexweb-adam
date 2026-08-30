"""Polymarket prediction market data for paper trading."""

import json
from datetime import datetime, timedelta
from typing import Any

import httpx
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

PM_HISTORY_SETTING_KEY = "pm_price_history"
PM_HISTORY_MIN_TICKS = 10
PM_HISTORY_MAX_POINTS = 200

# slug -> list of (timestamp, yes_price)
_pm_history: dict[str, list[tuple[datetime, float]]] = {}
_pm_history_dirty = False
_pm_history_loaded = False
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


def _parse_yes_token_id(market: dict) -> str | None:
  raw = market.get("clobTokenIds")
  if not raw:
    return None
  try:
    ids = json.loads(raw) if isinstance(raw, str) else raw
    if isinstance(ids, list) and ids:
      return str(ids[0])
  except Exception:
    pass
  return None


def _merge_history_points(
  slug: str,
  points: list[tuple[datetime, float]],
) -> None:
  global _pm_history_dirty
  if not points:
    return
  merged: dict[datetime, float] = {t: p for t, p in _pm_history.get(slug, [])}
  for ts, price in points:
    merged[ts] = price
  ordered = sorted(merged.items(), key=lambda item: item[0])[-PM_HISTORY_MAX_POINTS:]
  _pm_history[slug] = ordered
  _pm_history_dirty = True


def _history_to_dataframe(
  hist: list[tuple[datetime, float]],
  market: dict,
) -> pd.DataFrame:
  volume = market.get("volume24hr", 1000) or 1000
  rows = []
  for ts, p in hist:
    rows.append({
      "timestamp": ts,
      "open": p,
      "high": min(0.99, p * 1.002),
      "low": max(0.01, p * 0.998),
      "close": p,
      "volume": volume,
    })
  return pd.DataFrame(rows)


async def _fetch_clob_price_history(token_id: str) -> list[tuple[datetime, float]]:
  try:
    async with httpx.AsyncClient(timeout=20) as client:
      resp = await client.get(
        f"{settings.polymarket_clob_api_url}/prices-history",
        params={
          "market": token_id,
          "interval": "1d",
          "fidelity": 30,
        },
      )
      if resp.status_code != 200:
        return []
      history = resp.json().get("history") or []
      points: list[tuple[datetime, float]] = []
      for point in history:
        ts_raw = point.get("t")
        price_raw = point.get("p")
        if ts_raw is None or price_raw is None:
          continue
        price = float(price_raw)
        if price <= 0 or price >= 1:
          continue
        points.append((datetime.utcfromtimestamp(int(ts_raw)), price))
      return points[-PM_HISTORY_MAX_POINTS:]
  except Exception as exc:
    print(f"Polymarket CLOB history error: {exc}")
    return []


async def _bootstrap_history_from_clob(full_slug: str, market: dict) -> None:
  if len(_pm_history.get(full_slug, [])) >= PM_HISTORY_MIN_TICKS:
    return
  token_id = _parse_yes_token_id(market)
  if not token_id:
    return
  boot = await _fetch_clob_price_history(token_id)
  _merge_history_points(full_slug, boot)


def serialize_pm_history() -> dict[str, list[list[Any]]]:
  return {
    slug: [[ts.isoformat(), price] for ts, price in hist[-100:]]
    for slug, hist in _pm_history.items()
    if hist
  }


def load_pm_history_payload(payload: dict[str, list[list[Any]]]) -> None:
  global _pm_history_loaded
  for slug, points in payload.items():
    parsed: list[tuple[datetime, float]] = []
    for point in points:
      if not point or len(point) < 2:
        continue
      iso, price = point[0], point[1]
      try:
        parsed.append((datetime.fromisoformat(str(iso).replace("Z", "")), float(price)))
      except (TypeError, ValueError):
        continue
    if parsed:
      _merge_history_points(slug, parsed)
  _pm_history_loaded = True


async def hydrate_pm_history_from_settings(session: AsyncSession) -> None:
  global _pm_history_loaded
  if _pm_history_loaded:
    return
  from app.engines.platform_settings import get_platform_setting

  raw = await get_platform_setting(session, PM_HISTORY_SETTING_KEY)
  if raw:
    try:
      load_pm_history_payload(json.loads(raw))
    except json.JSONDecodeError:
      _pm_history_loaded = True
      return
  _pm_history_loaded = True


async def persist_pm_history_to_settings(session: AsyncSession) -> None:
  global _pm_history_dirty
  if not _pm_history_dirty:
    return
  from app.engines.platform_settings import set_platform_setting

  await set_platform_setting(session, PM_HISTORY_SETTING_KEY, json.dumps(serialize_pm_history()))
  _pm_history_dirty = False


def clear_pm_history_cache() -> None:
  """Test helper — reset in-memory PM history."""
  global _pm_history, _pm_history_dirty, _pm_history_loaded
  _pm_history = {}
  _pm_history_dirty = False
  _pm_history_loaded = False


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
  _merge_history_points(full_slug, [(now, price)])
  _pm_history[full_slug] = [
    (t, p) for t, p in _pm_history[full_slug] if t > now - timedelta(hours=48)
  ][-PM_HISTORY_MAX_POINTS:]

  await _bootstrap_history_from_clob(full_slug, market)

  if len(_pm_history[full_slug]) >= PM_HISTORY_MIN_TICKS:
    df = _history_to_dataframe(_pm_history[full_slug], market)
    return price, df

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
