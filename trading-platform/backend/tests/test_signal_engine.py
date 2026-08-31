"""Unit tests for SignalEngine technical analysis helpers."""

import numpy as np
import pandas as pd

from app.engines.signal_engine import SignalEngine


def _ohlc_frame(rows: int = 60, *, base: float = 100.0, volume: float = 1_000_000.0) -> pd.DataFrame:
  idx = np.arange(rows, dtype=float)
  close = base + np.sin(idx / 5.0) * 2.0
  return pd.DataFrame(
    {
      "close": close,
      "high": close + 0.5,
      "low": close - 0.5,
      "volume": np.full(rows, volume),
    }
  )


def test_volume_confirmed_true_when_recent_above_average():
  df = _ohlc_frame(30, volume=1_000_000.0)
  df.loc[df.index[-1], "volume"] = 1_200_000.0
  assert SignalEngine().volume_confirmed(df) is True


def test_volume_confirmed_false_when_recent_below_threshold():
  df = _ohlc_frame(30, volume=1_000_000.0)
  df.loc[df.index[-1], "volume"] = 500_000.0
  assert SignalEngine().volume_confirmed(df) is False


def test_volume_confirmed_defaults_true_without_volume_column():
  df = _ohlc_frame(30).drop(columns=["volume"])
  assert SignalEngine().volume_confirmed(df) is True


def test_near_level_within_tolerance():
  engine = SignalEngine()
  assert engine._near_level(100.0, 100.5, pct=0.015) is True
  assert engine._near_level(100.0, 110.0, pct=0.015) is False
  assert engine._near_level(100.0, None) is False


def test_rsi_divergence_bullish_pattern():
  engine = SignalEngine()
  close = pd.Series([10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0.5, 0.3, 0.2, 0.1, 0.05, 0.04, 0.03, 0.02, 0.01])
  rsi = pd.Series([40, 38, 36, 34, 32, 30, 28, 26, 24, 31, 32, 34, 36, 38, 40, 42, 44, 46, 48])
  assert engine._rsi_divergence(close, rsi, window=14) == "bullish"


def test_rsi_divergence_none_on_short_series():
  engine = SignalEngine()
  close = pd.Series([1, 2, 3])
  rsi = pd.Series([50, 51, 52])
  assert engine._rsi_divergence(close, rsi) == "none"


def test_analyze_returns_hold_on_insufficient_data():
  result = SignalEngine().analyze("TEST", pd.DataFrame({"close": [1, 2, 3]}), {})
  assert result.direction == "hold"
  assert result.reason == "Insufficient data"
  assert result.volume_confirmed is False


def test_composite_score_preserves_positive_technical_floor():
  engine = SignalEngine()
  score = engine.composite_score(0.6, 0.1, {"technical_weight": 0.4, "sentiment_weight": 0.3, "momentum_weight": 0.3})
  assert score >= 0.3
