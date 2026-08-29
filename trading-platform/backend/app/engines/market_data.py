import random
from datetime import datetime, timedelta
from typing import Any

import httpx
import numpy as np
import pandas as pd

from app.config import settings

COINGECKO_IDS = {
  "BTCUSDT": "bitcoin",
  "ETHUSDT": "ethereum",
  "SOLUSDT": "solana",
  "DOGEUSDT": "dogecoin",
  "PEPEUSDT": "pepe",
  "BNBUSDT": "binancecoin",
  "XRPUSDT": "ripple",
  "ADAUSDT": "cardano",
  "AVAXUSDT": "avalanche-2",
  "LINKUSDT": "chainlink",
  "MATICUSDT": "matic-network",
  "SHIBUSDT": "shiba-inu",
  "WIFUSDT": "dogwifcoin",
  "BONKUSDT": "bonk",
  "FLOKIUSDT": "floki",
  "TRUMPUSDT": "official-trump",
  "MEMEUSDT": "memecoin-2",
  "PAXGUSDT": "pax-gold",
  "XAUUSDT": "pax-gold",
}

# Yahoo Finance tickers — primary fallback when Binance is geo-blocked (e.g. Render US)
YAHOO_CRYPTO_SYMBOLS = {
  "BTCUSDT": "BTC-USD",
  "ETHUSDT": "ETH-USD",
  "SOLUSDT": "SOL-USD",
  "DOGEUSDT": "DOGE-USD",
  "PEPEUSDT": "PEPE-USD",
  "BNBUSDT": "BNB-USD",
  "XRPUSDT": "XRP-USD",
  "ADAUSDT": "ADA-USD",
  "AVAXUSDT": "AVAX-USD",
  "LINKUSDT": "LINK-USD",
  "MATICUSDT": "MATIC-USD",
  "SHIBUSDT": "SHIB-USD",
  "WIFUSDT": "WIF-USD",
  "BONKUSDT": "BONK-USD",
  "FLOKIUSDT": "FLOKI-USD",
  "TRUMPUSDT": "TRUMP-USD",
  "MEMEUSDT": "MEME-USD",
  "PAXGUSDT": "PAXG-USD",
  "XAUUSDT": "GC=F",
}

# Prefer 24/7 crypto feeds over stale Yahoo futures for paper marks and exits.
CRYPTO_LIVE_PRICE_PROXY: dict[str, str] = {
  "XAUUSDT": "PAXGUSDT",
}
PROXY_ENTRY_RECONCILE_DRIFT_PCT = 0.008

_price_cache: dict[str, float] = {}


def proxy_entry_drift_pct(symbol: str, entry_price: float, live_price: float) -> float | None:
  """Return relative drift when symbol uses a live proxy feed."""
  if symbol not in CRYPTO_LIVE_PRICE_PROXY or entry_price <= 0 or live_price <= 0:
    return None
  return abs(live_price - entry_price) / entry_price


def reconcile_proxy_entry_levels(position: Any, live_price: float) -> bool:
  """Align entry/stop/take to the proxy feed when a legacy entry used a stale tick."""
  drift = proxy_entry_drift_pct(position.symbol, float(position.entry_price), live_price)
  if drift is None or drift <= PROXY_ENTRY_RECONCILE_DRIFT_PCT:
    return False
  ratio = live_price / float(position.entry_price)
  position.entry_price = live_price
  if position.stop_loss:
    position.stop_loss = float(position.stop_loss) * ratio
  if position.take_profit:
    position.take_profit = float(position.take_profit) * ratio
  return True


