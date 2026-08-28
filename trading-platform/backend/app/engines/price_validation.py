"""Reject trades when fetched prices are implausible for a symbol."""

# (min, max) USD — blocks fallback/stale prices that inflate paper P&L
SYMBOL_PRICE_BOUNDS: dict[str, tuple[float, float]] = {
  "BTCUSDT": (1000, 500_000),
  "ETHUSDT": (50, 50_000),
  "SOLUSDT": (1, 10_000),
  "DOGEUSDT": (0.001, 10),
  "PEPEUSDT": (0.0000001, 0.01),
  "BNBUSDT": (10, 10_000),
  "XRPUSDT": (0.01, 100),
  "ADAUSDT": (0.01, 100),
  "AVAXUSDT": (1, 10_000),
  "LINKUSDT": (1, 10_000),
  "MATICUSDT": (0.01, 100),
  "SHIBUSDT": (0.00000001, 0.01),
  "WIFUSDT": (0.01, 100),
  "BONKUSDT": (0.00000001, 0.01),
  "PAXGUSDT": (500, 10_000),
  "XAUUSDT": (500, 10_000),
  "AAPL": (10, 2000),
  "MSFT": (10, 2000),
  "NVDA": (10, 2000),
  "TSLA": (10, 2000),
  "SPY": (10, 2000),
  "QQQ": (10, 2000),
  "ES=F": (1000, 50_000),
  "NQ=F": (1000, 100_000),
  "GC=F": (500, 10_000),
  "SI=F": (5, 500),
  "CL=F": (10, 500),
  "EURUSD=X": (0.5, 2.0),
}


def is_price_sane(symbol: str, price: float) -> bool:
  if price <= 0:
    return False
  if symbol.startswith("PM:"):
    return 0.02 <= price <= 0.98
  bounds = SYMBOL_PRICE_BOUNDS.get(symbol)
  if not bounds:
    return True
  low, high = bounds
  return low <= price <= high


def is_price_consistent(entry_price: float, current_price: float, max_move_pct: float = 0.20) -> bool:
  """Reject single-tick jumps that usually mean stale fallback data, not real markets."""
  if entry_price <= 0 or current_price <= 0:
    return False
  move = abs(current_price - entry_price) / entry_price
  return move <= max_move_pct
