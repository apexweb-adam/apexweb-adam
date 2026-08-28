"""Hyperliquid perp market data for paper-trading memecoin perps."""

from __future__ import annotations

from datetime import datetime, timedelta

import httpx
import numpy as np
import pandas as pd

HL_INFO_URL = "https://api.hyperliquid.xyz/info"

# Binance symbol → Hyperliquid perp coin name
HL_SYMBOL_MAP = {
  "BTCUSDT": "BTC",
  "ETHUSDT": "ETH",
  "SOLUSDT": "SOL",
  "DOGEUSDT": "DOGE",
  "PEPEUSDT": "kPEPE",
  "WIFUSDT": "WIF",
  "BONKUSDT": "kBONK",
  "SHIBUSDT": "kSHIB",
  "MEMEUSDT": "MEME",
  "TRUMPUSDT": "TRUMP",
}

_mids_cache: dict[str, float] = {}


async def fetch_hyperliquid_mid(coin: str) -> float:
  try:
    async with httpx.AsyncClient(timeout=10) as client:
      response = await client.post(HL_INFO_URL, json={"type": "allMids"})
      if response.status_code != 200:
        return 0.0
      mids = response.json()
      price = float(mids.get(coin, 0) or 0)
      if price > 0:
        _mids_cache[coin] = price
      return price
  except Exception as e:
    print(f"Hyperliquid mid error for {coin}: {e}")
    return _mids_cache.get(coin, 0.0)


async def fetch_hyperliquid_candles(
  coin: str,
  interval: str = "15m",
  limit: int = 100,
) -> tuple[float, pd.DataFrame | None]:
  """Fetch HL candle snapshot; returns (mark_price, ohlcv_df)."""
  interval_ms = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "1h": 3_600_000,
  }.get(interval, 900_000)

  end = int(datetime.utcnow().timestamp() * 1000)
  start = end - interval_ms * limit

  try:
    async with httpx.AsyncClient(timeout=15) as client:
      response = await client.post(
        HL_INFO_URL,
        json={
          "type": "candleSnapshot",
          "req": {"coin": coin, "interval": interval, "startTime": start, "endTime": end},
        },
      )
      if response.status_code != 200:
        mid = await fetch_hyperliquid_mid(coin)
        return mid, None
      candles = response.json()
      if not candles:
        mid = await fetch_hyperliquid_mid(coin)
        return mid, None

      rows = []
      for c in candles:
        rows.append({
          "timestamp": datetime.utcfromtimestamp(c["t"] / 1000),
          "open": float(c["o"]),
          "high": float(c["h"]),
          "low": float(c["l"]),
          "close": float(c["c"]),
          "volume": float(c["v"]),
        })
      df = pd.DataFrame(rows)
      price = float(df["close"].iloc[-1])
      _mids_cache[coin] = price
      return price, df
  except Exception as e:
    print(f"Hyperliquid candle error for {coin}: {e}")
    mid = _mids_cache.get(coin, 0.0)
    return mid, None


def hyperliquid_coin_for_symbol(symbol: str) -> str | None:
  return HL_SYMBOL_MAP.get(symbol.upper())


async def fetch_hyperliquid_for_symbol(symbol: str, interval: str = "15m") -> tuple[float, pd.DataFrame | None]:
  coin = hyperliquid_coin_for_symbol(symbol)
  if not coin:
    return 0.0, None
  return await fetch_hyperliquid_candles(coin, interval)
