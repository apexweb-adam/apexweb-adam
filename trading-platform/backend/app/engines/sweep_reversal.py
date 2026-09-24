"""Sweep reversal with a volume-absorption proxy (sleeve SR1).

Herman Sweep Reversal Map, from ICT Month 1: liquidity is swept, price
reclaims the level, then structure confirms the reversal. No arrows.

Bookmap-style iceberg / hidden-order heatmaps are not on this desk.
`absorption_score` and `hidden_liquidity` are a volume-climax plus wick
rejection proxy. They are not DOM, not an iceberg print, and not a live
ES order (including the 7731.25 example).

Paper only. Static risk is $400. This sleeve does not retune H11, F1,
F3, G1, or S1.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

SLEEVE_ID = "SR1"
PAPER_ONLY = True
RISK_USD = 400.0
DOM_AVAILABLE = False
BOOKMAP_PROXY_NOTE = (
  "No DOM. Hidden bid/offer is volume climax plus wick rejection only."
)


@dataclass
class SweepSignal:
  sleeve_id: str
  symbol: str
  direction: str
  score: float
  swept_level: float | None
  reclaim: bool
  structure_confirmed: bool
  absorption_score: float
  volume_climax: bool
  hidden_liquidity: str
  reason: str
  paper_only: bool = True
  risk_usd: float = RISK_USD
  dom_available: bool = False


def _series(df: pd.DataFrame, name: str) -> pd.Series:
  if name in df.columns:
    return df[name].astype(float)
  titled = name.capitalize()
  if titled in df.columns:
    return df[titled].astype(float)
  raise KeyError(name)


def _hold(symbol: str, reason: str, **kwargs) -> SweepSignal:
  return SweepSignal(
    sleeve_id=SLEEVE_ID,
    symbol=symbol,
    direction="hold",
    score=0.0,
    swept_level=None,
    reclaim=False,
    structure_confirmed=False,
    absorption_score=0.0,
    volume_climax=False,
    hidden_liquidity="none",
    reason=reason,
    paper_only=PAPER_ONLY,
    risk_usd=RISK_USD,
    dom_available=DOM_AVAILABLE,
    **kwargs,
  )


def _wick_ratio(high: float, low: float, close: float, open_: float | None, side: str) -> float:
  span = high - low
  if span <= 0:
    return 0.0
  body_edge = close if open_ is None else (min(open_, close) if side == "lower" else max(open_, close))
  if side == "lower":
    wick = body_edge - low
  else:
    wick = high - body_edge
  return max(0.0, wick) / span


def _absorption(wick_ratio: float, volume_ratio: float) -> float:
  vol_component = min(1.0, volume_ratio / 2.5)
  return round(min(1.0, 0.55 * wick_ratio + 0.45 * vol_component), 4)


def detect_sweep_reversal(
  df: pd.DataFrame,
  symbol: str = "ES",
  lookback: int = 20,
  climax_multiple: float = 1.5,
  wick_min: float = 0.35,
  min_absorption: float = 0.55,
) -> SweepSignal:
  """Last-bar sweep → reclaim → break of structure, plus absorption proxy."""
  if df is None or len(df) < lookback + 3:
    return _hold(symbol, "insufficient bars for sweep reversal")

  try:
    high = _series(df, "high")
    low = _series(df, "low")
    close = _series(df, "close")
  except KeyError:
    return _hold(symbol, "missing OHLC columns")

  volume = None
  try:
    volume = _series(df, "volume")
  except KeyError:
    volume = None

  open_ = None
  try:
    open_ = _series(df, "open")
  except KeyError:
    open_ = None

  history_high = high.iloc[-(lookback + 2):-2]
  history_low = low.iloc[-(lookback + 2):-2]
  if history_high.empty or history_low.empty:
    return _hold(symbol, "insufficient bars for sweep reversal")

  prior_high = float(history_high.max())
  prior_low = float(history_low.min())
  sweep_high = float(high.iloc[-2])
  sweep_low = float(low.iloc[-2])
  sweep_close = float(close.iloc[-2])
  confirm_close = float(close.iloc[-1])
  structure_high = float(high.iloc[-3])
  structure_low = float(low.iloc[-3])
  sweep_open = None if open_ is None else float(open_.iloc[-2])

  if volume is None:
    volume_ratio = 0.0
    volume_climax = False
  else:
    hist_vol = volume.iloc[-(lookback + 2):-2]
    mean_vol = float(hist_vol.mean()) if len(hist_vol) else 0.0
    sweep_vol = float(volume.iloc[-2])
    volume_ratio = (sweep_vol / mean_vol) if mean_vol > 0 else 0.0
    volume_climax = volume_ratio >= climax_multiple

  bullish_sweep = sweep_low < prior_low
  bearish_sweep = sweep_high > prior_high
  bullish_reclaim = bullish_sweep and (sweep_close > prior_low or confirm_close > prior_low)
  bearish_reclaim = bearish_sweep and (sweep_close < prior_high or confirm_close < prior_high)
  bullish_bos = confirm_close > structure_high
  bearish_bos = confirm_close < structure_low

  lower_wick = _wick_ratio(sweep_high, sweep_low, sweep_close, sweep_open, "lower")
  upper_wick = _wick_ratio(sweep_high, sweep_low, sweep_close, sweep_open, "upper")
  bullish_wick = lower_wick >= wick_min
  bearish_wick = upper_wick >= wick_min
  bullish_absorption = _absorption(lower_wick, volume_ratio)
  bearish_absorption = _absorption(upper_wick, volume_ratio)

  bullish_ok = (
    bullish_reclaim
    and bullish_bos
    and volume_climax
    and bullish_wick
    and bullish_absorption >= min_absorption
  )
  bearish_ok = (
    bearish_reclaim
    and bearish_bos
    and volume_climax
    and bearish_wick
    and bearish_absorption >= min_absorption
  )

  if bullish_ok and bearish_ok:
    return _hold(symbol, f"{BOOKMAP_PROXY_NOTE} Both sides fired; stand aside.")

  if bullish_ok:
    return SweepSignal(
      sleeve_id=SLEEVE_ID,
      symbol=symbol,
      direction="buy",
      score=bullish_absorption,
      swept_level=prior_low,
      reclaim=True,
      structure_confirmed=True,
      absorption_score=bullish_absorption,
      volume_climax=True,
      hidden_liquidity="bid",
      reason=(
        f"{BOOKMAP_PROXY_NOTE} Swept {prior_low:.4f}, reclaimed, "
        f"broke {structure_high:.4f}. Absorption {bullish_absorption:.2f}. "
        f"Paper risk ${RISK_USD:.0f}."
      ),
      paper_only=PAPER_ONLY,
      risk_usd=RISK_USD,
      dom_available=DOM_AVAILABLE,
    )

  if bearish_ok:
    return SweepSignal(
      sleeve_id=SLEEVE_ID,
      symbol=symbol,
      direction="sell",
      score=bearish_absorption,
      swept_level=prior_high,
      reclaim=True,
      structure_confirmed=True,
      absorption_score=bearish_absorption,
      volume_climax=True,
      hidden_liquidity="offer",
      reason=(
        f"{BOOKMAP_PROXY_NOTE} Swept {prior_high:.4f}, reclaimed, "
        f"broke {structure_low:.4f}. Absorption {bearish_absorption:.2f}. "
        f"Paper risk ${RISK_USD:.0f}."
      ),
      paper_only=PAPER_ONLY,
      risk_usd=RISK_USD,
      dom_available=DOM_AVAILABLE,
    )

  why = []
  if bullish_sweep or bearish_sweep:
    why.append("sweep")
  if bullish_reclaim or bearish_reclaim:
    why.append("reclaim")
  if (bullish_sweep and bullish_bos) or (bearish_sweep and bearish_bos):
    why.append("structure")
  if not volume_climax:
    why.append("no volume climax")
  detail = ", ".join(why) if why else "no sweep"
  return SweepSignal(
    sleeve_id=SLEEVE_ID,
    symbol=symbol,
    direction="hold",
    score=0.0,
    swept_level=prior_low if bullish_sweep else (prior_high if bearish_sweep else None),
    reclaim=bool(bullish_reclaim or bearish_reclaim),
    structure_confirmed=bool((bullish_sweep and bullish_bos) or (bearish_sweep and bearish_bos)),
    absorption_score=max(bullish_absorption, bearish_absorption) if (bullish_sweep or bearish_sweep) else 0.0,
    volume_climax=volume_climax,
    hidden_liquidity="none",
    reason=f"{BOOKMAP_PROXY_NOTE} Incomplete sequence ({detail}).",
    paper_only=PAPER_ONLY,
    risk_usd=RISK_USD,
    dom_available=DOM_AVAILABLE,
  )