def generate_synthetic_ohlcv(base_price: float, periods: int = 100) -> pd.DataFrame:
  """Generate realistic OHLCV data when live APIs are unavailable."""
  np.random.seed(int(base_price) % 10000)
  returns = np.random.normal(0.0001, 0.002, periods)
  prices = base_price * np.cumprod(1 + returns)
  timestamps = [datetime.utcnow() - timedelta(minutes=5 * i) for i in range(periods, 0, -1)]

  data = []
  for i, (ts, close) in enumerate(zip(timestamps, prices)):
    vol = abs(np.random.normal(0, close * 0.001))
    data.append({
      "timestamp": ts,
      "open": close * (1 - vol),
      "high": close * (1 + vol),
      "low": close * (1 - vol * 1.5),
      "close": close,
      "volume": random.uniform(100, 10000),
    })
  return pd.DataFrame(data)


async def fetch_binance(symbol: str, interval: str = "5m", limit: int = 100) -> tuple[float, pd.DataFrame | None]:
  try:
    async with httpx.AsyncClient(timeout=10) as client:
      ticker = await client.get(
        f"{settings.binance_api_url}/ticker/price",
        params={"symbol": symbol},
      )
      if ticker.status_code != 200:
        return 0.0, None
      price = float(ticker.json()["price"])

      klines = await client.get(
        f"{settings.binance_api_url}/klines",
        params={"symbol": symbol, "interval": interval, "limit": limit},
      )
      if klines.status_code != 200:
        return price, None

      data = klines.json()
      if len(data) < 30:
        return price, None

      df = pd.DataFrame(
        data,
        columns=[
          "timestamp", "open", "high", "low", "close", "volume",
          "close_time", "quote_volume", "trades", "taker_buy_base",
          "taker_buy_quote", "ignore",
        ],
      )
      for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
      _price_cache[symbol] = price
      return price, df
  except Exception:
    return 0.0, None


