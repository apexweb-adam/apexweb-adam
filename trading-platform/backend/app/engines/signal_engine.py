from dataclasses import dataclass

import numpy as np
import pandas as pd
import ta


@dataclass
class SignalResult:
  symbol: str
  score: float
  direction: str
  rsi: float
  macd_signal: str
  momentum: float
  volatility: float
  reason: str


class SignalEngine:
  """Technical analysis signal generator using RSI, MACD, momentum, and volatility."""

  def analyze(self, symbol: str, df: pd.DataFrame, strategy_params: dict) -> SignalResult:
    if df is None or len(df) < 30:
      return SignalResult(
        symbol=symbol,
        score=0.0,
        direction="hold",
        rsi=50.0,
        macd_signal="neutral",
        momentum=0.0,
        volatility=0.0,
        reason="Insufficient data",
      )

    close = df["close"] if "close" in df.columns else df["Close"]
    high = df["high"] if "high" in df.columns else df["High"]
    low = df["low"] if "low" in df.columns else df["Low"]

    rsi = ta.momentum.RSIIndicator(close).rsi().iloc[-1]
    macd = ta.trend.MACD(close)
    macd_line = macd.macd().iloc[-1]
    macd_signal_line = macd.macd_signal().iloc[-1]
    macd_hist = macd.macd_diff().iloc[-1]

    momentum = (close.iloc[-1] - close.iloc[-10]) / close.iloc[-10] if len(close) >= 10 else 0
    volatility = close.pct_change().std() * np.sqrt(252) if len(close) > 1 else 0

    rsi_oversold = strategy_params.get("rsi_oversold", 30)
    rsi_overbought = strategy_params.get("rsi_overbought", 70)

    score = 0.0
    reasons: list[str] = []
    direction = "hold"

    if rsi < rsi_oversold:
      score += 0.35
      reasons.append(f"RSI oversold ({rsi:.1f})")
      direction = "buy"
    elif rsi > rsi_overbought:
      score -= 0.35
      reasons.append(f"RSI overbought ({rsi:.1f})")
      direction = "sell"

    if macd_hist > 0 and macd_line > macd_signal_line:
      score += 0.25
      reasons.append("MACD bullish crossover")
      if direction == "hold":
        direction = "buy"
    elif macd_hist < 0 and macd_line < macd_signal_line:
      score -= 0.25
      reasons.append("MACD bearish crossover")
      if direction == "hold":
        direction = "sell"

    if momentum > 0.02:
      score += 0.2
      reasons.append(f"Strong momentum (+{momentum*100:.1f}%)")
    elif momentum < -0.02:
      score -= 0.2
      reasons.append(f"Negative momentum ({momentum*100:.1f}%)")

    if volatility > 0.5:
      score *= 0.8
      reasons.append("High volatility - reduced confidence")

    score = max(-1.0, min(1.0, score))
    macd_signal = "bullish" if macd_hist > 0 else "bearish" if macd_hist < 0 else "neutral"

    return SignalResult(
      symbol=symbol,
      score=abs(score),
      direction=direction if score > 0 else "sell" if score < 0 else "hold",
      rsi=float(rsi) if not np.isnan(rsi) else 50.0,
      macd_signal=macd_signal,
      momentum=float(momentum),
      volatility=float(volatility) if not np.isnan(volatility) else 0.0,
      reason="; ".join(reasons) if reasons else "No clear signal",
    )

  def composite_score(
    self,
    technical_score: float,
    sentiment_score: float,
    weights: dict,
  ) -> float:
    base = (
      technical_score * weights.get("technical_weight", 0.4)
      + abs(sentiment_score) * weights.get("sentiment_weight", 0.3)
      + technical_score * weights.get("momentum_weight", 0.3)
    )
    return max(base, technical_score * 0.5) if technical_score > 0 else base