async def fetch_coingecko(symbol: str) -> tuple[float, pd.DataFrame | None]:
  coin_id = COINGECKO_IDS.get(symbol)
  if not coin_id:
    return 0.0, None

  try:
    async with httpx.AsyncClient(timeout=15) as client:
      price_resp = await client.get(
        "https://api.coingecko.com/api/v3/simple/price",
        params={"ids": coin_id, "vs_currencies": "usd"},
      )
      if price_resp.status_code != 200:
        return 0.0, None
      price = float(price_resp.json()[coin_id]["usd"])

      ohlc_resp = await client.get(
        f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc",
        params={"vs_currency": "usd", "days": 1},
      )
      if ohlc_resp.status_code == 200 and len(ohlc_resp.json()) >= 30:
        ohlc = ohlc_resp.json()
        df = pd.DataFrame(ohlc, columns=["timestamp", "open", "high", "low", "close"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df["volume"] = random.uniform(1000, 50000)
        for col in ["open", "high", "low", "close"]:
          df[col] = df[col].astype(float)
        _price_cache[symbol] = price
        return price, df

      _price_cache[symbol] = price
      return price, None
  except Exception:
    return 0.0, None


async def fetch_yahoo_crypto(symbol: str, interval: str = "15m") -> tuple[float, pd.DataFrame | None]:
  """Fetch crypto via Yahoo chart API — works when Binance is geo-blocked."""
  yahoo_symbol = YAHOO_CRYPTO_SYMBOLS.get(symbol)
  if not yahoo_symbol:
    return 0.0, None

  range_ = "5d" if interval in ("5m", "15m") else "1mo"
  price, df = await fetch_yahoo_chart(yahoo_symbol, interval=interval, range_=range_)
  if price > 0:
    _price_cache[symbol] = price
    if df is not None and len(df) >= 30:
      return price, df
    return price, generate_synthetic_ohlcv(price)
  return 0.0, None


async def fetch_crypto_data(symbol: str, interval: str = "5m") -> tuple[float, pd.DataFrame | None]:
  proxy = CRYPTO_LIVE_PRICE_PROXY.get(symbol)
  if proxy and proxy != symbol:
    proxy_price, proxy_df = await fetch_crypto_data(proxy, interval)
    if proxy_price > 0:
      _price_cache[symbol] = proxy_price
      if proxy_df is not None and len(proxy_df) >= 30:
        return proxy_price, proxy_df
      return proxy_price, generate_synthetic_ohlcv(proxy_price)

  price, df = await fetch_binance(symbol, interval)
  if price > 0 and df is not None and len(df) >= 30:
    return price, df

  if settings.hyperliquid_enabled:
    from app.engines.hyperliquid_data import fetch_hyperliquid_for_symbol

    hl_price, hl_df = await fetch_hyperliquid_for_symbol(symbol, interval)
    if hl_price > 0 and hl_df is not None and len(hl_df) >= 30:
      _price_cache[symbol] = hl_price
      return hl_price, hl_df
    if hl_price > 0:
      _price_cache[symbol] = hl_price
      return hl_price, generate_synthetic_ohlcv(hl_price)

  yahoo_price, yahoo_df = await fetch_yahoo_crypto(symbol, interval)
  if yahoo_price > 0:
    return yahoo_price, yahoo_df

  cg_price, cg_df = await fetch_coingecko(symbol)
  if cg_price > 0:
    if cg_df is not None and len(cg_df) >= 30:
      return cg_price, cg_df
    return cg_price, generate_synthetic_ohlcv(cg_price)

  if price > 0:
    return price, generate_synthetic_ohlcv(price)

  cached = _price_cache.get(symbol, 0)
  if cached > 0:
    return cached, generate_synthetic_ohlcv(cached)

  return 0.0, None


YAHOO_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ApexTrading/1.0)"}


async def fetch_yahoo_chart(symbol: str, interval: str = "1h", range_: str = "1mo") -> tuple[float, pd.DataFrame | None]:
  """Primary stock/futures/commodity feed — avoids yfinance + hardcoded fallback bugs."""
  try:
    async with httpx.AsyncClient(timeout=15, headers=YAHOO_HEADERS) as client:
      resp = await client.get(
        "https://query1.finance.yahoo.com/v8/finance/chart/" + symbol,
        params={"interval": interval, "range": range_},
      )
      if resp.status_code != 200:
        return 0.0, None

      result = resp.json().get("chart", {}).get("result")
      if not result:
        return 0.0, None

      chart = result[0]
      meta = chart.get("meta", {})
      price = float(meta.get("regularMarketPrice") or meta.get("previousClose") or 0)
      if price <= 0:
        return 0.0, None

      timestamps = chart.get("timestamp") or []
      quote = chart.get("indicators", {}).get("quote", [{}])[0]
      if len(timestamps) < 30:
        _price_cache[symbol] = price
        return price, None

      rows = []
      for i, ts in enumerate(timestamps):
        close = quote.get("close", [None] * len(timestamps))[i]
        if close is None:
          continue
        rows.append({
          "timestamp": datetime.utcfromtimestamp(ts),
          "open": quote.get("open", [close] * len(timestamps))[i] or close,
          "high": quote.get("high", [close] * len(timestamps))[i] or close,
          "low": quote.get("low", [close] * len(timestamps))[i] or close,
          "close": close,
          "volume": quote.get("volume", [0] * len(timestamps))[i] or 0,
        })

      if len(rows) < 30:
        _price_cache[symbol] = price
        return price, None

      df = pd.DataFrame(rows)
      for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
      df = df.dropna(subset=["close"])
      _price_cache[symbol] = price
      return price, df
  except Exception:
    return 0.0, None


async def fetch_yfinance_data(symbol: str) -> tuple[float, pd.DataFrame | None]:
  price, df = await fetch_yahoo_chart(symbol)
  if price > 0 and df is not None:
    return price, df

  try:
    import yfinance as yf
    ticker = yf.Ticker(symbol)
    df = ticker.history(period="1mo", interval="1h")
    if not df.empty and len(df) >= 30:
      df = df.reset_index()
      df.columns = [c.lower() for c in df.columns]
      price = float(df["close"].iloc[-1])
      _price_cache[symbol] = price
      return price, df
  except Exception:
    pass

  cached = _price_cache.get(symbol, 0)
  if cached > 0:
    return cached, None

  return 0.0, None
